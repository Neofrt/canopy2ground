from __future__ import annotations

import argparse
from pathlib import Path

import numpy as np
import pandas as pd
from scipy import stats
import statsmodels.api as sm
from statsmodels.stats.multitest import multipletests

TZ_LOCAL = "America/Belem"
SOURCE_FILES = {
    "FIELD": "field_microclimate_hourly.csv",
    "ERA5": "era5_land_hourly.csv",
    "INMET": "inmet_hourly.csv",
}
VARIABLES = {
    "temperature": {"field": "field_temp_C", "external": "temp_C", "unit": "°C", "label": "Temperatura do ar"},
    "rh": {"field": "field_rh_pct", "external": "rh_pct", "unit": "p.p.", "label": "Umidade relativa"},
    "vpd": {"field": "field_vpd_kPa", "external": "vpd_kPa", "unit": "kPa", "label": "VPD"},
}
CONTRASTS = [("ERA5", "FIELD"), ("INMET", "FIELD"), ("ERA5", "INMET")]


def normalize_datetime(series: pd.Series) -> pd.Series:
    dt = pd.to_datetime(series, errors="coerce")
    try:
        tz = dt.dt.tz
    except AttributeError:
        tz = None
    if tz is None:
        return dt.dt.tz_localize(TZ_LOCAL, ambiguous="NaT", nonexistent="shift_forward")
    return dt.dt.tz_convert(TZ_LOCAL)


def calc_vpd(temp_c: pd.Series, rh_pct: pd.Series) -> pd.Series:
    es = 0.6108 * np.exp((17.27 * temp_c) / (temp_c + 237.3))
    return es * (1.0 - rh_pct / 100.0)


def read_source(path: Path, source: str) -> pd.DataFrame:
    if not path.exists():
        raise FileNotFoundError(f"Arquivo não encontrado para {source}: {path}")
    df = pd.read_csv(path, low_memory=False)
    if "datetime_local" not in df.columns:
        raise ValueError(f"{source}: coluna 'datetime_local' não encontrada em {path}")
    df["datetime_local"] = normalize_datetime(df["datetime_local"])
    df = df[df["datetime_local"].notna()].copy()
    df["datetime_local"] = df["datetime_local"].dt.floor("h")

    if source == "FIELD":
        if any(c not in df.columns for c in ["field_temp_C", "field_rh_pct"]):
            raise ValueError(f"{source}: colunas field_temp_C/field_rh_pct ausentes")
        if "field_vpd_kPa" not in df.columns:
            df["field_vpd_kPa"] = calc_vpd(df["field_temp_C"], df["field_rh_pct"])
        cols = {"field_temp_C": "temperature", "field_rh_pct": "rh", "field_vpd_kPa": "vpd"}
    else:
        if any(c not in df.columns for c in ["temp_C", "rh_pct"]):
            raise ValueError(f"{source}: colunas temp_C/rh_pct ausentes")
        if "vpd_kPa" not in df.columns:
            df["vpd_kPa"] = calc_vpd(df["temp_C"], df["rh_pct"])
        cols = {"temp_C": "temperature", "rh_pct": "rh", "vpd_kPa": "vpd"}

    out = df[["datetime_local"] + list(cols)].rename(columns={old: f"{source}_{new}" for old, new in cols.items()})
    numeric = [c for c in out.columns if c != "datetime_local"]
    return out.groupby("datetime_local", as_index=False)[numeric].mean().sort_values("datetime_local")


def build_hourly_common(root: Path, window: str, sources: tuple[str, ...]) -> pd.DataFrame:
    proc = root / "data" / "processed" / "climate"
    frames = [read_source(proc / SOURCE_FILES[s], s) for s in sources]
    merged = frames[0]
    for frame in frames[1:]:
        merged = merged.merge(frame, on="datetime_local", how="inner")
    if window == "light":
        h = merged["datetime_local"].dt.hour
        merged = merged[(h >= 6) & (h < 18)].copy()
    return merged.sort_values("datetime_local").reset_index(drop=True)


def build_daily_common(hourly: pd.DataFrame, min_hours: int) -> pd.DataFrame:
    x = hourly.copy()
    x["date"] = x["datetime_local"].dt.date
    value_cols = [c for c in x.columns if c not in {"datetime_local", "date"}]
    daily = x.groupby("date", as_index=False)[value_cols].mean()
    counts = x.groupby("date", as_index=False).size().rename(columns={"size": "n_common_hours"})
    daily = daily.merge(counts, on="date", how="left")
    daily = daily[daily["n_common_hours"] >= min_hours].copy()
    daily["date"] = pd.to_datetime(daily["date"])
    return daily.sort_values("date").reset_index(drop=True)


