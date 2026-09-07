#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from pathlib import Path

import numpy as np
import pandas as pd


class DataIntegrityError(RuntimeError):
    """Raised when a merge key that must be unique contains duplicates."""


def hydro_date_from_datetime(s):
    dates = s.dt.normalize()
    after = (s.dt.hour > 12) | ((s.dt.hour == 12) & ((s.dt.minute > 0) | (s.dt.second > 0)))
    return (dates + pd.to_timedelta(after.astype(int), unit="D")).dt.date


def read_csv(path, dates=()):
    x = pd.read_csv(path)
    for c in dates:
        if c in x.columns:
            x[c] = pd.to_datetime(x[c], errors="coerce")
    return x


def assert_unique(df: pd.DataFrame, keys, dataset: str):
    keys = list(keys)
    missing = [k for k in keys if k not in df.columns]
    if missing:
        raise DataIntegrityError(f"{dataset}: chaves ausentes para validação: {missing}")
    dup = df[df.duplicated(keys, keep=False)]
    if not dup.empty:
        sample = dup[keys].drop_duplicates().head(10).to_dict("records")
        raise DataIntegrityError(
            f"{dataset}: foram encontradas chaves duplicadas em {keys}. "
            f"A integração foi interrompida para evitar multiplicação silenciosa de linhas. "
            f"Exemplos: {sample}"
        )


def micro_daily_integrated(micro30, min_light=20):
    m = micro30.copy()
    m["datetime"] = pd.to_datetime(m["datetime"])
    m["date"] = m["datetime"].dt.date
    m = m[(m["datetime"].dt.hour >= 6) & (m["datetime"].dt.hour < 18)].copy()

    p = m[m["site"] == "pasto"][["datetime", "temp_C", "rh_pct", "vpd_kPa", "par_umol"]].rename(
        columns={"temp_C": "temp_pasto", "rh_pct": "rh_pasto", "vpd_kPa": "vpd_pasto", "par_umol": "I0_par"}
    )
    assert_unique(p, ["datetime"], "microclima_pasto_30min")
    m = m.merge(p, on="datetime", how="left", validate="many_to_one")

    m["delta_temp_C"] = np.where(m["site"].eq("pasto"), 0, m["temp_C"] - m["temp_pasto"])
    m["delta_rh_pp"] = np.where(m["site"].eq("pasto"), 0, m["rh_pct"] - m["rh_pasto"])
    m["delta_vpd_kPa"] = np.where(m["site"].eq("pasto"), 0, m["vpd_kPa"] - m["vpd_pasto"])

    rows = []
    for (site, date), g in m.groupby(["site", "date"]):
        def mean_if(col):
            z = g[col].dropna()
            return z.mean() if len(z) >= min_light else np.nan

        n_rh = int(g["rh_pct"].notna().sum())
        n_sat = int((g["rh_pct"].notna() & (g["rh_pct"] >= 99.9)).sum())
        frac = n_sat / n_rh if n_rh else np.nan
        pair = g["par_umol"].notna() & g["I0_par"].notna() & (g["I0_par"] > 0)
        n_pair = int(pair.sum())
        sum_i = float(g.loc[pair, "par_umol"].sum()) if n_pair >= min_light else np.nan
        sum_i0 = float(g.loc[pair, "I0_par"].sum()) if n_pair >= min_light else np.nan
        trans = 1.0 if site == "pasto" else (sum_i / sum_i0 if np.isfinite(sum_i) and np.isfinite(sum_i0) and sum_i0 > 0 else np.nan)
        fc = 0.0 if site == "pasto" else (1 - trans if np.isfinite(trans) else np.nan)
        qa_fc = "referencia" if site == "pasto" else ("sem_dados" if pd.isna(fc) else ("fora_0_1" if fc < 0 or fc > 1 else "ok"))
        n_par = int(g["par_umol"].notna().sum())
        n_i0 = int(g["I0_par"].notna().sum())

        rows.append({
            "date": date,
            "site": site,
            "temp_luz_C": mean_if("temp_C"),
            "rh_luz_pct": mean_if("rh_pct"),
            "vpd_luz_kPa": mean_if("vpd_kPa"),
            "par_luz_umol": mean_if("par_umol"),
            "par_externo_luz_umol": mean_if("I0_par"),
            "dli_mol_m2": g["par_umol"].sum() * 1800 / 1e6 if n_par >= min_light else np.nan,
            "dli_external_mol_m2": g["I0_par"].sum() * 1800 / 1e6 if n_i0 >= min_light else np.nan,
            "delta_temp_C": mean_if("delta_temp_C"),
            "delta_rh_pp": mean_if("delta_rh_pp"),
            "delta_vpd_kPa": mean_if("delta_vpd_kPa"),
            "n_rh_luz": n_rh,
            "n_rh_saturado": n_sat,
            "fracao_rh_saturado": frac,
            # Saturação observada é descritiva; na floresta primária foi confirmada em campo.
            "rh_saturation_observed": bool(frac > 0.5) if not pd.isna(frac) else False,
            "n_par_pareado": n_pair,
            "soma_I": sum_i,
            "soma_I0": sum_i0,
            "transmittance_daily": trans,
            "fractional_cover_daily": fc,
            "qa_fc_daily": qa_fc,
        })

    out = pd.DataFrame(rows)
    if not out.empty:
        # Aliases mantidos por compatibilidade; não há mascaramento por saturação de RH.
        out["rh_luz_qc_pct"] = out["rh_luz_pct"]
        out["vpd_luz_qc_kPa"] = out["vpd_luz_kPa"]
        out["delta_rh_qc_pp"] = out["delta_rh_pp"]
        out["delta_vpd_qc_kPa"] = out["delta_vpd_kPa"]
        out["qa_rh_vpd"] = np.where(out["rh_luz_pct"].isna() & out["vpd_luz_kPa"].isna(), "sem_dados", "ok_observed_condition")
        assert_unique(out, ["date", "site"], "microclima_diario_integrado")
    return out


