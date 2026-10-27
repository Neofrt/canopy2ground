#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from pathlib import Path

import numpy as np
import pandas as pd


def _pick(df: pd.DataFrame, names: list[str]) -> str:
    for name in names:
        if name in df.columns:
            return name
    raise ValueError(f"Nenhuma das colunas esperadas foi encontrada: {names}")


def _vpd(temp_c: pd.Series, rh_pct: pd.Series) -> pd.Series:
    es = 0.6108 * np.exp((17.27 * temp_c) / (temp_c + 237.3))
    return es * (1.0 - rh_pct / 100.0)


def load_models(path: Path) -> dict:
    if not path.exists():
        raise FileNotFoundError(
            f"Modelo atual não encontrado: {path}. "
            "Execute climate/fit_harmonization_models.py antes da aplicação."
        )
    cfg = json.loads(path.read_text(encoding="utf-8"))
    required = {"temperature", "rh", "vpd"}
    missing = required - set(cfg.get("variables", {}))
    if missing:
        raise ValueError(f"Modelos ausentes em {path}: {sorted(missing)}")
    return cfg


def build_daily_era5(hourly: pd.DataFrame, min_hours: int = 18) -> pd.DataFrame:
    x = hourly.copy()
    dt_col = _pick(x, ["datetime_local", "datetime", "time"])
    temp_col = _pick(x, ["temp_C", "era5_temp_C", "temperature_C"])
    rh_col = _pick(x, ["rh_pct", "era5_rh_pct", "relative_humidity_pct"])

    x[dt_col] = pd.to_datetime(x[dt_col], errors="coerce")
    x[temp_col] = pd.to_numeric(x[temp_col], errors="coerce")
    x[rh_col] = pd.to_numeric(x[rh_col], errors="coerce")
    x = x.dropna(subset=[dt_col, temp_col, rh_col]).copy()

    vpd_col = next((c for c in ["vpd_kPa", "era5_vpd_kPa"] if c in x.columns), None)
    if vpd_col is None:
        x["_vpd_kPa"] = _vpd(x[temp_col], x[rh_col])
        vpd_col = "_vpd_kPa"
    else:
        x[vpd_col] = pd.to_numeric(x[vpd_col], errors="coerce")

    x["date"] = x[dt_col].dt.floor("D")
    x["_valid"] = x[[temp_col, rh_col, vpd_col]].notna().all(axis=1)
    daily = (
        x.groupby("date", as_index=False)
        .agg(
            era5_temp_C_raw=(temp_col, "mean"),
            era5_rh_pct_raw=(rh_col, "mean"),
            era5_vpd_kPa_raw=(vpd_col, "mean"),
            n_hours=("_valid", "sum"),
        )
        .sort_values("date")
    )
    daily["use_for_harmonization"] = daily["n_hours"] >= int(min_hours)
    return daily


def apply_harmonization(daily: pd.DataFrame, models: dict) -> pd.DataFrame:
    out = daily.copy()
    vars_cfg = models["variables"]

    temp_cfg = vars_cfg["temperature"]
    if temp_cfg.get("operational_method", "raw") == "linear":
        out["temp_C_final"] = float(temp_cfg["intercept"]) + float(temp_cfg["slope"]) * out["era5_temp_C_raw"]
    else:
        out["temp_C_final"] = out["era5_temp_C_raw"]
    out["temp_C_harmonized"] = out["temp_C_final"]
    out["temp_method"] = temp_cfg.get("operational_method", "raw")

    rh = vars_cfg["rh"]
    if rh.get("operational_method", "linear") == "linear":
        out["rh_pct_harmonized"] = float(rh["intercept"]) + float(rh["slope"]) * out["era5_rh_pct_raw"]
    else:
        out["rh_pct_harmonized"] = out["era5_rh_pct_raw"]
    out["rh_pct_harmonized"] = out["rh_pct_harmonized"].clip(lower=rh.get("clip_min"), upper=rh.get("clip_max"))
    out["rh_method"] = rh.get("operational_method", "linear")

    vpd = vars_cfg["vpd"]
    if vpd.get("operational_method", "linear") == "linear":
        out["vpd_kPa_harmonized"] = float(vpd["intercept"]) + float(vpd["slope"]) * out["era5_vpd_kPa_raw"]
    else:
        out["vpd_kPa_harmonized"] = out["era5_vpd_kPa_raw"]
    if vpd.get("clip_min") is not None:
        out["vpd_kPa_harmonized"] = out["vpd_kPa_harmonized"].clip(lower=float(vpd["clip_min"]))
    if vpd.get("clip_max") is not None:
        out["vpd_kPa_harmonized"] = out["vpd_kPa_harmonized"].clip(upper=float(vpd["clip_max"]))
    out["vpd_method"] = vpd.get("operational_method", "linear")

    out["model_id"] = models.get("model_id", "unknown")
    out["model_generated_at_utc"] = models.get("generated_at_utc", "unknown")
    out["model_n_days"] = models.get("validation_design", {}).get("n_days", np.nan)
    out["reference_site"] = models.get("reference_site", "pasto")
    out["temporal_scale"] = models.get("temporal_scale", "daily_24h")

    bad = ~out["use_for_harmonization"].fillna(False)
    for col in ["temp_C_final", "temp_C_harmonized", "rh_pct_harmonized", "vpd_kPa_harmonized"]:
        out.loc[bad, col] = np.nan
    return out


def main() -> None:
    ap = argparse.ArgumentParser(description="Apply the current dynamically updated Canopy2Ground ERA5-Land harmonization model.")
    ap.add_argument("--root", default=".")
    ap.add_argument("--models", default="results/harmonization/current_model.json")
    ap.add_argument("--input", default="data/processed/climate/era5_land_hourly.csv")
    ap.add_argument("--output", default="data/processed/climate/climate_daily_harmonized.csv")
    ap.add_argument("--min-hours", type=int, default=18)
    args = ap.parse_args()

    root = Path(args.root).resolve()
    model_path = root / args.models
    input_path = root / args.input
    output_path = root / args.output

    if not input_path.exists():
        raise FileNotFoundError(f"ERA5-Land horário não encontrado: {input_path}")

    models = load_models(model_path)
    hourly = pd.read_csv(input_path, low_memory=False)
    daily = build_daily_era5(hourly, min_hours=args.min_hours)
    out = apply_harmonization(daily, models)

    output_path.parent.mkdir(parents=True, exist_ok=True)
    out.to_csv(output_path, index=False, encoding="utf-8-sig")

    print("Harmonização climática concluída.")
    print(f"Modelo atual: {models.get('model_id', 'unknown')}")
    print("Temperatura/RH/VPD: regressões lineares atualizadas com a série pareada disponível.")
    print(f"Dias ERA5: {len(out):,} | utilizáveis: {int(out['use_for_harmonization'].sum()):,}")
    print(f"Saída: {output_path}")


if __name__ == "__main__":
    main()
