from __future__ import annotations

import argparse
from pathlib import Path

import numpy as np
import pandas as pd


VARIABLES = {
    "temperature": {"label": "Temperatura do ar", "unit": "°C"},
    "rh": {"label": "Umidade relativa do ar", "unit": "%"},
    "vpd": {"label": "VPD", "unit": "kPa"},
}


def read_daily(path: Path) -> pd.DataFrame:
    if not path.exists():
        raise FileNotFoundError(f"Arquivo não encontrado: {path}")

    df = pd.read_csv(path, low_memory=False)

    required = [
        "date",
        "FIELD_temperature", "ERA5_temperature",
        "FIELD_rh", "ERA5_rh",
        "FIELD_vpd", "ERA5_vpd",
    ]
    missing = [c for c in required if c not in df.columns]
    if missing:
        raise ValueError(f"Colunas ausentes em {path}: {missing}")

    df["date"] = pd.to_datetime(df["date"], errors="coerce")
    df = df[df["date"].notna()].copy()

    for c in required[1:]:
        df[c] = pd.to_numeric(df[c], errors="coerce")

    return df.sort_values("date").reset_index(drop=True)


def vpd_from_t_rh(temp_c: np.ndarray, rh_pct: np.ndarray) -> np.ndarray:
    rh = np.clip(np.asarray(rh_pct, dtype=float), 0.0, 100.0)
    t = np.asarray(temp_c, dtype=float)
    es = 0.6108 * np.exp((17.27 * t) / (t + 237.3))
    return es * (1.0 - rh / 100.0)


def fit_linear(x: np.ndarray, y: np.ndarray) -> tuple[float, float]:
    x = np.asarray(x, dtype=float)
    y = np.asarray(y, dtype=float)
    ok = np.isfinite(x) & np.isfinite(y)
    x, y = x[ok], y[ok]

    if len(x) < 3 or np.nanstd(x) == 0:
        return float(np.nanmean(y)), 0.0

    slope, intercept = np.polyfit(x, y, 1)
    return float(intercept), float(slope)


def predict_linear(x: np.ndarray, intercept: float, slope: float) -> np.ndarray:
    return intercept + slope * np.asarray(x, dtype=float)


def fit_additive_bias(x: np.ndarray, y: np.ndarray) -> float:
    x = np.asarray(x, dtype=float)
    y = np.asarray(y, dtype=float)
    ok = np.isfinite(x) & np.isfinite(y)
    return float(np.nanmean(y[ok] - x[ok]))


def ccc(obs: np.ndarray, pred: np.ndarray) -> float:
    obs = np.asarray(obs, dtype=float)
    pred = np.asarray(pred, dtype=float)
    ok = np.isfinite(obs) & np.isfinite(pred)
    obs, pred = obs[ok], pred[ok]

    if len(obs) < 2:
        return np.nan

    mx, my = np.mean(obs), np.mean(pred)
    vx, vy = np.var(obs, ddof=1), np.var(pred, ddof=1)
    cov = np.cov(obs, pred, ddof=1)[0, 1]
    den = vx + vy + (mx - my) ** 2
    return float(2 * cov / den) if den != 0 else np.nan


def metrics(obs: np.ndarray, pred: np.ndarray) -> dict:
    obs = np.asarray(obs, dtype=float)
    pred = np.asarray(pred, dtype=float)
    ok = np.isfinite(obs) & np.isfinite(pred)
    obs, pred = obs[ok], pred[ok]

    if len(obs) == 0:
        return {
            "n": 0, "bias": np.nan, "mae": np.nan, "rmse": np.nan,
            "r": np.nan, "r2": np.nan, "ccc": np.nan,
        }

    err = pred - obs
    r = np.corrcoef(obs, pred)[0, 1] if len(obs) >= 3 and np.std(obs) > 0 and np.std(pred) > 0 else np.nan

    return {
        "n": len(obs),
        "bias": float(np.mean(err)),
        "mae": float(np.mean(np.abs(err))),
        "rmse": float(np.sqrt(np.mean(err ** 2))),
        "r": float(r) if np.isfinite(r) else np.nan,
        "r2": float(r ** 2) if np.isfinite(r) else np.nan,
        "ccc": ccc(obs, pred),
    }


def training_mask(dates: pd.Series, i: int, embargo_days: int) -> np.ndarray:
    target = dates.iloc[i]
    delta = (dates - target).abs().dt.days.to_numpy()
    return delta > embargo_days


