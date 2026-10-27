#!/usr/bin/env python3
from __future__ import annotations

import argparse
import importlib.util
import json
import shutil
import sys
from pathlib import Path

import pandas as pd

from climate.field_reference import build_field_reference
from climate.inmet import normalize_inmet
from climate.era5 import normalize_era5
from climate.chirps import normalize_chirps
from climate.validation import (
    validate_precipitation,
    validate_hourly_micro,
    validate_hourly_rain,
    validate_hourly_soil,
    monthly_pairs,
    best_alignment,
)
from climate.download_era5 import download_era5_land_timeseries
from climate.download_chirps import download_chirps_point_series

HERE = Path(__file__).resolve().parent
CLIMATE_PACKAGES = ('numpy', 'pandas', 'xarray')


def missing_packages(extra=()):
    return [p for p in (*CLIMATE_PACKAGES, *extra) if importlib.util.find_spec(p) is None]


def _merge_defaults(user, default):
    if isinstance(user, dict) and isinstance(default, dict):
        out = dict(user)
        for k, v in default.items():
            out[k] = _merge_defaults(out[k], v) if k in out else v
        return out
    return user


def ensure_config(root: Path) -> Path:
    cfg_dir = root / 'config'; cfg_dir.mkdir(parents=True, exist_ok=True)
    dst = cfg_dir / 'climate_config.json'; src = HERE / 'config' / 'climate_config.example.json'
    if not src.exists():
        raise FileNotFoundError(f'Arquivo de configuração climática de exemplo ausente: {src}')
    defaults = json.loads(src.read_text(encoding='utf-8'))
    if not dst.exists():
        shutil.copy2(src, dst)
        print(f'Configuração climática criada em: {dst}', flush=True)
        coords = defaults.get('site_coordinates', {})
        if coords.get('latitude') is None or coords.get('longitude') is None:
            print('ATENÇÃO: preencha latitude e longitude exatas do pluviômetro do pasto antes de extrair CHIRPS/ERA5 em grade.', flush=True)
        else:
            print(f"Coordenadas climáticas configuradas: {coords.get('latitude')}, {coords.get('longitude')}", flush=True)
    else:
        current = json.loads(dst.read_text(encoding='utf-8'))
        merged = _merge_defaults(current, defaults)
        if merged != current:
            dst.write_text(json.dumps(merged, indent=2, ensure_ascii=False), encoding='utf-8')
            print(f'Configuração climática atualizada com novos campos, preservando valores locais: {dst}', flush=True)
    return dst


def glob_many(root: Path, patterns):
    out = []
    for pat in patterns:
        out.extend(root.glob(pat))
    return sorted({p.resolve() for p in out if p.is_file()})


def _date_range(field_daily: pd.DataFrame, cfg: dict, start_arg=None, end_arg=None):
    dl = cfg.get('download', {})
    start = start_arg or dl.get('start_date')
    end = end_arg or dl.get('end_date')
    dates = pd.to_datetime(field_daily['date'], errors='coerce').dropna()
    if start is None:
        start = dates.min().date().isoformat()
    else:
        start = pd.Timestamp(start).date().isoformat()
    if end is None:
        end = dates.max().date().isoformat()
    else:
        end = pd.Timestamp(end).date().isoformat()
    if pd.Timestamp(end) < pd.Timestamp(start):
        raise ValueError('Data final anterior à data inicial.')
    return start, end


def _set_coordinates(cfg_path: Path, cfg: dict, latitude, longitude):
    changed = False
    if latitude is not None:
        cfg.setdefault('site_coordinates', {})['latitude'] = float(latitude); changed = True
    if longitude is not None:
        cfg.setdefault('site_coordinates', {})['longitude'] = float(longitude); changed = True
    if changed:
        if cfg['site_coordinates'].get('latitude') is None or cfg['site_coordinates'].get('longitude') is None:
            raise ValueError('Informe latitude e longitude juntas.')
        cfg['site_coordinates']['status'] = 'EXACT_PASTURE_GAUGE_COORDINATES'
        cfg_path.write_text(json.dumps(cfg, indent=2, ensure_ascii=False), encoding='utf-8')
        print(f'Coordenadas gravadas em {cfg_path}: {cfg["site_coordinates"]["latitude"]}, {cfg["site_coordinates"]["longitude"]}', flush=True)


