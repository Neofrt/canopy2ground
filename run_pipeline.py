#!/usr/bin/env python3
from __future__ import annotations

import argparse
import importlib.util
import json
import subprocess
import sys
from copy import deepcopy
from pathlib import Path

HERE = Path(__file__).resolve().parent
DEFAULT_ROOT = HERE
REQUIRED_PACKAGES = (
    "numpy", "pandas", "openpyxl", "tzdata", "scipy", "statsmodels",
    "matplotlib", "xarray", "netCDF4", "cdsapi", "rasterio", "docx", "reportlab",
)


def run_cmd(cmd):
    print("\n$", " ".join(map(str, cmd)), flush=True)
    subprocess.run([str(x) for x in cmd], check=True)


def missing_packages():
    return [pkg for pkg in REQUIRED_PACKAGES if importlib.util.find_spec(pkg) is None]


def running_in_virtualenv() -> bool:
    return sys.prefix != getattr(sys, "base_prefix", sys.prefix)


def ensure_dependencies(auto_install: bool = False):
    missing = missing_packages()
    if not missing:
        print("Dependências Python: OK.", flush=True)
        return

    req = HERE / "requirements.txt"
    pip_cmd = [sys.executable, "-m", "pip", "install", "-r", req]
    if auto_install:
        print("Dependências ausentes:", ", ".join(missing), flush=True)
        run_cmd(pip_cmd)
        missing_after = missing_packages()
        if missing_after:
            raise SystemExit("Falha ao instalar dependências: " + ", ".join(missing_after))
        print("Dependências instaladas com sucesso.", flush=True)
        return

    pretty = " ".join(f'"{str(x)}"' if " " in str(x) else str(x) for x in pip_cmd)
    raise SystemExit(
        "\nDependências Python ausentes: " + ", ".join(missing)
        + "\n\nUse setup_env.ps1 (Windows) ou setup_env.sh (Linux/macOS) para criar o ambiente virtual automaticamente.\n"
        + "Comando alternativo: " + pretty + "\n"
    )


def merge_missing(defaults, current):
    """Recursively add only missing keys. Existing user values always win."""
    if not isinstance(defaults, dict) or not isinstance(current, dict):
        return deepcopy(current)
    out = deepcopy(current)
    for key, default_value in defaults.items():
        if key not in out:
            out[key] = deepcopy(default_value)
        elif isinstance(default_value, dict) and isinstance(out[key], dict):
            out[key] = merge_missing(default_value, out[key])
    return out


def ensure_config(config_dst: Path, config_src: Path):
    template = json.loads(config_src.read_text(encoding="utf-8"))
    if not config_dst.exists():
        config_dst.write_text(json.dumps(template, ensure_ascii=False, indent=2), encoding="utf-8")
        return "created", []

    current = json.loads(config_dst.read_text(encoding="utf-8"))
    merged = merge_missing(template, current)
    warnings = []
    if "project_start" in merged:
        warnings.append("'project_start' é legada e ignorada; cada série usa suas datas disponíveis.")
    if merged != current:
        config_dst.write_text(json.dumps(merged, ensure_ascii=False, indent=2), encoding="utf-8")
        return "completed_missing_fields", warnings
    return "unchanged", warnings




RAW_INPUT_SUFFIXES = {".csv", ".xlsx", ".xls", ".zip", ".txt"}


def ensure_field_raw_available(root: Path) -> None:
    raw = root / "data" / "raw"
    candidates = []
    if raw.exists():
        candidates = [
            p for p in raw.rglob("*")
            if p.is_file()
            and p.suffix.lower() in RAW_INPUT_SUFFIXES
            and p.name.lower() not in {"readme.txt", "readme.md"}
        ]
    if not candidates:
        raise SystemExit(
            "\nNenhum arquivo RAW de campo foi encontrado em: " + str(raw)
            + "\n\nA estrutura de data/raw foi criada automaticamente, mas os arquivos "
            + "originais de sensores nao acompanham o codigo.\n"
            + "Copie os downloads para PASTO, SECUNDARIA e PRIMARIA e execute novamente.\n"
            + "O pipeline nunca preenche a ausencia de RAW com dados artificiais.\n"
        )


