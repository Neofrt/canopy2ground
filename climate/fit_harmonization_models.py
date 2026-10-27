from __future__ import annotations

import argparse
import hashlib
import json
from datetime import datetime, timezone
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
    df = df.dropna(subset=required[1:]).sort_values("date").reset_index(drop=True)
    if len(df) < 4:
        raise ValueError("São necessários pelo menos 4 dias pareados Pastagem + ERA5-Land para ajustar e validar os modelos.")
    return df


def load_policy(path: Path) -> dict:
    if not path.exists():
        raise FileNotFoundError(f"Política de harmonização não encontrada: {path}")
    cfg = json.loads(path.read_text(encoding="utf-8"))
    methods = cfg.get("operational_methods", {})
    missing = {"temperature", "rh", "vpd"} - set(methods)
    if missing:
        raise ValueError(f"Métodos operacionais ausentes na política: {sorted(missing)}")
    return cfg


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
        return {"n": 0, "bias": np.nan, "mae": np.nan, "rmse": np.nan, "r": np.nan, "r2": np.nan, "ccc": np.nan}
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


def loeo_predictions(df: pd.DataFrame, embargo_days: int = 1) -> pd.DataFrame:
    rows = []
    for i in range(len(df)):
        train = training_mask(df["date"], i, embargo_days)
        test = df.iloc[i]
        row = {"date": test["date"], "event_id": test["date"].strftime("%Y-%m-%d"), "embargo_days": embargo_days}
        for var in ["temperature", "rh", "vpd"]:
            x_all = df[f"ERA5_{var}"].to_numpy(dtype=float)
            y_all = df[f"FIELD_{var}"].to_numpy(dtype=float)
            x_train, y_train = x_all[train], y_all[train]
            x_test, y_test = float(test[f"ERA5_{var}"]), float(test[f"FIELD_{var}"])
            row[f"{var}_obs_field"] = y_test
            row[f"{var}_era5_raw"] = x_test
            delta = fit_additive_bias(x_train, y_train)
            row[f"{var}_additive"] = x_test + delta
            intercept, slope = fit_linear(x_train, y_train)
            row[f"{var}_linear"] = intercept + slope * x_test
        t_int, t_slope = fit_linear(df.loc[train, "ERA5_temperature"].to_numpy(float), df.loc[train, "FIELD_temperature"].to_numpy(float))
        rh_int, rh_slope = fit_linear(df.loc[train, "ERA5_rh"].to_numpy(float), df.loc[train, "FIELD_rh"].to_numpy(float))
        t_h = t_int + t_slope * float(test["ERA5_temperature"])
        rh_h = float(np.clip(rh_int + rh_slope * float(test["ERA5_rh"]), 0.0, 100.0))
        row["temperature_for_vpd_physical"] = t_h
        row["rh_for_vpd_physical"] = rh_h
        row["vpd_physical"] = float(vpd_from_t_rh(np.array([t_h]), np.array([rh_h]))[0])
        rows.append(row)
    return pd.DataFrame(rows)


def evaluate_cv(pred: pd.DataFrame) -> pd.DataFrame:
    candidates = {
        "temperature": ["era5_raw", "additive", "linear"],
        "rh": ["era5_raw", "additive", "linear"],
        "vpd": ["era5_raw", "additive", "linear", "physical"],
    }
    rows = []
    for var, models in candidates.items():
        obs = pred[f"{var}_obs_field"].to_numpy(dtype=float)
        raw_metrics = None
        for model in models:
            m = metrics(obs, pred[f"{var}_{model}"].to_numpy(dtype=float))
            if model == "era5_raw":
                raw_metrics = m.copy()
            rows.append({
                "variable": var,
                "variable_label": VARIABLES[var]["label"],
                "unit": VARIABLES[var]["unit"],
                "model": model,
                **m,
                "delta_rmse_vs_raw": m["rmse"] - raw_metrics["rmse"] if raw_metrics else np.nan,
                "delta_mae_vs_raw": m["mae"] - raw_metrics["mae"] if raw_metrics else np.nan,
                "delta_ccc_vs_raw": m["ccc"] - raw_metrics["ccc"] if raw_metrics else np.nan,
            })
    out = pd.DataFrame(rows)
    out["rank_rmse"] = out.groupby("variable")["rmse"].rank(method="min", ascending=True).astype(int)
    out["best_by_rmse"] = out["rank_rmse"] == 1
    return out.sort_values(["variable", "rank_rmse", "model"]).reset_index(drop=True)