def canonical_local_rain(ra: pd.DataFrame, rext: pd.DataFrame) -> pd.DataFrame:
    """Build one local-rain row per date/site without allowing a transition-day cartesian merge."""
    non_pasto = ra[ra["site"] != "pasto"][["date", "site", "rain_mm", "coverage", "serial"]].copy()
    assert_unique(non_pasto, ["date", "site"], "precipitacao_local_cap_ref")
    non_pasto = non_pasto.rename(
        columns={"rain_mm": "rain_local_mm", "coverage": "rain_local_coverage", "serial": "rain_local_serial"}
    )

    pasto_cols = [c for c in ["date", "rain_ext_mm", "coverage", "serial"] if c in rext.columns]
    pasto = rext[pasto_cols].copy()
    pasto["site"] = "pasto"
    pasto = pasto.rename(
        columns={"rain_ext_mm": "rain_local_mm", "coverage": "rain_local_coverage", "serial": "rain_local_serial"}
    )
    assert_unique(pasto, ["date", "site"], "precipitacao_local_pasto_canonica")
    out = pd.concat([non_pasto, pasto], ignore_index=True, sort=False)
    assert_unique(out, ["date", "site"], "precipitacao_local_canonica")
    return out


def process(root: Path, config_path: Path):
    cfg = json.loads(config_path.read_text(encoding="utf-8"))
    min_light = int(cfg.get("light_period", {}).get("min_intervals_daily", 20))

    p_micro = root / "data" / "processed" / "microclima" / "microclima_30min_long.csv"
    p_microw = root / "data" / "processed" / "microclima" / "microclima_30min_wide.csv"
    p_tmsw = root / "data" / "processed" / "tms" / "tms_30min_wide.csv"
    p_tmsd = root / "data" / "processed" / "tms" / "tms_diario_hidrologico.csv"
    p_well30 = root / "data" / "processed" / "poco" / "pocos_30min.csv"
    p_welld = root / "data" / "processed" / "poco" / "pocos_diario_pressao_absoluta.csv"
    rain_dir = root / "data" / "processed" / "precipitacao"
    p_rain_all = rain_dir / "03_precipitacao_diaria_todos_sites.csv"
    p_rain_ext = rain_dir / "04_precipitacao_diaria_pasto_externo.csv"

    required = [p_micro, p_microw, p_tmsw, p_tmsd, p_rain_all, p_rain_ext]
    missing = [str(p) for p in required if not p.exists()]
    if missing:
        raise RuntimeError("Arquivos processados ausentes:\n" + "\n".join(missing))

    micro30 = read_csv(p_micro, ["datetime"])
    microw = read_csv(p_microw, ["datetime"])
    tmsw = read_csv(p_tmsw, ["datetime"])
    assert_unique(microw, ["datetime"], "microclima_30min_wide")
    assert_unique(tmsw, ["datetime"], "tms_30min_wide")
    integrated30 = microw.merge(tmsw, on="datetime", how="outer", validate="one_to_one")

    if p_well30.exists():
        w = read_csv(p_well30, ["datetime"])
        assert_unique(w, ["datetime", "site"], "pocos_30min")
        wp = w.pivot(index="datetime", columns="site", values=["pressure_abs_kPa", "temperature_C", "qa_review"])
        wp.columns = [f"{site}_well_{var}" for var, site in wp.columns]
        wp = wp.reset_index()
        assert_unique(wp, ["datetime"], "pocos_30min_wide")
        integrated30 = integrated30.merge(wp, on="datetime", how="outer", validate="one_to_one")

    integrated30 = integrated30.sort_values("datetime")
    integrated30["date"] = integrated30["datetime"].dt.date
    integrated30["hydro_date"] = hydro_date_from_datetime(integrated30["datetime"])
    integrated30["hora"] = integrated30["datetime"].dt.strftime("%H:%M")
    integrated30["periodo_luz"] = (integrated30["datetime"].dt.hour >= 6) & (integrated30["datetime"].dt.hour < 18)

    rext = pd.read_csv(p_rain_ext)
    rext["date"] = pd.to_datetime(rext["date"]).dt.date
    assert_unique(rext, ["date"], "precipitacao_pasto_externo")
    extcols = [c for c in [
        "date", "rain_ext_mm", "serial", "coverage", "status",
        "use_for_calibration_strict", "use_for_calibration_relaxed", "use_for_calibration"
    ] if c in rext.columns]
    rr = rext[extcols].rename(
        columns={"date": "hydro_date", "serial": "rain_ext_serial", "coverage": "rain_ext_coverage", "status": "rain_ext_status"}
    )
    assert_unique(rr, ["hydro_date"], "precipitacao_pasto_externo_hydrologic")
    integrated30 = integrated30.merge(rr, on="hydro_date", how="left", validate="many_to_one")

    microd = micro_daily_integrated(micro30, min_light=min_light)
    tmsd = pd.read_csv(p_tmsd)
    tmsd["date"] = pd.to_datetime(tmsd["date"]).dt.date
    assert_unique(tmsd, ["date", "site", "depth_cm"], "tms_diario_hidrologico")

    ra = pd.read_csv(p_rain_all)
    ra["date"] = pd.to_datetime(ra["date"]).dt.date
    rain_local = canonical_local_rain(ra, rext)

    rext2 = rext.rename(columns={"serial": "rain_ext_serial", "coverage": "rain_ext_coverage", "status": "rain_ext_status"})
    assert_unique(rext2, ["date"], "precipitacao_externa_diaria")

    daily = tmsd.merge(microd, on=["date", "site"], how="left", validate="many_to_one")
    daily = daily.merge(rain_local, on=["date", "site"], how="left", validate="many_to_one")
    daily = daily.merge(rext2, on="date", how="left", validate="many_to_one", suffixes=("", "_extdup"))

    if p_welld.exists():
        wd = pd.read_csv(p_welld)
        wd["date"] = pd.to_datetime(wd["date"]).dt.date
        wd = wd.drop(columns=["serial"], errors="ignore")
        assert_unique(wd, ["date", "site"], "pocos_diario")
        daily = daily.merge(wd, on=["date", "site"], how="left", validate="many_to_one")

    assert_unique(daily, ["date", "site", "depth_cm"], "metricas_diarias_integradas")
    daily = daily.sort_values(["date", "site", "depth_cm"])

    proc = root / "data" / "processed" / "integrated"
    res = root / "results" / "integrated"
    proc.mkdir(parents=True, exist_ok=True)
    res.mkdir(parents=True, exist_ok=True)

    integrated30.to_csv(proc / "dados_integrados_30min.csv", index=False, encoding="utf-8-sig")
    microd.to_csv(proc / "microclima_diario_integrado.csv", index=False, encoding="utf-8-sig")
    daily.to_csv(proc / "metricas_diarias_integradas.csv", index=False, encoding="utf-8-sig")

    qa = pd.DataFrame([
        {
            "dataset": "integrated_30min",
            "n_rows": len(integrated30),
            "start": integrated30["datetime"].min(),
            "end": integrated30["datetime"].max(),
            "unique_key": "datetime",
            "duplicate_keys": int(integrated30.duplicated(["datetime"]).sum()),
        },
        {
            "dataset": "daily_integrated",
            "n_rows": len(daily),
            "start": daily["date"].min(),
            "end": daily["date"].max(),
            "unique_key": "date+site+depth_cm",
            "duplicate_keys": int(daily.duplicated(["date", "site", "depth_cm"]).sum()),
        },
    ])
    qa.to_csv(res / "resumo_integracao.csv", index=False, encoding="utf-8-sig")
    return {"integrated30": integrated30, "daily": daily, "micro_daily": microd}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--root", required=True)
    ap.add_argument("--config", required=True)
    args = ap.parse_args()
    r = process(Path(args.root), Path(args.config))
    print(f"Integração: {len(r['integrated30']):,} linhas de 30 min; {len(r['daily']):,} linhas diárias site-profundidade.")


if __name__ == "__main__":
    main()