def run_field_pipeline(root: Path, config_dst: Path, qa_rain: float, skip_wells: bool):
    run_cmd([sys.executable, HERE / "setup_project.py", "--root", root])
    ensure_field_raw_available(root)

    rain_out = root / "data" / "processed" / "precipitacao"
    run_cmd([
        sys.executable, HERE / "modules" / "precipitation.py",
        "--entrada", root / "data" / "raw",
        "--saida", rain_out,
        "--qa-relaxed", str(qa_rain),
    ])
    run_cmd([sys.executable, HERE / "modules" / "microclimate.py", "--root", root, "--config", config_dst])
    run_cmd([sys.executable, HERE / "modules" / "tms.py", "--root", root, "--config", config_dst])

    well_raw_exists = any(
        (root / "data" / "raw" / site / "Poço").exists()
        and any((root / "data" / "raw" / site / "Poço").rglob("*.csv"))
        for site in ["PASTO", "SECUNDARIA"]
    )
    if not skip_wells and well_raw_exists:
        run_cmd([sys.executable, HERE / "modules" / "wells.py", "--root", root, "--config", config_dst])
    else:
        print("\nPoços: etapa ignorada (sem RAW ou --skip-wells).", flush=True)

    run_cmd([sys.executable, HERE / "modules" / "integrate.py", "--root", root, "--config", config_dst])
    run_cmd([sys.executable, HERE / "scripts" / "validate_outputs.py", "--root", root, "--config", config_dst])


def _exists(path: Path) -> bool:
    return path.exists() and path.is_file()


def run_climate_layer(root: Path, args):
    cmd = [sys.executable, HERE / "run_climate_pipeline.py", "--root", root]
    if args.download_climate:
        cmd.append("--download")
    if args.force_climate_download:
        cmd.append("--force-download")
    if args.skip_inmet:
        cmd.append("--skip-inmet")
    if args.skip_era5:
        cmd.append("--skip-era5")
    if args.skip_chirps:
        cmd.append("--skip-chirps")
    run_cmd(cmd)

    proc = root / "data" / "processed" / "climate"
    field = proc / "field_microclimate_hourly.csv"
    inmet = proc / "inmet_hourly.csv"
    era5 = proc / "era5_land_hourly.csv"
    micro = root / "results" / "validation" / "climate" / "microclimate"
    current_model = root / "results" / "harmonization" / "current_model.json"

    # Pairwise Pasture + ERA5 is the core atmospheric comparison and does not depend on INMET.
    if _exists(field) and _exists(era5):
        run_cmd([sys.executable, HERE / "scripts" / "compare_microclimate_sources.py", "--root", root])
    else:
        print("\nComparação atmosférica: ignorada; Pastagem + ERA5-Land horários ainda não estão simultaneamente disponíveis.", flush=True)

    # Refit cumulatively every run when paired Pasture + ERA5 daily data exist.
    pair_daily = micro / "era5_field_common_daily_all.csv"
    current_pair_ready = _exists(field) and _exists(era5) and _exists(pair_daily)
    if current_pair_ready:
        run_cmd([sys.executable, HERE / "climate" / "fit_harmonization_models.py", "--root", root])
        if _exists(current_model):
            run_cmd([sys.executable, HERE / "climate" / "harmonization.py", "--root", root])
    else:
        print("\nHarmonização: ignorada; pareamento diário Pastagem + ERA5-Land da execução atual não está disponível.", flush=True)

    # Figure generation is product-wise: missing INMET must not block independent products.
    run_cmd([sys.executable, HERE / "scripts" / "generate_figures.py", "--root", root])

    # Dynamic results report: always reflects the latest available model and validation outputs.
    run_cmd([sys.executable, HERE / "scripts" / "generate_results_report.py", "--root", root])


