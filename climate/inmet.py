from __future__ import annotations

from pathlib import Path
import pandas as pd
import numpy as np

from .common import hydrologic_date, to_numeric_series, vpd_from_temp_rh


def _read_inmet(path: Path) -> pd.DataFrame:
    # INMET exports commonly use semicolon delimiters and decimal comma.
    return pd.read_csv(path, sep=';', encoding='utf-8-sig', dtype='string', low_memory=False)


def normalize_inmet(path: Path, cfg: dict, project_timezone: str) -> tuple[pd.DataFrame, pd.DataFrame]:
    raw = _read_inmet(path)
    cc = cfg.get('columns', {})
    date_col = cc.get('date', 'Data')
    hour_col = cc.get('hour_utc', 'Hora (UTC)')
    required = [date_col, hour_col]
    missing = [c for c in required if c not in raw.columns]
    if missing:
        raise ValueError(f'INMET: colunas obrigatórias ausentes: {missing}. Encontradas: {list(raw.columns)}')

    hour = raw[hour_col].fillna('').str.replace(r'\D', '', regex=True).str.zfill(4)
    stamp = raw[date_col].fillna('') + ' ' + hour.str[:2] + ':' + hour.str[2:4]
    dt_utc = pd.to_datetime(stamp, format='%d/%m/%Y %H:%M', errors='coerce', utc=True)
    dt_local = dt_utc.dt.tz_convert(project_timezone)

    out = pd.DataFrame({
        'datetime_utc': dt_utc,
        'datetime_local': dt_local.dt.tz_localize(None),
    })
    mapping = {
        'temp_C': cc.get('temp_C', 'Temp. Ins. (C)'),
        'rh_pct': cc.get('rh_pct', 'Umi. Ins. (%)'),
        'dewpoint_C': cc.get('dewpoint_C', 'Pto Orvalho Ins. (C)'),
        'pressure_hPa': cc.get('pressure_hPa', 'Pressao Ins. (hPa)'),
        'wind_ms': cc.get('wind_ms', 'Vel. Vento (m/s)'),
        'radiation_kj_m2': cc.get('radiation_kj_m2', 'Radiacao (KJ/m²)'),
        'rain_mm': cc.get('rain_mm', 'Chuva (mm)'),
    }
    for new, old in mapping.items():
        out[new] = to_numeric_series(raw[old]) if old in raw.columns else np.nan
    out['vpd_kPa'] = vpd_from_temp_rh(out['temp_C'], out['rh_pct'])
    out['radiation_mj_m2'] = out['radiation_kj_m2'] / 1000.0
    out = out[out['datetime_utc'].notna()].sort_values('datetime_utc').drop_duplicates('datetime_utc', keep='last')

    daily_frames = []
    for window in ['utc_calendar','local_calendar','hydrologic_12_12_local']:
        z = out.copy()
        if window == 'utc_calendar':
            z['date'] = z['datetime_utc'].dt.tz_localize(None).dt.date
        elif window == 'local_calendar':
            z['date'] = z['datetime_local'].dt.date
        else:
            z['date'] = hydrologic_date(z['datetime_local'], 12)
        d = z.groupby('date', as_index=False).agg(
            inmet_rain_mm=('rain_mm', lambda q: q.sum(min_count=1)),
            inmet_temp_C=('temp_C','mean'),
            inmet_rh_pct=('rh_pct','mean'),
            inmet_vpd_kPa=('vpd_kPa','mean'),
            inmet_dewpoint_C=('dewpoint_C','mean'),
            inmet_pressure_hPa=('pressure_hPa','mean'),
            inmet_radiation_mj_m2=('radiation_mj_m2', lambda q: q.sum(min_count=1)),
            n_inmet_hourly=('datetime_utc','count'),
            n_inmet_rain=('rain_mm','count'),
        )
        d['inmet_rain_coverage'] = d['n_inmet_rain'] / 24.0
        d['window'] = window
        daily_frames.append(d)
    daily = pd.concat(daily_frames, ignore_index=True)
    return out, daily
