from __future__ import annotations

from pathlib import Path
import pandas as pd


def build_field_reference(root: Path, timezone: str = 'America/Belem') -> dict[str, pd.DataFrame]:
    proc = root / 'data' / 'processed'
    rain_dir = proc / 'precipitacao'
    int_dir = proc / 'integrated'

    daily_path = rain_dir / '04_precipitacao_diaria_pasto_externo.csv'
    norm_path = rain_dir / '02_registros_normalizados.csv'
    integ_path = int_dir / 'dados_integrados_30min.csv'
    for p in [daily_path, norm_path, integ_path]:
        if not p.exists():
            raise FileNotFoundError(f'Arquivo de campo necessário não encontrado: {p}')

    daily = pd.read_csv(daily_path, low_memory=False)
    daily['date'] = pd.to_datetime(daily['date'], errors='coerce').dt.date
    daily = daily.rename(columns={'rain_ext_mm': 'field_rain_mm'})
    daily['window'] = 'hydrologic_12_12_local'
    keep = [c for c in ['date', 'field_rain_mm', 'coverage', 'status', 'use_for_calibration_strict', 'use_for_calibration_relaxed', 'serial', 'window'] if c in daily.columns]
    daily = daily[keep].sort_values('date')

    norm = pd.read_csv(norm_path, low_memory=False)
    norm['datetime'] = pd.to_datetime(norm['datetime'], errors='coerce')
    norm = norm[(norm['site'] == 'pasto') & norm['datetime'].notna()].copy()

    # A validação HORÁRIA usa apenas modos em que zeros e intervalos secos também
    # estão explicitamente presentes no arquivo normalizado. No modo
    # event_cumulative_mm, 02_registros_normalizados.csv preserva apenas
    # incrementos positivos; interpretar ausências como zero criaria falsos dias/horas
    # secos. Esse modo continua válido para a série diária canônica, mas não é usado
    # na validação horária sem uma grade de cobertura explícita.
    eligible_modes = {'tip_counts_15min', 'interval_mm'}
    hi = norm[norm['mode'].isin(eligible_modes)].copy()
    if not hi.empty:
        hi['rain_mm'] = pd.to_numeric(hi['rain_mm'], errors='coerce')
        hi = hi.dropna(subset=['rain_mm'])
        hi['hour'] = hi['datetime'].dt.floor('h')

        # Esperado por hora inferido da cadência mediana de cada serial/modo. Para
        # o tipping bucket de 15 min, expected_records_hour = 4.
        cadence = {}
        for (serial, mode), g in hi.groupby(['serial', 'mode'], dropna=False):
            dt = g['datetime'].drop_duplicates().sort_values()
            gaps = dt.diff().dt.total_seconds().div(60).dropna()
            gaps = gaps[(gaps > 0) & (gaps <= 60)]
            step = float(gaps.median()) if not gaps.empty else 15.0
            expected = max(1, int(round(60.0 / step))) if step <= 60 else 1
            cadence[(serial, mode)] = (step, expected)

        rows = []
        for (hour, serial, mode), g in hi.groupby(['hour', 'serial', 'mode'], dropna=False):
            step, expected = cadence[(serial, mode)]
            n = int(g['datetime'].nunique())
            rows.append({
                'datetime_local': hour,
                'serial': serial,
                'source_mode': mode,
                'field_rain_mm': float(g['rain_mm'].sum()),
                'n_source_records': n,
                'expected_records_hour': expected,
                'native_step_min': step,
                'hourly_coverage': min(n / expected, 1.0) if expected else float('nan'),
                'use_for_hourly_validation': bool(n >= expected),
            })
        field_rain_hourly = pd.DataFrame(rows).sort_values('datetime_local').reset_index(drop=True)
    else:
        field_rain_hourly = pd.DataFrame(columns=[
            'datetime_local', 'serial', 'source_mode', 'field_rain_mm',
            'n_source_records', 'expected_records_hour', 'native_step_min',
            'hourly_coverage', 'use_for_hourly_validation'
        ])

    integ = pd.read_csv(integ_path, low_memory=False)
    integ['datetime'] = pd.to_datetime(integ['datetime'], errors='coerce')

    micro_cols = [c for c in ['datetime', 'pasto_temp_C', 'pasto_rh_pct', 'pasto_vpd_kPa', 'pasto_dewpoint_C', 'pasto_par_umol'] if c in integ.columns]
    micro = integ[micro_cols].dropna(subset=['datetime']).copy()
    micro['hour'] = micro['datetime'].dt.floor('h')
    micro_agg = {c: 'mean' for c in micro_cols if c != 'datetime'}
    field_micro_hourly = micro.groupby('hour', as_index=False).agg(micro_agg).rename(columns={
        'hour': 'datetime_local',
        'pasto_temp_C': 'field_temp_C',
        'pasto_rh_pct': 'field_rh_pct',
        'pasto_vpd_kPa': 'field_vpd_kPa',
        'pasto_dewpoint_C': 'field_dewpoint_C',
        'pasto_par_umol': 'field_par_umol',
    })

    soil_cols = [c for c in [
        'datetime',
        'pasto_015_vwc_m3m3', 'pasto_050_vwc_m3m3', 'pasto_100_vwc_m3m3',
        'pasto_015_soil_temp_C', 'pasto_050_soil_temp_C', 'pasto_100_soil_temp_C',
    ] if c in integ.columns]
    soil = integ[soil_cols].dropna(subset=['datetime']).copy()
    soil['hour'] = soil['datetime'].dt.floor('h')
    soil_agg = {c: 'mean' for c in soil_cols if c != 'datetime'}
    field_soil_hourly = soil.groupby('hour', as_index=False).agg(soil_agg).rename(columns={
        'hour': 'datetime_local',
        'pasto_015_vwc_m3m3': 'field_vwc_15cm_m3m3',
        'pasto_050_vwc_m3m3': 'field_vwc_50cm_m3m3',
        'pasto_100_vwc_m3m3': 'field_vwc_100cm_m3m3',
        'pasto_015_soil_temp_C': 'field_soil_temp_15cm_C',
        'pasto_050_soil_temp_C': 'field_soil_temp_50cm_C',
        'pasto_100_soil_temp_C': 'field_soil_temp_100cm_C',
    })

    return {
        'rain_daily': daily,
        'rain_hourly': field_rain_hourly,
        'micro_hourly': field_micro_hourly,
        'soil_hourly': field_soil_hourly,
    }