def fit_full_models(df: pd.DataFrame) -> pd.DataFrame:
    rows = []
    for var in ["temperature", "rh", "vpd"]:
        x = df[f"ERA5_{var}"].to_numpy(dtype=float)
        y = df[f"FIELD_{var}"].to_numpy(dtype=float)
        additive = fit_additive_bias(x, y)
        intercept, slope = fit_linear(x, y)
        fit_r2 = metrics(y, intercept + slope * x)["r2"]
        rows.extend([
            {"variable": var, "variable_label": VARIABLES[var]["label"], "unit": VARIABLES[var]["unit"], "model": "additive", "intercept": additive, "slope": 1.0, "fit_R2": metrics(y, x + additive)["r2"], "equation": f"FIELD_hat = ERA5 + ({additive:.8f})"},
            {"variable": var, "variable_label": VARIABLES[var]["label"], "unit": VARIABLES[var]["unit"], "model": "linear", "intercept": intercept, "slope": slope, "fit_R2": fit_r2, "equation": f"FIELD_hat = {intercept:.8f} + {slope:.8f} * ERA5"},
        ])
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
    out["ERA5_vpd_physical"] = vpd_from_t_rh(out["ERA5_temperature_linear"].to_numpy(float), out["ERA5_rh_linear"].to_numpy(float))
    return out


def data_fingerprint(df: pd.DataFrame) -> str:
    cols = ["date", "FIELD_temperature", "ERA5_temperature", "FIELD_rh", "ERA5_rh", "FIELD_vpd", "ERA5_vpd"]
    payload = df[cols].to_csv(index=False, date_format="%Y-%m-%d", float_format="%.10g").encode("utf-8")
    return hashlib.sha256(payload).hexdigest()[:12]


def _metric_row(cv: pd.DataFrame, var: str, model: str) -> dict:
    z = cv[(cv["variable"] == var) & (cv["model"] == model)]
    if z.empty:
        return {}
    return z.iloc[0].to_dict()


def build_current_model(df: pd.DataFrame, cv: pd.DataFrame, models: pd.DataFrame, policy: dict, embargo_days: int) -> dict:
    methods = policy["operational_methods"]
    bounds = policy.get("bounds", {})
    fp = data_fingerprint(df)
    start = df["date"].min().date().isoformat()
    end = df["date"].max().date().isoformat()
    method_payload = json.dumps(methods, sort_keys=True, separators=(",", ":")).encode("utf-8")
    method_fp = hashlib.sha256(method_payload).hexdigest()[:8]
    model_id = f"pasto_{start}_{end}_n{len(df)}_data{fp}_policy{method_fp}"
    out = {
        "schema_version": 3,
        "model_id": model_id,
        "generated_at_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "update_mode": "cumulative_refit_each_pipeline_run",
        "reference_site": policy.get("reference_site", "pasto"),
        "temporal_scale": policy.get("temporal_scale", "daily_24h"),
        "operational_methods": methods,
        "validation_design": {
            "method": "leave-one-day-out",
            "embargo_days": embargo_days,
            "n_days": int(len(df)),
            "period_start": start,
            "period_end": end,
            "primary_ranking": policy.get("validation", {}).get("primary_ranking", "RMSE"),
            "secondary_metrics": policy.get("validation", {}).get("secondary_metrics", ["CCC", "bias", "MAE", "R2"]),
        },
        "variables": {},
        "notes": [
            "Coefficients are refitted cumulatively from all currently available paired Pasture + ERA5-Land daily observations.",
            "The operational method is versioned separately from the coefficients; new data update coefficients without silently changing the selected method family.",
            "Raw ERA5-Land variables are always retained alongside harmonized variables.",
        ],
    }
    for var in ["temperature", "rh", "vpd"]:
        lin = models[(models["variable"] == var) & (models["model"] == "linear")].iloc[0]
        raw_cv = _metric_row(cv, var, "era5_raw")
        lin_cv = _metric_row(cv, var, "linear")
        v = {
            "operational_method": methods[var],
            "source": "ERA5-Land",
            "diagnostic_linear_model": {
                "intercept": float(lin["intercept"]),
                "slope": float(lin["slope"]),
                "fit_R2": float(lin["fit_R2"]),
            },
            "cross_validation": {
                "raw_RMSE": float(raw_cv.get("rmse", np.nan)),
                "linear_RMSE": float(lin_cv.get("rmse", np.nan)),
                "raw_CCC": float(raw_cv.get("ccc", np.nan)),
                "linear_CCC": float(lin_cv.get("ccc", np.nan)),
                "raw_bias": float(raw_cv.get("bias", np.nan)),
                "linear_bias": float(lin_cv.get("bias", np.nan)),
            },
        }
        if methods[var] == "linear":
            v["intercept"] = float(lin["intercept"])
            v["slope"] = float(lin["slope"])
        if var in bounds:
            if "min" in bounds[var]:
                v["clip_min"] = float(bounds[var]["min"])
            if "max" in bounds[var]:
                v["clip_max"] = float(bounds[var]["max"])
        out["variables"][var] = v
    return out