def loeo_predictions(df: pd.DataFrame, embargo_days: int = 0) -> pd.DataFrame:
    """
    Leave-one-event-out com evento = dia.

    embargo_days=0:
        retira apenas o próprio dia.
    embargo_days=1:
        retira o dia e também ±1 dia do treinamento.
    """
    rows = []

    for i in range(len(df)):
        train = training_mask(df["date"], i, embargo_days)
        test = df.iloc[i]

        row = {
            "date": test["date"],
            "event_id": test["date"].strftime("%Y-%m-%d"),
            "embargo_days": embargo_days,
        }

        # Modelos independentes para T, RH e VPD
        for var in ["temperature", "rh", "vpd"]:
            x_all = df[f"ERA5_{var}"].to_numpy(dtype=float)
            y_all = df[f"FIELD_{var}"].to_numpy(dtype=float)

            x_train = x_all[train]
            y_train = y_all[train]
            x_test = float(test[f"ERA5_{var}"])
            y_test = float(test[f"FIELD_{var}"])

            row[f"{var}_obs_field"] = y_test
            row[f"{var}_era5_raw"] = x_test

            # Correção aditiva
            delta = fit_additive_bias(x_train, y_train)
            row[f"{var}_additive"] = x_test + delta

            # Calibração linear: FIELD = intercept + slope * ERA5
            intercept, slope = fit_linear(x_train, y_train)
            row[f"{var}_linear"] = intercept + slope * x_test

        # VPD fisicamente reconstruído a partir de T e RH harmonizados linearmente
        t_int, t_slope = fit_linear(
            df.loc[train, "ERA5_temperature"].to_numpy(dtype=float),
            df.loc[train, "FIELD_temperature"].to_numpy(dtype=float),
        )
        rh_int, rh_slope = fit_linear(
            df.loc[train, "ERA5_rh"].to_numpy(dtype=float),
            df.loc[train, "FIELD_rh"].to_numpy(dtype=float),
        )

        t_h = t_int + t_slope * float(test["ERA5_temperature"])
        rh_h = rh_int + rh_slope * float(test["ERA5_rh"])
        rh_h = float(np.clip(rh_h, 0.0, 100.0))

        row["temperature_for_vpd_physical"] = t_h
        row["rh_for_vpd_physical"] = rh_h
        row["vpd_physical"] = float(vpd_from_t_rh(np.array([t_h]), np.array([rh_h]))[0])

        rows.append(row)

    return pd.DataFrame(rows)


def evaluate_cv(pred: pd.DataFrame) -> pd.DataFrame:
    rows = []

    candidates = {
        "temperature": ["era5_raw", "additive", "linear"],
        "rh": ["era5_raw", "additive", "linear"],
        "vpd": ["era5_raw", "additive", "linear", "physical"],
    }

    for var, models in candidates.items():
        obs = pred[f"{var}_obs_field"].to_numpy(dtype=float)

        raw_metrics = None

        for model in models:
            pred_col = f"{var}_{model}"
            m = metrics(obs, pred[pred_col].to_numpy(dtype=float))

            if model == "era5_raw":
                raw_metrics = m.copy()

            row = {
                "variable": var,
                "variable_label": VARIABLES[var]["label"],
                "unit": VARIABLES[var]["unit"],
                "model": model,
                **m,
            }

            if raw_metrics is not None:
                row["delta_rmse_vs_raw"] = m["rmse"] - raw_metrics["rmse"]
                row["delta_mae_vs_raw"] = m["mae"] - raw_metrics["mae"]
                row["delta_ccc_vs_raw"] = m["ccc"] - raw_metrics["ccc"]
            else:
                row["delta_rmse_vs_raw"] = np.nan
                row["delta_mae_vs_raw"] = np.nan
                row["delta_ccc_vs_raw"] = np.nan

            rows.append(row)

    out = pd.DataFrame(rows)

    out["rank_rmse"] = (
        out.groupby("variable")["rmse"]
        .rank(method="min", ascending=True)
        .astype(int)
    )
    out["best_by_rmse"] = out["rank_rmse"] == 1

    return out.sort_values(["variable", "rank_rmse", "model"]).reset_index(drop=True)


def fit_full_models(df: pd.DataFrame) -> pd.DataFrame:
    rows = []

    for var in ["temperature", "rh", "vpd"]:
        x = df[f"ERA5_{var}"].to_numpy(dtype=float)
        y = df[f"FIELD_{var}"].to_numpy(dtype=float)

        additive = fit_additive_bias(x, y)
        intercept, slope = fit_linear(x, y)

        rows.append({
            "variable": var,
            "variable_label": VARIABLES[var]["label"],
            "unit": VARIABLES[var]["unit"],
            "model": "additive",
            "intercept": additive,
            "slope": 1.0,
            "equation": f"FIELD_hat = ERA5 + ({additive:.8f})",
        })

        rows.append({
            "variable": var,
            "variable_label": VARIABLES[var]["label"],
            "unit": VARIABLES[var]["unit"],
            "model": "linear",
            "intercept": intercept,
            "slope": slope,
            "equation": f"FIELD_hat = {intercept:.8f} + {slope:.8f} * ERA5",
        })

    return pd.DataFrame(rows)


