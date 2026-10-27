from __future__ import annotations

from pathlib import Path
import numpy as np
import pandas as pd

from .common import hydrologic_date, rh_from_temp_dewpoint, vpd_from_temp_dewpoint


def _rename_aliases(df: pd.DataFrame) -> pd.DataFrame:
    aliases = {
        'valid_time':'datetime_utc','time':'datetime_utc','datetime':'datetime_utc','date':'datetime_utc',
        't2m':'temp_K','2m_temperature':'temp_K','temp_c':'temp_C',
        'd2m':'dewpoint_K','2m_dewpoint_temperature':'dewpoint_K','dewpoint_c':'dewpoint_C',
        'tp':'precip_m','total_precipitation':'precip_m','precip_mm':'precip_mm',
        'ssrd':'ssrd_J_m2','surface_solar_radiation_downwards':'ssrd_J_m2','ssrd_mj_m2':'ssrd_MJ_m2',
        'sp':'surface_pressure_Pa','surface_pressure':'surface_pressure_Pa',
        'u10':'u10_ms','10m_u_component_of_wind':'u10_ms',
        'v10':'v10_ms','10m_v_component_of_wind':'v10_ms',
        'vpd_kpa':'vpd_kPa',
        'swvl1':'soil_water_l1_m3m3','volumetric_soil_water_layer_1':'soil_water_l1_m3m3',
        'swvl2':'soil_water_l2_m3m3','volumetric_soil_water_layer_2':'soil_water_l2_m3m3',
        'swvl3':'soil_water_l3_m3m3','volumetric_soil_water_layer_3':'soil_water_l3_m3m3',
        'swvl4':'soil_water_l4_m3m3','volumetric_soil_water_layer_4':'soil_water_l4_m3m3',
        'stl1':'soil_temp_l1_K','soil_temperature_level_1':'soil_temp_l1_K',
        'stl2':'soil_temp_l2_K','soil_temperature_level_2':'soil_temp_l2_K',
        'stl3':'soil_temp_l3_K','soil_temperature_level_3':'soil_temp_l3_K',
        'stl4':'soil_temp_l4_K','soil_temperature_level_4':'soil_temp_l4_K',
    }
    return df.rename(columns={c: aliases[c] for c in df.columns if c in aliases})


def _finalize_hourly(df: pd.DataFrame, timezone: str) -> pd.DataFrame:
    x = _rename_aliases(df.copy())
    if 'datetime_utc' not in x.columns:
        raise ValueError('ERA5 horário: não encontrei coluna de tempo (valid_time/time/datetime/date).')
    dt = pd.to_datetime(x['datetime_utc'], errors='coerce', utc=True)
    x['datetime_utc'] = dt
    x['datetime_local'] = dt.dt.tz_convert(timezone).dt.tz_localize(None)
    for c in x.columns:
        if c in ['datetime_utc', 'datetime_local'] or pd.api.types.is_numeric_dtype(x[c]):
            continue
        try:
            converted = pd.to_numeric(x[c], errors='coerce')
            if converted.notna().any() or x[c].isna().all():
                x[c] = converted
        except Exception:
            pass
    if 'temp_C' not in x and 'temp_K' in x:
        x['temp_C'] = pd.to_numeric(x['temp_K'], errors='coerce') - 273.15
    if 'dewpoint_C' not in x and 'dewpoint_K' in x:
        x['dewpoint_C'] = pd.to_numeric(x['dewpoint_K'], errors='coerce') - 273.15
    if 'precip_mm' not in x and 'precip_m' in x:
        x['precip_mm'] = pd.to_numeric(x['precip_m'], errors='coerce') * 1000.0
    if 'ssrd_MJ_m2' not in x and 'ssrd_J_m2' in x:
        x['ssrd_MJ_m2'] = pd.to_numeric(x['ssrd_J_m2'], errors='coerce') / 1e6
        x['shortwave_W_m2'] = pd.to_numeric(x['ssrd_J_m2'], errors='coerce') / 3600.0
    if 'temp_C' in x and 'dewpoint_C' in x:
        x['rh_pct'] = rh_from_temp_dewpoint(x['temp_C'], x['dewpoint_C'])
        x['vpd_kPa'] = vpd_from_temp_dewpoint(x['temp_C'], x['dewpoint_C'])
    if 'u10_ms' in x and 'v10_ms' in x:
        x['wind_speed_10m'] = np.sqrt(pd.to_numeric(x['u10_ms'], errors='coerce')**2 + pd.to_numeric(x['v10_ms'], errors='coerce')**2)
    for i in range(1, 5):
        k = f'soil_temp_l{i}_K'
        if k in x:
            x[f'soil_temp_l{i}_C'] = pd.to_numeric(x[k], errors='coerce') - 273.15
    return x[x['datetime_utc'].notna()].sort_values('datetime_utc').drop_duplicates('datetime_utc', keep='last')