def _download(root: Path, cfg: dict, field: dict, start: str, end: str, force: bool, skip_era5: bool, skip_chirps: bool):
    print(f'Download climático: período {start} a {end}.', flush=True)
    if not skip_era5 and cfg.get('era5_land', {}).get('enabled', True):
        miss = missing_packages(('cdsapi',))
        if miss:
            print('ERA5-Land download não iniciado: cdsapi ausente. Execute setup_env.ps1/setup_env.sh para preparar as dependências.', flush=True)
        else:
            try:
                info = download_era5_land_timeseries(root, cfg, start, end, force=force)
                print(f'ERA5-Land download: {info.get("status")} | {len(info.get("files", []))} arquivo(s).', flush=True)
            except Exception as exc:
                print(f'ERA5-Land download: AVISO — {exc}', flush=True)
    if not skip_chirps and cfg.get('chirps_v3', {}).get('enabled', True):
        miss = missing_packages(('rasterio',))
        if miss:
            print('CHIRPS download não iniciado: rasterio ausente. Execute setup_env.ps1/setup_env.sh para preparar as dependências.', flush=True)
        else:
            for product in cfg.get('chirps_v3', {}).get('products', ['sat', 'rnl']):
                try:
                    info = download_chirps_point_series(root, cfg, product, start, end, force=force)
                    print(f'CHIRPS-v3 {product}: {info.get("status")} | {info.get("n_days", "reuso")} dias disponíveis | {info.get("n_unavailable", "-")} indisponíveis.', flush=True)
                except Exception as exc:
                    print(f'CHIRPS-v3 {product}: AVISO no download — {exc}', flush=True)


