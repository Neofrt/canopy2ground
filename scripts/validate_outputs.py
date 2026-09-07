#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from pathlib import Path

import pandas as pd


class ValidationFailure(RuntimeError):
    pass


def check_unique(df, keys, name, checks):
    n = int(df.duplicated(keys).sum())
    checks.append({"check": f"unique:{name}", "status": "PASS" if n == 0 else "FAIL", "detail": f"duplicate_keys={n}"})
    return n == 0


def main():
    ap = argparse.ArgumentParser(description="Validate core Canopy2Ground processed outputs.")
    ap.add_argument("--root", required=True)
    ap.add_argument("--config", required=True)
    args = ap.parse_args()

    root = Path(args.root).resolve()
    cfg = json.loads(Path(args.config).read_text(encoding="utf-8"))
    timezone = cfg.get("timezone", "America/Belem")

    core = {
        "rain": root / "data/processed/precipitacao/04_precipitacao_diaria_pasto_externo.csv",
        "micro30": root / "data/processed/microclima/microclima_30min_long.csv",
        "tms_native": root / "data/processed/tms/tms_native.csv",
        "tms30": root / "data/processed/tms/tms_30min_long.csv",
        "tms_daily": root / "data/processed/tms/tms_diario_hidrologico.csv",
        "integrated30": root / "data/processed/integrated/dados_integrados_30min.csv",
        "integrated_daily": root / "data/processed/integrated/metricas_diarias_integradas.csv",
        "micro_daily": root / "data/processed/integrated/microclima_diario_integrado.csv",
    }

    checks = []
    ok = True
    frames = {}
    for name, path in core.items():
        exists = path.exists()
        checks.append({"check": f"exists:{name}", "status": "PASS" if exists else "FAIL", "detail": str(path)})
        ok &= exists
        if exists:
            frames[name] = pd.read_csv(path, low_memory=False)

    if not ok:
        raise ValidationFailure("Arquivos processados centrais ausentes. Consulte o relatório de validação.")

    ok &= check_unique(frames["rain"], ["date"], "rain_external_daily", checks)
    ok &= check_unique(frames["micro30"], ["site", "datetime"], "microclimate_30min", checks)
    ok &= check_unique(frames["tms30"], ["site", "depth_cm", "datetime"], "tms_30min", checks)
    ok &= check_unique(frames["tms_daily"], ["date", "site", "depth_cm"], "tms_daily", checks)
    ok &= check_unique(frames["integrated30"], ["datetime"], "integrated_30min", checks)
    ok &= check_unique(frames["integrated_daily"], ["date", "site", "depth_cm"], "integrated_daily", checks)

    # TMS time axis must explicitly retain UTC and local time.
    required_tz_cols = {"datetime_utc", "datetime", "timezone_conversion", "tz_q"}
    missing_tz = sorted(required_tz_cols - set(frames["tms_native"].columns))
    if missing_tz:
        checks.append({"check": "tms_timezone_columns", "status": "FAIL", "detail": f"missing={missing_tz}"})
        ok = False
    else:
        utc = pd.to_datetime(frames["tms_native"]["datetime_utc"], errors="coerce", utc=True)
        local_actual = pd.to_datetime(frames["tms_native"]["datetime"], errors="coerce")
        local_expected = utc.dt.tz_convert(timezone).dt.tz_localize(None)
        valid = utc.notna() & local_actual.notna()
        if valid.any():
            max_seconds = (local_actual[valid] - local_expected[valid]).abs().dt.total_seconds().max()
        else:
            max_seconds = float("nan")
        tz_ok = bool(valid.any()) and float(max_seconds) <= 1.0
        checks.append({
            "check": "tms_utc_to_local_alignment",
            "status": "PASS" if tz_ok else "FAIL",
            "detail": f"timezone={timezone}; max_abs_seconds={max_seconds}",
        })
        ok &= tz_ok

    # Large delta-theta values are descriptive events, not automatic exclusions.
    event_col = "delta_theta_event_class"
    event_ok = event_col in frames["tms_daily"].columns
    checks.append({
        "check": "delta_theta_event_class_present",
        "status": "PASS" if event_ok else "FAIL",
        "detail": "large_wetting/large_drying are retained, not masked",
    })
    ok &= event_ok

    # RH saturation must never be classified as suspect by the current pipeline.
    if "qa_rh_vpd" in frames["micro_daily"].columns:
        suspect = frames["micro_daily"]["qa_rh_vpd"].astype(str).str.contains("suspeito", case=False, na=False).sum()
        sat_ok = int(suspect) == 0
        checks.append({"check": "rh_saturation_not_suspect", "status": "PASS" if sat_ok else "FAIL", "detail": f"suspect_rows={int(suspect)}"})
        ok &= sat_ok

    result_dir = root / "results" / "validation"
    result_dir.mkdir(parents=True, exist_ok=True)
    report = pd.DataFrame(checks)
    report.to_csv(result_dir / "validation_summary.csv", index=False, encoding="utf-8-sig")

    print(report.to_string(index=False))
    if not ok:
        raise SystemExit("\nVALIDAÇÃO FALHOU — o pipeline não deve ser considerado pronto para análise.")
    print("\nVALIDAÇÃO CONCLUÍDA: PASS")


if __name__ == "__main__":
    main()