def print_execution_summary(root: Path) -> None:
    proc = root / "data" / "processed" / "climate"
    res = root / "results"
    figure_status = res / "figures" / "FIGURE_STATUS.csv"

    print("\nCANOPY2GROUND V2 — EXECUTION SUMMARY", flush=True)
    print("Field validation:       " + ("PASS" if (res / "validation" / "field" / "validation_summary.csv").exists() else "CHECK OUTPUT"), flush=True)
    print("ERA5-Land:              " + ("AVAILABLE" if (proc / "era5_land_hourly.csv").exists() else "NOT AVAILABLE"), flush=True)
    print("INMET:                  " + ("AVAILABLE" if (proc / "inmet_hourly.csv").exists() else "NOT AVAILABLE (optional acquisition)"), flush=True)
    print("CHIRPS-v3 SAT:          " + ("AVAILABLE" if (proc / "chirps_v3_sat_daily_point.csv").exists() else "NOT AVAILABLE"), flush=True)
    print("CHIRPS-v3 RNL:          " + ("AVAILABLE" if (proc / "chirps_v3_rnl_daily_point.csv").exists() else "NOT AVAILABLE"), flush=True)
    print("Harmonization model:    " + ("AVAILABLE / REFIT WHEN PAIRED DATA EXIST" if (res / "harmonization" / "current_model.json").exists() else "NOT RUN"), flush=True)
    print("Harmonized series:      " + ("GENERATED" if (proc / "climate_daily_harmonized.csv").exists() else "NOT RUN"), flush=True)

    if figure_status.exists():
        import pandas as pd
        fs = pd.read_csv(figure_status, low_memory=False)
        for row in fs.itertuples(index=False):
            print(f"Figure {int(row.figure)}:               {row.status}", flush=True)
    else:
        print("Figures:                NOT RUN", flush=True)
    report_dir = res / "report"
    report_ok = (report_dir / "Canopy2Ground_resultados.docx").exists() and (report_dir / "Canopy2Ground_resultados.pdf").exists()
    print("Results report (DOCX/PDF): " + ("GENERATED" if report_ok else "NOT RUN"), flush=True)

    print("\nRAW preservado em:", root / "data" / "raw", flush=True)
    print("Dados externos em:", root / "data" / "external", flush=True)
    print("Dados processados em:", root / "data" / "processed", flush=True)
    print("Resultados/auditorias em:", root / "results", flush=True)

def main():
    ap = argparse.ArgumentParser(
        description="Canopy2Ground v2: RAW de campo -> QA -> integração -> clima externo -> validação -> harmonização -> resultados."
    )
    ap.add_argument("--root", default=str(DEFAULT_ROOT), help="Raiz do projeto/dados.")
    ap.add_argument("--qa-rain", type=float, default=0.90)
    ap.add_argument("--skip-wells", action="store_true")
    ap.add_argument("--install-deps", action="store_true")
    mode = ap.add_mutually_exclusive_group()
    mode.add_argument("--field-only", action="store_true", help="Executa apenas RAW -> dados de campo processados/validados.")
    mode.add_argument("--climate-only", action="store_true", help="Executa apenas a camada climática; requer produtos de campo já processados.")
    dl = ap.add_mutually_exclusive_group()
    dl.add_argument("--download-climate", dest="download_climate", action="store_true", help="Atualiza automaticamente ERA5-Land e CHIRPS-v3 (padrão).")
    dl.add_argument("--no-download-climate", dest="download_climate", action="store_false", help="Não tenta atualizar ERA5-Land/CHIRPS nesta execução; reutiliza somente arquivos já presentes.")
    ap.set_defaults(download_climate=True)
    ap.add_argument("--force-climate-download", action="store_true")
    ap.add_argument("--skip-inmet", action="store_true")
    ap.add_argument("--skip-era5", action="store_true")
    ap.add_argument("--skip-chirps", action="store_true")
    args = ap.parse_args()

    if not running_in_virtualenv():
        print("AVISO: execução fora de ambiente virtual. Para uma execução isolada e reproduzível, use .\\run.ps1 no Windows ou ./run.sh no Linux/macOS.", flush=True)
    ensure_dependencies(auto_install=args.install_deps)
    root = Path(args.root).resolve()
    config_dir = root / "config"
    config_dir.mkdir(parents=True, exist_ok=True)
    config_dst = config_dir / "project_config.json"
    config_src = HERE / "config" / "project_config.example.json"
    status, warnings = ensure_config(config_dst, config_src)
    print(f"Configuração de campo: {status} -> {config_dst}", flush=True)
    for msg in warnings:
        print("AVISO:", msg, flush=True)

    if not args.climate_only:
        run_field_pipeline(root, config_dst, args.qa_rain, args.skip_wells)

    if not args.field_only:
        run_climate_layer(root, args)

    status_script = HERE / "scripts" / "generate_status.py"
    if status_script.exists():
        run_cmd([sys.executable, status_script, "--root", root])

    print_execution_summary(root)


if __name__ == "__main__":
    main()