def _merge_hourly_parts(parts: list[pd.DataFrame], timezone: str) -> pd.DataFrame:
    if not parts:
        return pd.DataFrame()
    out = None
    for part in parts:
        if part.empty:
            continue
        p = part.drop(columns=['datetime_local'], errors='ignore').drop_duplicates('datetime_utc').set_index('datetime_utc')
        if out is None:
            out = p.copy()
            continue
        union = out.index.union(p.index)
        out = out.reindex(union)
        p = p.reindex(union)
        for c in p.columns:
            if c in out.columns:
                out[c] = out[c].combine_first(p[c])
            else:
                out[c] = p[c]
    if out is None:
        return pd.DataFrame()
    out = out.reset_index().rename(columns={'index':'datetime_utc'})
    out['datetime_utc'] = pd.to_datetime(out['datetime_utc'], utc=True, errors='coerce')
    out['datetime_local'] = out['datetime_utc'].dt.tz_convert(timezone).dt.tz_localize(None)
    return out.sort_values('datetime_utc').reset_index(drop=True)


def _aggregate_hourly(hourly: pd.DataFrame) -> pd.DataFrame:
    frames = []
    sum_cols = ['precip_mm', 'ssrd_MJ_m2']
    mean_cols = [
        'temp_C', 'dewpoint_C', 'rh_pct', 'vpd_kPa', 'wind_speed_10m', 'surface_pressure_Pa',
        'shortwave_W_m2',
        'soil_water_l1_m3m3', 'soil_water_l2_m3m3', 'soil_water_l3_m3m3', 'soil_water_l4_m3m3',
        'soil_temp_l1_C', 'soil_temp_l2_C', 'soil_temp_l3_C', 'soil_temp_l4_C',
    ]
    for window in ['utc_calendar', 'local_calendar', 'hydrologic_12_12_local']:
        z = hourly.copy()
        if window == 'utc_calendar':
            z['date'] = z['datetime_utc'].dt.tz_localize(None).dt.date
        elif window == 'local_calendar':
            z['date'] = z['datetime_local'].dt.date
        else:
            z['date'] = hydrologic_date(z['datetime_local'], 12)
        agg = {}
        for c in sum_cols:
            if c in z:
                agg[c] = (c, lambda q: q.sum(min_count=1))
        for c in mean_cols:
            if c in z:
                agg[c] = (c, 'mean')
        d = z.groupby('date', as_index=False).agg(**agg) if agg else z[['date']].drop_duplicates()
        d = d.rename(columns={c: f'era5_{c}' for c in d.columns if c != 'date'})
        counts = z.groupby('date').size()
        d['n_era5_hourly'] = d['date'].map(counts)
        d['window'] = window
        frames.append(d)
    return pd.concat(frames, ignore_index=True)


def _read_netcdf(path: Path, cfg: dict, timezone: str) -> pd.DataFrame:
    import xarray as xr
    ds = xr.open_dataset(path)
    try:
        lat = cfg.get('site_coordinates', {}).get('latitude')
        lon = cfg.get('site_coordinates', {}).get('longitude')
        lat_name = next((n for n in ['latitude', 'lat'] if n in ds.coords or n in ds.dims), None)
        lon_name = next((n for n in ['longitude', 'lon'] if n in ds.coords or n in ds.dims), None)
        if lat_name and lon_name and ds.sizes.get(lat_name, 1) > 1 and ds.sizes.get(lon_name, 1) > 1:
            if lat is None or lon is None:
                raise ValueError('ERA5 NetCDF em grade: preencha latitude/longitude em climate_config.json.')
            lon_sel = lon % 360 if float(ds[lon_name].min()) >= 0 and lon < 0 else lon
            ds = ds.sel({lat_name: lat, lon_name: lon_sel}, method='nearest')
        df = ds.to_dataframe().reset_index()
    finally:
        ds.close()
    return _finalize_hourly(df, timezone)


def normalize_era5(paths: list[Path], cfg: dict, project_timezone: str) -> tuple[pd.DataFrame, pd.DataFrame]:
    hourly_parts, daily_parts = [], []
    basis = cfg.get('daily_csv_basis', 'hydrologic_12_12_local')
    for path in paths:
        if path.suffix.lower() == '.nc':
            hourly_parts.append(_read_netcdf(path, cfg, project_timezone))
            continue
        if path.suffix.lower() != '.csv':
            continue
        df = pd.read_csv(path, low_memory=False)
        cols = set(df.columns)
        if 'date' in cols and not ({'valid_time', 'time', 'datetime', 'datetime_utc'} & cols):
            d = _rename_aliases(df.copy())
            d['date'] = pd.to_datetime(d['date'], errors='coerce').dt.date
            ren = {c: f'era5_{c}' for c in d.columns if c != 'date' and not c.startswith('era5_')}
            d = d.rename(columns=ren)
            d['window'] = basis
            daily_parts.append(d)
            continue
        hourly_parts.append(_finalize_hourly(df, project_timezone))
    hourly = _merge_hourly_parts(hourly_parts, project_timezone)
    if not hourly.empty:
        daily_parts.append(_aggregate_hourly(hourly))
    daily = pd.concat(daily_parts, ignore_index=True, sort=False) if daily_parts else pd.DataFrame()
    return hourly, daily
