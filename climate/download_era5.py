from __future__ import annotations

import json
import shutil
import zipfile
from pathlib import Path


DATASET = "reanalysis-era5-land-timeseries"
DEFAULT_VARIABLES = [
    "2m_temperature",
    "2m_dewpoint_temperature",
    "total_precipitation",
    "surface_solar_radiation_downwards",
    "surface_pressure",
    "10m_u_component_of_wind",
    "10m_v_component_of_wind",
    "volumetric_soil_water_layer_1",
    "volumetric_soil_water_layer_2",
    "volumetric_soil_water_layer_3",
    "volumetric_soil_water_layer_4",
    "soil_temperature_level_1",
    "soil_temperature_level_2",
    "soil_temperature_level_3",
    "soil_temperature_level_4",
]


def build_request(latitude: float, longitude: float, start_date: str, end_date: str, variables=None, data_format: str = "netcdf") -> dict:
    return {
        "variable": list(variables or DEFAULT_VARIABLES),
        "location": {"longitude": float(longitude), "latitude": float(latitude)},
        "date": [f"{start_date}/{end_date}"],
        "data_format": data_format,
    }


def _extract_payload(payload: Path, out_dir: Path) -> list[Path]:
    out_dir.mkdir(parents=True, exist_ok=True)
    if zipfile.is_zipfile(payload):
        with zipfile.ZipFile(payload) as zf:
            safe = [n for n in zf.namelist() if not n.endswith('/') and (n.lower().endswith('.nc') or n.lower().endswith('.csv'))]
            for name in safe:
                target = out_dir / Path(name).name
                with zf.open(name) as src, target.open('wb') as dst:
                    shutil.copyfileobj(src, dst)
        return sorted([p for p in out_dir.iterdir() if p.suffix.lower() in {'.nc', '.csv'}])
    with payload.open('rb') as fh:
        magic = fh.read(8)
    ext = '.nc' if magic[:4] in {b'CDF\x01', b'CDF\x02', b'\x89HDF'} else payload.suffix
    target = out_dir / f"era5_land_timeseries{ext}"
    shutil.move(str(payload), target)
    return [target]


def download_era5_land_timeseries(root: Path, cfg: dict, start_date: str, end_date: str, force: bool = False) -> dict:
    coords = cfg.get('site_coordinates', {})
    lat, lon = coords.get('latitude'), coords.get('longitude')
    if lat is None or lon is None:
        raise ValueError('ERA5-Land: latitude/longitude exatas são obrigatórias em climate_config.json.')

    era_cfg = cfg.get('era5_land', {})
    dl_cfg = era_cfg.get('download', {})
    variables = dl_cfg.get('variables') or era_cfg.get('preferred_variables') or DEFAULT_VARIABLES
    out_dir = root / 'data' / 'external' / 'ERA5' / 'cds_timeseries'
    out_dir.mkdir(parents=True, exist_ok=True)
    manifest = out_dir / 'download_manifest.json'

    if manifest.exists() and not force:
        try:
            old = json.loads(manifest.read_text(encoding='utf-8'))
            if old.get('start_date') == start_date and old.get('end_date') == end_date and old.get('latitude') == float(lat) and old.get('longitude') == float(lon):
                files = [out_dir / x for x in old.get('files', [])]
                if files and all(p.exists() for p in files):
                    return {**old, 'status': 'reused'}
        except Exception:
            pass

    try:
        import cdsapi
    except ImportError as exc:
        raise RuntimeError('Pacote cdsapi ausente. Execute setup_env.ps1/setup_env.sh para preparar as dependências.') from exc

    request = build_request(lat, lon, start_date, end_date, variables, 'netcdf')
    payload = out_dir / 'era5_land_timeseries_download.zip'
    if payload.exists():
        payload.unlink()

    try:
        client = cdsapi.Client()
        client.retrieve(DATASET, request, str(payload))
    except Exception as exc:
        raise RuntimeError(
            'Falha no download ERA5-Land via CDS. Verifique %USERPROFILE%\\.cdsapirc, '
            'aceite a licença do dataset no Climate Data Store e tente novamente. '
            f'Detalhe: {exc}'
        ) from exc

    for p in out_dir.iterdir():
        if p.name not in {payload.name, manifest.name} and p.suffix.lower() in {'.nc', '.csv'}:
            p.unlink()
    files = _extract_payload(payload, out_dir)
    if payload.exists():
        payload.unlink()

    info = {
        'status': 'downloaded',
        'dataset': DATASET,
        'start_date': start_date,
        'end_date': end_date,
        'latitude': float(lat),
        'longitude': float(lon),
        'variables': list(variables),
        'files': [p.name for p in files],
        'request': request,
    }
    manifest.write_text(json.dumps(info, indent=2, ensure_ascii=False), encoding='utf-8')
    return info
