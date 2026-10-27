from __future__ import annotations

import json
from pathlib import Path
import numpy as np
import pandas as pd


def load_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding='utf-8'))


def ensure_parent(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)


def to_numeric_series(s: pd.Series) -> pd.Series:
    if s.dtype == object or pd.api.types.is_string_dtype(s):
        s = s.astype('string').str.replace(',', '.', regex=False)
    return pd.to_numeric(s, errors='coerce')


def saturation_vapor_pressure_kpa(temp_c):
    t = np.asarray(temp_c, dtype=float)
    return 0.6108 * np.exp((17.27 * t) / (t + 237.3))


def vpd_from_temp_rh(temp_c, rh_pct):
    es = saturation_vapor_pressure_kpa(temp_c)
    rh = np.asarray(rh_pct, dtype=float)
    return es * (1 - rh / 100.0)


def rh_from_temp_dewpoint(temp_c, dewpoint_c):
    es_t = saturation_vapor_pressure_kpa(temp_c)
    es_td = saturation_vapor_pressure_kpa(dewpoint_c)
    out = 100.0 * es_td / es_t
    return np.clip(out, 0, 100)


def vpd_from_temp_dewpoint(temp_c, dewpoint_c):
    return saturation_vapor_pressure_kpa(temp_c) - saturation_vapor_pressure_kpa(dewpoint_c)


def hydrologic_date(dt: pd.Series, closing_hour: int = 12) -> pd.Series:
    """12:00 belongs to the day ending at 12:00; times after 12:00 belong to the next hydrologic day."""
    x = pd.to_datetime(dt, errors='coerce')
    shifted = x - pd.to_timedelta(closing_hour, unit='h') - pd.to_timedelta(1, unit='s')
    return (shifted.dt.normalize() + pd.to_timedelta(1, unit='D')).dt.date


def regression_metrics(obs, pred) -> dict:
    obs = np.asarray(obs, dtype=float)
    pred = np.asarray(pred, dtype=float)
    ok = np.isfinite(obs) & np.isfinite(pred)
    obs = obs[ok]
    pred = pred[ok]
    n = len(obs)
    out = {
        'n': n,
        'obs_sum': float(np.sum(obs)) if n else np.nan,
        'pred_sum': float(np.sum(pred)) if n else np.nan,
        'bias_mean': np.nan,
        'MAE': np.nan,
        'RMSE': np.nan,
        'PBIAS': np.nan,
        'r': np.nan,
        'R2': np.nan,
        'NSE': np.nan,
        'KGE': np.nan,
        'slope': np.nan,
        'intercept': np.nan,
    }
    if n == 0:
        return out
    err = pred - obs
    out['bias_mean'] = float(np.mean(err))
    out['MAE'] = float(np.mean(np.abs(err)))
    out['RMSE'] = float(np.sqrt(np.mean(err**2)))
    if np.sum(obs) != 0:
        out['PBIAS'] = float(100 * np.sum(err) / np.sum(obs))
    if n >= 2 and np.std(obs, ddof=1) > 0 and np.std(pred, ddof=1) > 0:
        r = float(np.corrcoef(obs, pred)[0, 1])
        out['r'] = r
        out['R2'] = r**2
        slope, intercept = np.polyfit(obs, pred, 1)
        out['slope'] = float(slope)
        out['intercept'] = float(intercept)
        denom = np.sum((obs - np.mean(obs))**2)
        if denom > 0:
            out['NSE'] = float(1 - np.sum((pred - obs)**2) / denom)
        alpha = np.std(pred, ddof=1) / np.std(obs, ddof=1)
        beta = np.mean(pred) / np.mean(obs) if np.mean(obs) != 0 else np.nan
        if np.isfinite(beta):
            out['KGE'] = float(1 - np.sqrt((r - 1)**2 + (alpha - 1)**2 + (beta - 1)**2))
    return out


def event_metrics(obs, pred, threshold_mm: float) -> dict:
    obs = np.asarray(obs, dtype=float)
    pred = np.asarray(pred, dtype=float)
    ok = np.isfinite(obs) & np.isfinite(pred)
    obs = obs[ok] >= threshold_mm
    pred = pred[ok] >= threshold_mm
    hits = int(np.sum(obs & pred))
    misses = int(np.sum(obs & ~pred))
    false = int(np.sum(~obs & pred))
    correct_dry = int(np.sum(~obs & ~pred))
    pod = hits / (hits + misses) if hits + misses else np.nan
    far = false / (hits + false) if hits + false else np.nan
    csi = hits / (hits + misses + false) if hits + misses + false else np.nan
    return {
        'threshold_mm': threshold_mm,
        'hits': hits,
        'misses': misses,
        'false_alarms': false,
        'correct_dry': correct_dry,
        'POD': pod,
        'FAR': far,
        'CSI': csi,
    }
