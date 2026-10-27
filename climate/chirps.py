from __future__ import annotations

from pathlib import Path
import numpy as np
import pandas as pd


def _coord_name(ds, candidates):
    return next((n for n in candidates if n in ds.coords or n in ds.dims), None)


def _precip_name(ds):
    for n in ['precip', 'precipitation', 'rain', 'rainfall', 'chirps', 'pr']:
        if n in ds.data_vars:
            return n
    for n, da in ds.data_vars.items():
        if np.issubdtype(da.dtype, np.number):
            return n
    raise KeyError('CHIRPS: variável de precipitação não identificada.')


def _read_nc(path: Path, product: str, coords: dict) -> pd.DataFrame:
    import xarray as xr
    lat, lon = coords.get('latitude'), coords.get('longitude')
    if lat is None or lon is None:
        raise ValueError('CHIRPS NetCDF: preencha latitude e longitude exatas do pluviômetro do pasto em climate_config.json.')
    with xr.open_dataset(path, decode_times=True) as ds:
        latn = _coord_name(ds, ['latitude', 'lat', 'y'])
        lonn = _coord_name(ds, ['longitude', 'lon', 'x'])
        tn = _coord_name(ds, ['time', 'date', 'valid_time'])
        if not all([latn, lonn, tn]):
            raise KeyError(f'CHIRPS: coordenadas não reconhecidas em {path.name}')
        pn = _precip_name(ds)
        lon_sel = lon % 360 if float(ds[lonn].min()) >= 0 and lon < 0 else lon
        da = ds[pn].sel({latn: lat, lonn: lon_sel}, method='nearest').squeeze(drop=True)
        extras = [d for d in da.dims if d != tn]
        if extras:
            da = da.isel({d: 0 for d in extras})
        vals = np.asarray(da.values, dtype=float)
        dates = pd.to_datetime(ds[tn].values).normalize()
        grid_lat = float(da[latn].values) if latn in da.coords else np.nan
        grid_lon = float(da[lonn].values) if lonn in da.coords else np.nan
        if np.isfinite(grid_lon) and grid_lon > 180:
            grid_lon -= 360
    out = pd.DataFrame({
        'date': dates.date,
        f'chirps_{product}_mm': vals,
        'chirps_lat_grid': grid_lat,
        'chirps_lon_grid': grid_lon,
        'chirps_release': 'unknown',
        'source_file': path.name,
    })
    out.loc[out[f'chirps_{product}_mm'] < 0, f'chirps_{product}_mm'] = np.nan
    return out


def _read_csv(path: Path, product: str) -> pd.DataFrame:
    df = pd.read_csv(path, low_memory=False)
    datecol = next((c for c in ['date', 'time', 'datetime'] if c in df.columns), None)
    valcol = next((c for c in [f'chirps_{product}_mm', 'chirps_mm', 'precip_mm', 'precip', 'rain_mm'] if c in df.columns), None)
    if datecol is None or valcol is None:
        raise ValueError(f'CHIRPS CSV {path.name}: preciso de date/time e precipitação.')
    keep_meta = [c for c in ['chirps_release', 'chirps_lat_grid', 'chirps_lon_grid', 'requested_latitude', 'requested_longitude', 'source_url'] if c in df.columns]
    out = df[[datecol, valcol] + keep_meta].copy()
    out = out.rename(columns={datecol: 'date', valcol: f'chirps_{product}_mm'})
    out['date'] = pd.to_datetime(out['date'], errors='coerce').dt.date
    out[f'chirps_{product}_mm'] = pd.to_numeric(out[f'chirps_{product}_mm'], errors='coerce')
    if 'chirps_release' not in out:
        out['chirps_release'] = 'unknown'
    out['source_file'] = path.name
    return out.dropna(subset=['date'])


def normalize_chirps(paths: list[Path], product: str, coords: dict) -> pd.DataFrame:
    parts = []
    for p in paths:
        if 'manifest' in p.name.lower():
            continue
        if p.suffix.lower() == '.nc':
            parts.append(_read_nc(p, product, coords))
        elif p.suffix.lower() == '.csv':
            parts.append(_read_csv(p, product))
    if not parts:
        return pd.DataFrame(columns=['date', f'chirps_{product}_mm'])
    out = pd.concat(parts, ignore_index=True, sort=False)
    rank = {'final': 3, 'preliminary': 2, 'unknown': 1}
    out['_release_rank'] = out.get('chirps_release', pd.Series('unknown', index=out.index)).astype(str).str.lower().map(rank).fillna(0)
    out = out.sort_values(['date', '_release_rank', 'source_file']).drop_duplicates('date', keep='last').drop(columns='_release_rank')
    return out.reset_index(drop=True)