def pearson_safe(x: np.ndarray, y: np.ndarray) -> tuple[float, float]:
    if len(x) < 3 or np.nanstd(x) == 0 or np.nanstd(y) == 0:
        return np.nan, np.nan
    r, p = stats.pearsonr(x, y)
    return float(r), float(p)


def ccc(x: np.ndarray, y: np.ndarray) -> float:
    if len(x) < 2:
        return np.nan
    mx, my = np.mean(x), np.mean(y)
    vx, vy = np.var(x, ddof=1), np.var(y, ddof=1)
    cov = np.cov(x, y, ddof=1)[0, 1]
    den = vx + vy + (mx - my) ** 2
    return float(2 * cov / den) if den != 0 else np.nan


def agreement_metrics(a: np.ndarray, b: np.ndarray) -> dict:
    ok = np.isfinite(a) & np.isfinite(b)
    a, b = a[ok], b[ok]
    n = len(a)
    if n < 3:
        return {k: (n if k == "n" else np.nan) for k in ["n", "mean_A", "mean_B", "bias_A_minus_B", "mae", "rmse", "r", "r_p", "r2", "ccc", "slope_B_on_A", "intercept_B_on_A"]}
    diff = a - b
    r, rp = pearson_safe(a, b)
    lr = stats.linregress(a, b) if np.nanstd(a) > 0 else None
    return {
        "n": n, "mean_A": float(np.mean(a)), "mean_B": float(np.mean(b)),
        "bias_A_minus_B": float(np.mean(diff)), "mae": float(np.mean(np.abs(diff))),
        "rmse": float(np.sqrt(np.mean(diff**2))), "r": r, "r_p": rp,
        "r2": float(r**2) if np.isfinite(r) else np.nan, "ccc": ccc(a, b),
        "slope_B_on_A": float(lr.slope) if lr else np.nan,
        "intercept_B_on_A": float(lr.intercept) if lr else np.nan,
    }


def glsar_bias_test(diff: np.ndarray, maxiter: int = 50) -> dict:
    diff = np.asarray(diff, dtype=float)
    diff = diff[np.isfinite(diff)]
    n = len(diff)
    if n < 8:
        return {"n_model": n, "bias_ar1": np.nan, "se_ar1": np.nan, "ci95_low": np.nan, "ci95_high": np.nan, "t_value": np.nan, "p_value": np.nan, "rho_ar1": np.nan}
    model = sm.GLSAR(diff, np.ones((n, 1)), rho=1)
    res = model.iterative_fit(maxiter=maxiter)
    ci = np.asarray(res.conf_int(alpha=0.05))[0]
    try:
        rho = float(np.asarray(model.rho).ravel()[0])
    except Exception:
        rho = np.nan
    return {"n_model": n, "bias_ar1": float(res.params[0]), "se_ar1": float(res.bse[0]), "ci95_low": float(ci[0]), "ci95_high": float(ci[1]), "t_value": float(res.tvalues[0]), "p_value": float(res.pvalues[0]), "rho_ar1": rho}


def analyze_variable(daily: pd.DataFrame, variable: str) -> list[dict]:
    rows = []
    for a, b in CONTRASTS:
        pair = daily[["date", f"{a}_{variable}", f"{b}_{variable}"]].dropna().copy()
        arr_a = pair[f"{a}_{variable}"].to_numpy(dtype=float)
        arr_b = pair[f"{b}_{variable}"].to_numpy(dtype=float)
        rows.append({"variable": variable, "contrast": f"{a} - {b}", "source_A": a, "source_B": b, **agreement_metrics(arr_a, arr_b), **glsar_bias_test(arr_a - arr_b)})
    return rows


def add_holm_adjustment(df: pd.DataFrame) -> pd.DataFrame:
    out = df.copy()
    out["p_holm_within_variable"] = np.nan
    for _, idx in out.groupby("variable").groups.items():
        idx = list(idx)
        p = out.loc[idx, "p_value"].to_numpy(dtype=float)
        ok = np.isfinite(p)
        if ok.any():
            out.loc[np.array(idx)[ok], "p_holm_within_variable"] = multipletests(p[ok], method="holm")[1]
    out["significant_holm_0_05"] = out["p_holm_within_variable"] < 0.05
    return out


