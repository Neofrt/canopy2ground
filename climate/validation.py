from __future__ import annotations

import numpy as np
import pandas as pd

from .common import regression_metrics, event_metrics


def _compare_daily(field: pd.DataFrame, product: pd.DataFrame, pred_col: str, source: str, window: str, shifts: list[int], threshold: float):
    rows, events, pairs = [], [], []
    base = field[['date', 'field_rain_mm']].copy()
    base['date'] = pd.to_datetime(base['date'])
    meta = [c for c in ['chirps_release', 'chirps_lat_grid', 'chirps_lon_grid'] if c in product.columns]
    p = product[['date', pred_col] + meta].dropna(subset=['date']).copy()
    p['date'] = pd.to_datetime(p['date'])
    for shift in shifts:
        z = p.copy()
        z['date'] = z['date'] + pd.to_timedelta(shift, unit='D')
        m = base.merge(z, on='date', how='inner').dropna(subset=['field_rain_mm', pred_col])
        met = regression_metrics(m['field_rain_mm'], m[pred_col])
        met.update({'source': source, 'window': window, 'shift_days': shift})
        rows.append(met)
        ev = event_metrics(m['field_rain_mm'], m[pred_col], threshold)
        ev.update({'source': source, 'window': window, 'shift_days': shift})
        events.append(ev)
        mm = m.copy()
        mm['source'] = source
        mm['window'] = window
        mm['shift_days'] = shift
        mm = mm.rename(columns={pred_col: 'product_rain_mm'})
        pairs.append(mm)
    return rows, events, pairs


def validate_precipitation(field_daily: pd.DataFrame, inmet_daily: pd.DataFrame, era5_daily: pd.DataFrame, chirps: dict[str, pd.DataFrame], cfg: dict):
    shifts = list(map(int, cfg.get('shifts_days', [-1, 0, 1])))
    thr = float(cfg.get('rain_event_threshold_mm', 0.2))
    metrics, events, pairs = [], [], []
    if not inmet_daily.empty:
        for window, g in inmet_daily.groupby('window'):
            r, e, p = _compare_daily(field_daily, g, 'inmet_rain_mm', 'INMET', window, shifts, thr)
            metrics += r; events += e; pairs += p
    if not era5_daily.empty:
        pred = next((c for c in ['era5_precip_mm', 'era5_precip_m'] if c in era5_daily.columns), None)
        if pred:
            for window, g in era5_daily.groupby('window'):
                gg = g.copy()
                if pred == 'era5_precip_m':
                    gg['era5_precip_mm'] = pd.to_numeric(gg[pred], errors='coerce') * 1000
                    col = 'era5_precip_mm'
                else:
                    col = pred
                r, e, p = _compare_daily(field_daily, gg, col, 'ERA5-Land', window, shifts, thr)
                metrics += r; events += e; pairs += p
    for product, df in chirps.items():
        col = f'chirps_{product}_mm'
        if not df.empty and col in df:
            r, e, p = _compare_daily(field_daily, df, col, f'CHIRPS-v3-{product.upper()}', 'nominal_daily', shifts, thr)
            metrics += r; events += e; pairs += p
    return pd.DataFrame(metrics), pd.DataFrame(events), pd.concat(pairs, ignore_index=True) if pairs else pd.DataFrame()


def validate_hourly_micro(field_hourly: pd.DataFrame, inmet_hourly: pd.DataFrame, era5_hourly: pd.DataFrame):
    rows = []
    f = field_hourly.copy()
    f['datetime_local'] = pd.to_datetime(f['datetime_local'])
    for name, src in [('INMET', inmet_hourly), ('ERA5-Land', era5_hourly)]:
        if src.empty:
            continue
        s = src.copy()
        s['datetime_local'] = pd.to_datetime(s['datetime_local'])
        m = f.merge(s, on='datetime_local', how='inner', suffixes=('', '_product'))
        for field_col, product_candidates, var in [
            ('field_temp_C', ['temp_C', 'era5_temp_C'], 'temperature_C'),
            ('field_rh_pct', ['rh_pct', 'era5_rh_pct'], 'relative_humidity_pct'),
            ('field_vpd_kPa', ['vpd_kPa', 'era5_vpd_kPa'], 'vpd_kPa'),
        ]:
            pc = next((c for c in product_candidates if c in m.columns), None)
            if field_col in m and pc:
                met = regression_metrics(m[field_col], m[pc])
                met.update({'source': name, 'variable': var})
                rows.append(met)
    return pd.DataFrame(rows)