def main():
    ap = argparse.ArgumentParser(description='Canopy2Ground v2 — climate acquisition, normalization and validation.')
    ap.add_argument('--root', default=str(HERE))
    ap.add_argument('--config', default=None)
    ap.add_argument('--skip-inmet', action='store_true')
    ap.add_argument('--skip-era5', action='store_true')
    ap.add_argument('--skip-chirps', action='store_true')
    ap.add_argument('--download', action='store_true', help='Baixa/atualiza ERA5-Land e extrai séries pontuais CHIRPS-v3.')
    ap.add_argument('--force-download', action='store_true')
    ap.add_argument('--start-date', default=None, help='YYYY-MM-DD; padrão: primeira data do campo.')
    ap.add_argument('--end-date', default=None, help='YYYY-MM-DD; padrão: última data do campo.')
    ap.add_argument('--latitude', type=float, default=None)
    ap.add_argument('--longitude', type=float, default=None)
    args = ap.parse_args()

    missing = missing_packages()
    if missing:
        raise SystemExit('Dependências climáticas ausentes: ' + ', '.join(missing) + '\nExecute setup_env.ps1 (Windows) ou setup_env.sh (Linux/macOS) para preparar o ambiente isolado.')

    root = Path(args.root).resolve()
    cfg_path = Path(args.config).resolve() if args.config else ensure_config(root)
    cfg = json.loads(cfg_path.read_text(encoding='utf-8'))
    _set_coordinates(cfg_path, cfg, args.latitude, args.longitude)
    tz = cfg.get('timezone', 'America/Belem')
    proc = root / 'data' / 'processed' / 'climate'
    res = root / 'results' / 'validation' / 'climate'
    proc.mkdir(parents=True, exist_ok=True); res.mkdir(parents=True, exist_ok=True)

    field = build_field_reference(root, tz)
    field['rain_daily'].to_csv(proc / 'field_rain_daily_hydrologic.csv', index=False, encoding='utf-8-sig')
    field['rain_hourly'].to_csv(proc / 'field_rain_hourly_available.csv', index=False, encoding='utf-8-sig')
    field['micro_hourly'].to_csv(proc / 'field_microclimate_hourly.csv', index=False, encoding='utf-8-sig')
    field['soil_hourly'].to_csv(proc / 'field_soil_hourly.csv', index=False, encoding='utf-8-sig')

    start, end = _date_range(field['rain_daily'], cfg, args.start_date, args.end_date)
    if args.download:
        _download(root, cfg, field, start, end, args.force_download, args.skip_era5, args.skip_chirps)

    inmet_hourly = pd.DataFrame(); inmet_daily = pd.DataFrame()
    if not args.skip_inmet and cfg.get('inmet', {}).get('enabled', True):
        paths = glob_many(root, cfg['inmet'].get('input_globs', ['data/external/INMET/*.csv']))
        if paths:
            parts_h, parts_d = [], []
            for p in paths:
                h, d = normalize_inmet(p, cfg['inmet'], tz); h['source_file'] = p.name; d['source_file'] = p.name; parts_h.append(h); parts_d.append(d)
            inmet_hourly = pd.concat(parts_h, ignore_index=True).sort_values('datetime_utc').drop_duplicates('datetime_utc', keep='last')
            inmet_daily = pd.concat(parts_d, ignore_index=True).sort_values(['window', 'date', 'source_file']).drop_duplicates(['window', 'date'], keep='last')
            inmet_hourly.to_csv(proc / 'inmet_hourly.csv', index=False, encoding='utf-8-sig')
            inmet_daily.to_csv(proc / 'inmet_daily_windows.csv', index=False, encoding='utf-8-sig')
            print(f'INMET: {len(inmet_hourly):,} registros horários normalizados.', flush=True)
        else:
            print('INMET: nenhum arquivo encontrado em data/external/INMET.', flush=True)

    era5_hourly = pd.DataFrame(); era5_daily = pd.DataFrame()
    if not args.skip_era5 and cfg.get('era5_land', {}).get('enabled', True):
        paths = glob_many(root, cfg['era5_land'].get('input_globs', ['data/external/ERA5/**/*.csv', 'data/external/ERA5/**/*.nc']))
        if paths:
            e_cfg = dict(cfg['era5_land']); e_cfg['site_coordinates'] = cfg.get('site_coordinates', {})
            era5_hourly, era5_daily = normalize_era5(paths, e_cfg, tz)
            if not era5_hourly.empty:
                era5_hourly.to_csv(proc / 'era5_land_hourly.csv', index=False, encoding='utf-8-sig')
            if not era5_daily.empty:
                era5_daily.to_csv(proc / 'era5_land_daily_windows.csv', index=False, encoding='utf-8-sig')
            print(f'ERA5-Land: {len(era5_hourly):,} registros horários; {len(era5_daily):,} registros diários/janela.', flush=True)
        else:
            print('ERA5-Land: nenhum CSV/NetCDF encontrado em data/external/ERA5.', flush=True)

    chirps = {}
    if not args.skip_chirps and cfg.get('chirps_v3', {}).get('enabled', True):
        coords = cfg.get('site_coordinates', {})
        for product in cfg['chirps_v3'].get('products', ['sat', 'rnl']):
            pats = cfg['chirps_v3'].get('input_globs', {}).get(product, [f'data/external/CHIRPS/{product}/**/*.csv', f'data/external/CHIRPS/{product}/**/*.nc'])
            paths = glob_many(root, pats)
            if paths:
                try:
                    ch = normalize_chirps(paths, product, coords)
                    if cfg.get('validation', {}).get('chirps_final_only_primary', True) and 'chirps_release' in ch.columns:
                        primary = ch[ch['chirps_release'].astype(str).str.lower().isin(['final', 'unknown'])].copy()
                    else:
                        primary = ch
                    chirps[product] = primary
                    ch.to_csv(proc / f'chirps_v3_{product}_daily_point.csv', index=False, encoding='utf-8-sig')
                    print(f'CHIRPS-v3 {product}: {len(ch):,} dias disponíveis; {len(primary):,} usados na validação principal.', flush=True)
                except ValueError as e:
                    print(f'CHIRPS-v3 {product}: {e}', flush=True); chirps[product] = pd.DataFrame()
            else:
                print(f'CHIRPS-v3 {product}: nenhum arquivo encontrado.', flush=True); chirps[product] = pd.DataFrame()

    val_cfg = cfg.get('validation', {})
    field_daily_val = field['rain_daily'].copy()
    qa_pref = str(val_cfg.get('field_qa_preference', 'relaxed')).lower()
    qa_col = 'use_for_calibration_strict' if qa_pref == 'strict' else 'use_for_calibration_relaxed'
    if qa_col in field_daily_val.columns:
        keep = field_daily_val[qa_col].astype('string').str.lower().isin(['true', '1', 't', 'yes'])
        field_daily_val = field_daily_val[keep].copy()

    m, e, p = validate_precipitation(field_daily_val, inmet_daily, era5_daily, chirps, val_cfg)
    hm = validate_hourly_micro(field['micro_hourly'], inmet_hourly, era5_hourly)
    hs = validate_hourly_soil(field['soil_hourly'], era5_hourly)
    hr, he = validate_hourly_rain(field['rain_hourly'], inmet_hourly, era5_hourly, float(val_cfg.get('rain_event_threshold_mm', 0.2)), val_cfg.get('shifts_hours', [-1, 0, 1]))
    mon = monthly_pairs(field_daily_val, p)
    best = best_alignment(m)

    m.to_csv(res / 'precip_metrics_daily.csv', index=False, encoding='utf-8-sig')
    e.to_csv(res / 'precip_event_detection.csv', index=False, encoding='utf-8-sig')
    p.to_csv(res / 'precip_paired_daily.csv', index=False, encoding='utf-8-sig')
    hm.to_csv(res / 'microclimate_metrics_hourly.csv', index=False, encoding='utf-8-sig')
    hs.to_csv(res / 'soil_metrics_hourly.csv', index=False, encoding='utf-8-sig')
    hr.to_csv(res / 'precip_metrics_hourly.csv', index=False, encoding='utf-8-sig')
    he.to_csv(res / 'precip_event_detection_hourly.csv', index=False, encoding='utf-8-sig')
    mon.to_csv(res / 'precip_monthly_paired.csv', index=False, encoding='utf-8-sig')
    best.to_csv(res / 'best_temporal_alignment.csv', index=False, encoding='utf-8-sig')

    (res / 'CLIMATE_METHOD_STATUS.txt').write_text(
        'Canopy2Ground v2 — climate method status\n\n'
        'Precipitation products remain validation products; no precipitation bias correction is applied automatically.\n'
        'Primary field-rain validation uses the strict QA criterion; relaxed QA is retained as a documented sensitivity option.\n'
        'For atmospheric variables, the operational policy cumulatively refits linear temperature, RH and VPD harmonization coefficients whenever new paired Pasture + ERA5-Land days are available; raw ERA5-Land values are always retained alongside harmonized products.\n'
        'CHIRPS preliminary data are excluded from the primary validation by default.\n',
        encoding='utf-8',
    )
    print(f'Validação climática concluída. Resultados: {res}', flush=True)


if __name__ == '__main__':
    main()