def update_history(path: Path, model: dict) -> None:
    rows = []
    vd = model["validation_design"]
    for var, cfg in model["variables"].items():
        diag = cfg.get("diagnostic_linear_model", {})
        cv = cfg.get("cross_validation", {})
        rows.append({
            "model_id": model["model_id"],
            "generated_at_utc": model["generated_at_utc"],
            "period_start": vd["period_start"],
            "period_end": vd["period_end"],
            "n_days": vd["n_days"],
            "embargo_days": vd["embargo_days"],
            "variable": var,
            "operational_method": cfg["operational_method"],
            "intercept": cfg.get("intercept", np.nan),
            "slope": cfg.get("slope", np.nan),
            "diagnostic_intercept": diag.get("intercept", np.nan),
            "diagnostic_slope": diag.get("slope", np.nan),
            "fit_R2": diag.get("fit_R2", np.nan),
            "raw_RMSE": cv.get("raw_RMSE", np.nan),
            "linear_RMSE": cv.get("linear_RMSE", np.nan),
            "raw_CCC": cv.get("raw_CCC", np.nan),
            "linear_CCC": cv.get("linear_CCC", np.nan),
        })
    new = pd.DataFrame(rows)
    if path.exists():
        old = pd.read_csv(path, low_memory=False)
        if "model_id" in old.columns and model["model_id"] in set(old["model_id"].astype(str)):
            return
        new = pd.concat([old, new], ignore_index=True)
    path.parent.mkdir(parents=True, exist_ok=True)
    new.to_csv(path, index=False, encoding="utf-8-sig")


def write_note(path: Path, embargo_days: int) -> None:
    txt = f"""Canopy2Ground — empirical ERA5 harmonization

Update policy
-------------
The model is cumulative and is refitted on each pipeline run when paired Pasture + ERA5-Land daily observations are available.
The method family is versioned, while coefficients are allowed to evolve as the monitoring series grows.

Cross-validation
----------------
Leave-one-day-out with a {embargo_days}-day temporal embargo around the held-out day.
Candidate diagnostics: raw ERA5, additive correction, linear regression and, for VPD, physical reconstruction from harmonized T and RH.
Operational policy currently uses dynamically refitted linear models for temperature, RH and VPD.
Performance metrics are calculated only from held-out predictions; full-data coefficients are estimated after cross-validation.
"""
    path.write_text(txt, encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser(description="Atualiza cumulativamente os modelos ERA5-Land -> Pastagem.")
    parser.add_argument("--root", default=".")
    parser.add_argument("--policy", default="config/harmonization_policy.json")
    parser.add_argument("--input", default="results/validation/climate/microclimate/era5_field_common_daily_all.csv")
    parser.add_argument("--embargo-days", type=int, default=None)
    args = parser.parse_args()
    root = Path(args.root).resolve()
    policy = load_policy(root / args.policy)
    embargo_days = args.embargo_days
    if embargo_days is None:
        embargo_days = int(policy.get("validation", {}).get("embargo_days", 1))
    if embargo_days < 0:
        raise ValueError("--embargo-days deve ser >= 0")

    input_path = root / args.input
    if not input_path.exists():
        legacy = root / "results/validation/climate/microclimate/microclimate_common_daily_all.csv"
        if legacy.exists():
            input_path = legacy
    outdir = root / "results" / "harmonization"
    outdir.mkdir(parents=True, exist_ok=True)

    df = read_daily(input_path)
    pred = loeo_predictions(df, embargo_days=embargo_days)
    cv = evaluate_cv(pred)
    models = fit_full_models(df)
    candidates = full_candidate_series(df, models)
    current = build_current_model(df, cv, models, policy, embargo_days)

    pred.to_csv(outdir / "loeo_predictions_daily.csv", index=False, encoding="utf-8-sig")
    cv.to_csv(outdir / "cross_validation_metrics.csv", index=False, encoding="utf-8-sig")
    models.to_csv(outdir / "calibration_models_full.csv", index=False, encoding="utf-8-sig")
    candidates.to_csv(outdir / "harmonized_daily_candidates.csv", index=False, encoding="utf-8-sig")
    (outdir / "current_model.json").write_text(json.dumps(current, ensure_ascii=False, indent=2), encoding="utf-8")
    update_history(root / policy.get("history", {}).get("file", "results/harmonization/model_history.csv"), current)
    write_note(outdir / "METHOD_HARMONIZATION.txt", embargo_days)

    print("\nCANOPY2GROUND — DYNAMIC HARMONIZATION UPDATE")
    print(f"Modelo atual: {current['model_id']}")
    print(f"Dias pareados: {len(df)} | período: {current['validation_design']['period_start']} a {current['validation_design']['period_end']}")
    print(f"Validação: leave-one-day-out | embargo = {embargo_days} dia(s)")
    for var in ["temperature", "rh", "vpd"]:
        cfg = current["variables"][var]
        diag = cfg["diagnostic_linear_model"]
        if cfg["operational_method"] == "linear":
            print(f"{var}: linear atualizado -> intercept={cfg['intercept']:.8f}; slope={cfg['slope']:.8f}; R²={diag['fit_R2']:.3f}")
        else:
            print(f"{var}: método operacional={cfg['operational_method']} | regressão diagnóstica R²={diag['fit_R2']:.3f}")
    print(f"Saídas: {outdir}")


if __name__ == "__main__":
    main()
