from __future__ import annotations

import tempfile
import urllib.request
from pathlib import Path

import numpy as np
import pandas as pd


BASE = 'https://data.chc.ucsb.edu/products/CHIRPS/v3.0/daily'


def final_cog_url(product: str, date) -> str:
    d = pd.Timestamp(date)
    return f'{BASE}/final/{product}/cogs/{d:%Y}/chirps-v3.0.{product}.{d:%Y.%m.%d}.cog'


def prelim_tif_url(date) -> str:
    d = pd.Timestamp(date)
    return f'{BASE}/prelim/sat/{d:%Y}/chirps-v3.0.prelim.{d:%Y.%m.%d}.tif'


def _sample_raster(path_or_url: str, latitude: float, longitude: float) -> tuple[float, float, float]:
    try:
        import rasterio
        from rasterio.warp import transform
    except ImportError as exc:
        raise RuntimeError('CHIRPS automático requer rasterio. Execute setup_env.ps1/setup_env.sh para preparar as dependências.') from exc

    env = {
        'GDAL_DISABLE_READDIR_ON_OPEN': 'EMPTY_DIR',
        'GDAL_HTTP_MULTIRANGE': 'YES',
        'GDAL_HTTP_MERGE_CONSECUTIVE_RANGES': 'YES',
        'CPL_VSIL_CURL_ALLOWED_EXTENSIONS': '.cog,.tif',
        'GDAL_HTTP_CONNECTTIMEOUT': '15',
        'GDAL_HTTP_TIMEOUT': '60',
    }
    with rasterio.Env(**env):
        with rasterio.open(path_or_url) as src:
            x, y = float(longitude), float(latitude)
            if src.crs and not src.crs.is_geographic:
                xs, ys = transform('EPSG:4326', src.crs, [x], [y])
                x, y = xs[0], ys[0]
            row, col = src.index(x, y)
            if row < 0 or col < 0 or row >= src.height or col >= src.width:
                raise ValueError('Coordenada fora da cobertura do CHIRPS.')
            val = next(src.sample([(x, y)]))[0]
            if src.nodata is not None and np.isclose(val, src.nodata):
                val = np.nan
            gx, gy = src.xy(row, col)
            if src.crs and not src.crs.is_geographic:
                lons, lats = transform(src.crs, 'EPSG:4326', [gx], [gy])
                gx, gy = lons[0], lats[0]
            return float(val), float(gy), float(gx)


def _download_temp(url: str) -> str:
    fh = tempfile.NamedTemporaryFile(suffix='.tif', delete=False)
    fh.close()
    try:
        urllib.request.urlretrieve(url, fh.name)
    except Exception:
        Path(fh.name).unlink(missing_ok=True)
        raise
    return fh.name


def _err(exc: Exception) -> str:
    text = str(exc).replace('\n', ' ').strip()
    return f'{type(exc).__name__}: {text[:240]}' if text else type(exc).__name__