def full_candidate_series(df: pd.DataFrame, models: pd.DataFrame) -> pd.DataFrame:
    out = df.copy()

    for var in ["temperature", "rh", "vpd"]:
        x = out[f"ERA5_{var}"].to_numpy(dtype=float)

        add = models[(models["variable"] == var) & (models["model"] == "additive")].iloc[0]
        lin = models[(models["variable"] == var) & (models["model"] == "linear")].iloc[0]

        out[f"ERA5_{var}_additive"] = x + float(add["intercept"])
        out[f"ERA5_{var}_linear"] = float(lin["intercept"]) + float(lin["slope"]) * x

    out["ERA5_rh_linear"] = out["ERA5_rh_linear"].clip(0, 100)

    out["ERA5_vpd_physical"] = vpd_from_t_rh(
        out["ERA5_temperature_linear"].to_numpy(dtype=float),
        out["ERA5_rh_linear"].to_numpy(dtype=float),
    )

    return out


def write_note(path: Path, embargo_days: int) -> None:
    txt = f"""Canopy2Ground — empirical ERA5 harmonization

Cross-validation design
-----------------------
Leave-one-event-out (LOEO), with one event defined as one daily observation.

Embargo:
{embargo_days} day(s).

If embargo_days = 0, only the target day is removed from model fitting.
If embargo_days = 1, the target day and the adjacent day before/after are excluded.

Candidate models
----------------
1. era5_raw
   No correction.

2. additive
   FIELD_hat = ERA5 + mean(FIELD - ERA5) estimated only from training days.

3. linear
   FIELD_hat = beta0 + beta1 * ERA5, estimated only from training days.

4. physical (VPD only)
   Temperature and RH are independently harmonized with linear models,
   then VPD is recomputed from harmonized T and RH.

Evaluation
----------
All metrics are calculated exclusively from held-out-day predictions:
bias, MAE, RMSE, Pearson r, R² and Lin's CCC.

The primary ranking is RMSE. CCC and bias should be inspected jointly.
The full-data coefficients are provided only after cross-validation and
must not be interpreted as cross-validated performance.

Terminology
-----------
"Calibration" = empirical statistical model fitted between ERA5-Land and field data.
"Harmonized series" = ERA5-Land series after application of the selected calibration.
"""
    path.write_text(txt, encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Calibração empírica ERA5 -> campo com leave-one-event-out diário."
    )
    parser.add_argument("--root", default=".", help="Raiz do projeto Canopy2Ground.")
    parser.add_argument(
        "--embargo-days",
        type=int,
        default=0,
        help="Dias adicionais excluídos ao redor do dia de teste. Padrão: 0.",
    )
    args = parser.parse_args()

    if args.embargo_days < 0:
        raise ValueError("--embargo-days deve ser >= 0")

    root = Path(args.root).resolve()
    input_path = (
        root / "results" / "climate_validation" / "microclimate_statistics"
        / "microclimate_common_daily_all.csv"
    )
    outdir = root / "results" / "harmonization"
    outdir.mkdir(parents=True, exist_ok=True)

    df = read_daily(input_path)
    pred = loeo_predictions(df, embargo_days=args.embargo_days)
    cv = evaluate_cv(pred)
    models = fit_full_models(df)
    candidates = full_candidate_series(df, models)

    pred.to_csv(
        outdir / "loeo_predictions_daily.csv",
        index=False,
        encoding="utf-8-sig",
    )
    cv.to_csv(
        outdir / "cross_validation_metrics.csv",
        index=False,
        encoding="utf-8-sig",
    )
    models.to_csv(
        outdir / "calibration_models_full.csv",
        index=False,
        encoding="utf-8-sig",
    )
    candidates.to_csv(
        outdir / "harmonized_daily_candidates.csv",
        index=False,
        encoding="utf-8-sig",
    )
    write_note(outdir / "METHOD_HARMONIZATION.txt", args.embargo_days)

    print("\nCANOPY2GROUND — EMPIRICAL HARMONIZATION")
    print(f"LOEO: 1 evento = 1 dia | embargo = {args.embargo_days} dia(s)")
    print(f"Dias avaliados: {len(pred)}")
    print("\nValidação cruzada:")
    cols = [
        "variable_label", "model", "n", "bias", "mae", "rmse",
        "r", "r2", "ccc", "delta_rmse_vs_raw", "delta_ccc_vs_raw",
        "rank_rmse", "best_by_rmse",
    ]
    with pd.option_context("display.max_columns", None, "display.width", 220):
        print(cv[cols].to_string(index=False))

    print(f"\nResultados salvos em: {outdir}")
    print("Arquivos principais:")
    print("  cross_validation_metrics.csv")
    print("  calibration_models_full.csv")
    print("  loeo_predictions_daily.csv")
    print("  harmonized_daily_candidates.csv")


if __name__ == "__main__":
    main()