def write_method_note(path: Path, window: str, min_hours: int, n_hourly: int, n_daily: int) -> None:
    path.write_text(
        f"""Canopy2Ground — comparação estatística de microclima\n\n"
        f"Pastagem, INMET e ERA5-Land são pareados no mesmo horário local.\n"
        f"Janela: {'06:00–18:00' if window == 'light' else '24 horas'}; mínimo diário: {min_hours} horas comuns.\n"
        f"Horários comuns: {n_hourly}; dias incluídos: {n_daily}.\n\n"
        "Contrastes diários pareados: ERA5-FIELD, INMET-FIELD e ERA5-INMET.\n"
        "Inferência: GLSAR com resíduos AR(1); p-valores ajustados por Holm dentro de cada variável.\n"
        "Concordância: Pearson r, R², CCC de Lin, MAE, RMSE e viés.\n"
        "O pareamento Pastagem + ERA5-Land é também salvo separadamente para regressão e atualização dos modelos de harmonização, sem depender da disponibilidade do INMET.\n""",
        encoding="utf-8",
    )


def main() -> None:
    parser = argparse.ArgumentParser(description="Compara microclima de Pastagem, ERA5-Land e, quando disponível, INMET.")
    parser.add_argument("--root", default=".")
    parser.add_argument("--window", choices=["all", "light"], default="all")
    parser.add_argument("--min-hours", type=int, default=None)
    args = parser.parse_args()

    root = Path(args.root).resolve()
    proc = root / "data" / "processed" / "climate"
    outdir = root / "results" / "validation" / "climate" / "microclimate"
    outdir.mkdir(parents=True, exist_ok=True)
    min_hours = args.min_hours if args.min_hours is not None else (18 if args.window == "all" else 9)

    if not (proc / SOURCE_FILES["FIELD"]).exists() or not (proc / SOURCE_FILES["ERA5"]).exists():
        raise FileNotFoundError("Pastagem + ERA5-Land são necessários para a comparação atmosférica.")

    # Pairwise FIELD + ERA5: always produced and used by regression/harmonization.
    pair_hourly = build_hourly_common(root, args.window, ("FIELD", "ERA5"))
    pair_daily = build_daily_common(pair_hourly, min_hours)
    if pair_daily.empty:
        raise ValueError("Nenhum dia Pastagem + ERA5-Land atingiu o mínimo de horas comuns.")
    pair_hourly.to_csv(outdir / f"era5_field_common_hourly_{args.window}.csv", index=False, encoding="utf-8-sig")
    pair_daily.to_csv(outdir / f"era5_field_common_daily_{args.window}.csv", index=False, encoding="utf-8-sig")
    print(f"Pastagem + ERA5-Land: {len(pair_hourly):,} horas comuns; {len(pair_daily):,} dias.", flush=True)

    # Three-source outputs must belong to the current execution. Remove previous
    # products before deciding whether INMET is available, preventing a later
    # report from silently reusing stale statistics.
    tri_outputs = [
        outdir / f"microclimate_common_hourly_{args.window}.csv",
        outdir / f"microclimate_common_daily_{args.window}.csv",
        outdir / f"microclimate_source_comparison_{args.window}.csv",
        outdir / f"METHOD_microclimate_source_comparison_{args.window}.txt",
    ]
    for path in tri_outputs:
        if path.exists():
            path.unlink()

    # Three-source comparison is optional because INMET acquisition may be external/manual.
    if not (proc / SOURCE_FILES["INMET"]).exists():
        print("Pastagem + ERA5-Land + INMET: ignorada; INMET não disponível. Pareamento Pastagem + ERA5-Land foi preservado.", flush=True)
        return

    hourly = build_hourly_common(root, args.window, ("FIELD", "ERA5", "INMET"))
    daily = build_daily_common(hourly, min_hours)
    if daily.empty:
        print("Pastagem + ERA5-Land + INMET: nenhum dia atingiu o mínimo de horas comuns.", flush=True)
        return

    rows = []
    for variable in VARIABLES:
        rows.extend(analyze_variable(daily, variable))
    stats_df = add_holm_adjustment(pd.DataFrame(rows))
    stats_df.insert(1, "variable_label", stats_df["variable"].map({k: v["label"] for k, v in VARIABLES.items()}))
    stats_df.insert(2, "unit", stats_df["variable"].map({k: v["unit"] for k, v in VARIABLES.items()}))

    hourly.to_csv(outdir / f"microclimate_common_hourly_{args.window}.csv", index=False, encoding="utf-8-sig")
    daily.to_csv(outdir / f"microclimate_common_daily_{args.window}.csv", index=False, encoding="utf-8-sig")
    stats_df.to_csv(outdir / f"microclimate_source_comparison_{args.window}.csv", index=False, encoding="utf-8-sig")
    write_method_note(outdir / f"METHOD_microclimate_source_comparison_{args.window}.txt", args.window, min_hours, len(hourly), len(daily))
    print(f"Pastagem + ERA5-Land + INMET: {len(hourly):,} horas comuns; {len(daily):,} dias. GLSAR-AR(1)+Holm concluído.", flush=True)


if __name__ == "__main__":
    main()