def download_chirps_point_series(root: Path, cfg: dict, product: str, start_date: str, end_date: str, force: bool = False) -> dict:
    product = product.lower()
    if product not in {'sat', 'rnl'}:
        raise ValueError('CHIRPS product deve ser sat ou rnl.')
    coords = cfg.get('site_coordinates', {})
    lat, lon = coords.get('latitude'), coords.get('longitude')
    if lat is None or lon is None:
        raise ValueError('CHIRPS: latitude/longitude exatas são obrigatórias em climate_config.json.')

    ch_cfg = cfg.get('chirps_v3', {})
    dl_cfg = ch_cfg.get('download', {})
    use_prelim = bool(dl_cfg.get('include_preliminary_sat', False)) and product == 'sat'
    out_dir = root / 'data' / 'external' / 'CHIRPS' / product / 'extracted'
    out_dir.mkdir(parents=True, exist_ok=True)
    out_csv = out_dir / f'chirps_v3_{product}_point_{start_date}_{end_date}.csv'
    manifest_csv = out_dir / f'chirps_v3_{product}_download_manifest_{start_date}_{end_date}.csv'

    cached_final, cached_prelim = {}, {}
    had_cache = out_csv.exists() and manifest_csv.exists() and not force
    if had_cache:
        try:
            old = pd.read_csv(out_csv, low_memory=False)
            if 'date' in old.columns and f'chirps_{product}_mm' in old.columns:
                old['date'] = pd.to_datetime(old['date'], errors='coerce').dt.date.astype('string')
                for _, r in old.dropna(subset=['date']).iterrows():
                    release = str(r.get('chirps_release', 'unknown')).lower()
                    record = r.to_dict()
                    if release == 'final':
                        cached_final[str(r['date'])] = record
                    elif release == 'preliminary':
                        cached_prelim[str(r['date'])] = record
        except Exception:
            cached_final, cached_prelim = {}, {}

    rows, audit = [], []
    requested_dates = [d.date().isoformat() for d in pd.date_range(start_date, end_date, freq='D')]
    # Se todas as datas solicitadas já possuem release final, não há razão para
    # consultar novamente o servidor. Datas preliminares/ausentes são rechecadas
    # em execuções futuras para permitir promoção automática a final.
    if had_cache and all(d in cached_final for d in requested_dates):
        return {
            'status': 'reused', 'product': product, 'n_days': len(requested_dates),
            'n_requested': len(requested_dates), 'n_unavailable': 0,
            'release_counts': {'final': len(requested_dates)},
            'file': str(out_csv), 'manifest': str(manifest_csv),
        }

    for d in pd.date_range(start_date, end_date, freq='D'):
        date_str = d.date().isoformat()
        if date_str in cached_final:
            record = cached_final[date_str]
            rows.append(record)
            audit.append({
                'date': date_str, 'product': product, 'release': 'final',
                'status': 'ok_cached_final', 'detail': '',
                'source_url': record.get('source_url', final_cog_url(product, d)),
            })
            continue

        value = grid_lat = grid_lon = np.nan
        release = 'final'
        url = final_cog_url(product, d)
        status = 'missing'
        detail = ''

        # Cada data é tentada de forma independente. Uma falha de rede em um dia
        # nunca faz o downloader pular silenciosamente todas as datas seguintes.
        try:
            value, grid_lat, grid_lon = _sample_raster(url, lat, lon)
            status = 'ok'
        except Exception as exc:
            status = 'final_unavailable'
            detail = _err(exc)

        # CHIRPS-v3 prelim diário existe apenas para SAT. O fallback é opcional e
        # nunca entra na validação principal quando chirps_final_only_primary=true.
        if status != 'ok' and use_prelim:
            release = 'preliminary'
            if date_str in cached_prelim:
                record = cached_prelim[date_str]
                rows.append(record)
                audit.append({
                    'date': date_str, 'product': product, 'release': 'preliminary',
                    'status': 'ok_cached_preliminary', 'detail': detail,
                    'source_url': record.get('source_url', prelim_tif_url(d)),
                })
                continue
            url = prelim_tif_url(d)
            tmp = None
            try:
                tmp = _download_temp(url)
                value, grid_lat, grid_lon = _sample_raster(tmp, lat, lon)
                status = 'ok'
                detail = ''
            except Exception as exc:
                status = 'prelim_unavailable'
                detail = _err(exc)
            finally:
                if tmp:
                    Path(tmp).unlink(missing_ok=True)

        audit.append({
            'date': date_str,
            'product': product,
            'release': release,
            'status': status,
            'detail': detail,
            'source_url': url,
        })
        if status == 'ok':
            rows.append({
                'date': date_str,
                f'chirps_{product}_mm': value if value >= 0 else np.nan,
                'chirps_release': release,
                'chirps_lat_grid': grid_lat,
                'chirps_lon_grid': grid_lon,
                'requested_latitude': float(lat),
                'requested_longitude': float(lon),
                'source_url': url,
            })

    data_cols = [
        'date', f'chirps_{product}_mm', 'chirps_release', 'chirps_lat_grid',
        'chirps_lon_grid', 'requested_latitude', 'requested_longitude', 'source_url'
    ]
    data = pd.DataFrame(rows, columns=data_cols)
    if not data.empty:
        data['date'] = pd.to_datetime(data['date'], errors='coerce').dt.date.astype('string')
        data = data.sort_values(['date', 'chirps_release']).drop_duplicates('date', keep='last')
    audit_df = pd.DataFrame(audit, columns=['date', 'product', 'release', 'status', 'detail', 'source_url'])
    data.to_csv(out_csv, index=False, encoding='utf-8-sig')
    audit_df.to_csv(manifest_csv, index=False, encoding='utf-8-sig')
    releases = data['chirps_release'].value_counts().to_dict() if not data.empty else {}
    success = audit_df['status'].astype(str).str.startswith('ok') if not audit_df.empty else pd.Series(dtype=bool)
    return {
        'status': 'updated' if had_cache else 'downloaded',
        'product': product,
        'n_days': len(data),
        'n_requested': len(audit_df),
        'n_unavailable': int((~success).sum()) if len(success) else 0,
        'release_counts': releases,
        'file': str(out_csv),
        'manifest': str(manifest_csv),
    }