def validate_hourly_soil(field_soil_hourly: pd.DataFrame, era5_hourly: pd.DataFrame):
    if field_soil_hourly.empty or era5_hourly.empty:
        return pd.DataFrame()
    f = field_soil_hourly.copy(); f['datetime_local'] = pd.to_datetime(f['datetime_local'])
    e = era5_hourly.copy(); e['datetime_local'] = pd.to_datetime(e['datetime_local'])
    m = f.merge(e, on='datetime_local', how='inner')
    rows = []
    comparisons = [
        ('field_vwc_15cm_m3m3', 'soil_water_l2_m3m3', 'VWC', '15cm', 'ERA5_layer2_7_28cm', 'primary'),
        ('field_vwc_50cm_m3m3', 'soil_water_l3_m3m3', 'VWC', '50cm', 'ERA5_layer3_28_100cm', 'primary'),
        ('field_vwc_100cm_m3m3', 'soil_water_l3_m3m3', 'VWC', '100cm', 'ERA5_layer3_28_100cm', 'boundary_sensitivity'),
        ('field_vwc_100cm_m3m3', 'soil_water_l4_m3m3', 'VWC', '100cm', 'ERA5_layer4_100_289cm', 'boundary_sensitivity'),
        ('field_soil_temp_15cm_C', 'soil_temp_l2_C', 'soil_temperature_C', '15cm', 'ERA5_layer2_7_28cm', 'primary'),
        ('field_soil_temp_50cm_C', 'soil_temp_l3_C', 'soil_temperature_C', '50cm', 'ERA5_layer3_28_100cm', 'primary'),
        ('field_soil_temp_100cm_C', 'soil_temp_l3_C', 'soil_temperature_C', '100cm', 'ERA5_layer3_28_100cm', 'boundary_sensitivity'),
        ('field_soil_temp_100cm_C', 'soil_temp_l4_C', 'soil_temperature_C', '100cm', 'ERA5_layer4_100_289cm', 'boundary_sensitivity'),
    ]
    for field_col, era_col, variable, field_depth, era_layer, comparison_role in comparisons:
        if field_col not in m.columns or era_col not in m.columns:
            continue
        met = regression_metrics(m[field_col], m[era_col])
        met.update({
            'source': 'ERA5-Land', 'variable': variable, 'field_depth': field_depth,
            'era5_layer': era_layer, 'comparison_role': comparison_role,
        })
        rows.append(met)
    return pd.DataFrame(rows)


def monthly_pairs(field_daily: pd.DataFrame, paired_daily: pd.DataFrame) -> pd.DataFrame:
    if paired_daily.empty:
        return pd.DataFrame()
    x = paired_daily.copy()
    x['date'] = pd.to_datetime(x['date'])
    x['month'] = x['date'].dt.to_period('M').astype(str)
    group_cols = ['source', 'window', 'shift_days', 'month']
    if 'chirps_release' in x.columns:
        x['chirps_release'] = x['chirps_release'].fillna('not_applicable')
        group_cols.append('chirps_release')
    out = x.groupby(group_cols, as_index=False).agg(
        field_rain_mm=('field_rain_mm', 'sum'),
        product_rain_mm=('product_rain_mm', 'sum'),
        n_paired_days=('date', 'nunique'),
    )

    f = field_daily[['date']].copy()
    f['date'] = pd.to_datetime(f['date'], errors='coerce')
    f = f.dropna().drop_duplicates()
    f['month'] = f['date'].dt.to_period('M').astype(str)
    nfield = f.groupby('month')['date'].nunique()
    out['n_field_valid_days'] = out['month'].map(nfield).fillna(0).astype(int)
    out['paired_field_coverage'] = np.where(
        out['n_field_valid_days'] > 0, out['n_paired_days'] / out['n_field_valid_days'], np.nan
    )
    out['complete_paired_field_coverage'] = out['n_paired_days'] == out['n_field_valid_days']
    periods = pd.PeriodIndex(out['month'], freq='M')
    out['calendar_days'] = periods.days_in_month.astype(int)
    out['field_month_calendar_complete'] = out['n_field_valid_days'] == out['calendar_days']
    return out


def validate_hourly_rain(field_rain_hourly: pd.DataFrame, inmet_hourly: pd.DataFrame, era5_hourly: pd.DataFrame, threshold_mm: float = 0.2, shifts_hours=None):
    rows, events = [], []
    if field_rain_hourly.empty:
        return pd.DataFrame(), pd.DataFrame()
    shifts = list(map(int, shifts_hours if shifts_hours is not None else [-1, 0, 1]))
    f = field_rain_hourly.copy()
    f['datetime_local'] = pd.to_datetime(f['datetime_local'])
    if 'use_for_hourly_validation' in f.columns:
        use = f['use_for_hourly_validation']
        if not pd.api.types.is_bool_dtype(use):
            use = use.astype('string').str.lower().isin(['true', '1', 't', 'yes'])
        f = f[use].copy()
    sources = []
    if not inmet_hourly.empty and 'rain_mm' in inmet_hourly.columns:
        sources.append(('INMET', inmet_hourly, 'rain_mm'))
    if not era5_hourly.empty and 'precip_mm' in era5_hourly.columns:
        sources.append(('ERA5-Land', era5_hourly, 'precip_mm'))
    for name, src, col in sources:
        base = src[['datetime_local', col]].copy()
        base['datetime_local'] = pd.to_datetime(base['datetime_local'])
        for shift in shifts:
            z = base.copy()
            z['datetime_local'] = z['datetime_local'] + pd.to_timedelta(shift, unit='h')
            m = f.merge(z, on='datetime_local', how='inner').dropna(subset=['field_rain_mm', col])
            met = regression_metrics(m['field_rain_mm'], m[col])
            met.update({'source': name, 'variable': 'hourly_rain_mm', 'shift_hours': shift})
            rows.append(met)
            ev = event_metrics(m['field_rain_mm'], m[col], threshold_mm)
            ev.update({'source': name, 'variable': 'hourly_rain_mm', 'shift_hours': shift})
            events.append(ev)
    return pd.DataFrame(rows), pd.DataFrame(events)

def best_alignment(metrics: pd.DataFrame) -> pd.DataFrame:
    if metrics.empty:
        return pd.DataFrame()
    x = metrics.copy()
    x['_kge_rank'] = x['KGE'].fillna(-np.inf)
    x['_rmse_rank'] = x['RMSE'].fillna(np.inf)
    x = x.sort_values(['source', '_kge_rank', '_rmse_rank'], ascending=[True, False, True])
    return x.groupby('source', as_index=False).head(1).drop(columns=['_kge_rank', '_rmse_rank']).reset_index(drop=True)
