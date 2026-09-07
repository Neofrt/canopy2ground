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
REQUIRED_PACKAGES = ("numpy", "pandas", "openpyxl", "tzdata")


def run_cmd(cmd):
    print("\n$", " ".join(map(str, cmd)), flush=True)
    subprocess.run([str(x) for x in cmd], check=True)


def missing_packages():
    return [pkg for pkg in REQUIRED_PACKAGES if importlib.util.find_spec(pkg) is None]


def ensure_dependencies(auto_install: bool = False):
    missing = missing_packages()
    if not missing:
        print("Dependências Python: OK (numpy, pandas, openpyxl, tzdata).", flush=True)
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
        + "\n\nInstale-as com o MESMO Python usado no pipeline:\n\n"
        + pretty
        + "\n\nOu execute novamente com --install-deps.\n"
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
    """Create config or add missing schema fields without overwriting user choices."""
    template = json.loads(config_src.read_text(encoding="utf-8"))
    if not config_dst.exists():
        config_dst.write_text(json.dumps(template, ensure_ascii=False, indent=2), encoding="utf-8")
        return "created", []

    current = json.loads(config_dst.read_text(encoding="utf-8"))
    merged = merge_missing(template, current)
    warnings = []
    if "project_start" in merged:
        warnings.append(
            "'project_start' é uma chave legada e é ignorada: o Canopy2Ground usa as datas disponíveis de cada série."
        )
    if merged != current:
        config_dst.write_text(json.dumps(merged, ensure_ascii=False, indent=2), encoding="utf-8")
        return "completed_missing_fields", warnings
    return "unchanged", warnings


def main():
    ap = argparse.ArgumentParser(
        description="Canopy2Ground: precipitação + microclima + TMS + poços + integração."
    )
    ap.add_argument("--root", default=str(DEFAULT_ROOT), help="Raiz do projeto/dados.")
    ap.add_argument("--qa-rain", type=float, default=0.90)
    ap.add_argument("--skip-wells", action="store_true")
    ap.add_argument(
        "--install-deps",
        action="store_true",
        help="Instala automaticamente as dependências do requirements.txt.",
    )
    args = ap.parse_args()

    ensure_dependencies(auto_install=args.install_deps)

    root = Path(args.root).resolve()
    config_src = HERE / "config" / "project_config.example.json"
    config_dir = root / "config"
    config_dir.mkdir(parents=True, exist_ok=True)
    config_dst = config_dir / "project_config.json"

    status, warnings = ensure_config(config_dst, config_src)
    if status == "created":
        print("Configuração criada em:", config_dst, flush=True)
    elif status == "completed_missing_fields":
        print("Configuração existente preservada; apenas campos ausentes foram adicionados:", config_dst, flush=True)
    else:
        print("Configuração existente preservada sem alterações:", config_dst, flush=True)
    for msg in warnings:
        print("AVISO:", msg, flush=True)

    # Cria somente diretórios derivados. Nunca escreve/modifica data/raw.
    run_cmd([sys.executable, HERE / "setup_project.py", "--root", root])

    rain_out = root / "data" / "processed" / "precipitacao"
    run_cmd([
        sys.executable,
        HERE / "modules" / "precipitation.py",
        "--entrada", root / "data" / "raw",
        "--saida", rain_out,
        "--qa-relaxed", str(args.qa_rain),
    ])

    run_cmd([
        sys.executable,
        HERE / "modules" / "microclimate.py",
        "--root", root,
        "--config", config_dst,
    ])

    run_cmd([
        sys.executable,
        HERE / "modules" / "tms.py",
        "--root", root,
        "--config", config_dst,
    ])

    well_raw_exists = any(
        (root / "data" / "raw" / site / "Poço").exists()
        and any((root / "data" / "raw" / site / "Poço").rglob("*.csv"))
        for site in ["PASTO", "SECUNDARIA"]
    )
    if not args.skip_wells and well_raw_exists:
        run_cmd([
            sys.executable,
            HERE / "modules" / "wells.py",
            "--root", root,
            "--config", config_dst,
        ])
    else:
        print("\nPoços: etapa ignorada (sem RAW ou --skip-wells).", flush=True)

    run_cmd([
        sys.executable,
        HERE / "modules" / "integrate.py",
        "--root", root,
        "--config", config_dst,
    ])

    validation_script = HERE / "scripts" / "validate_outputs.py"
    if validation_script.exists():
        run_cmd([
            sys.executable,
            validation_script,
            "--root", root,
            "--config", config_dst,
        ])

    status_script = HERE / "scripts" / "generate_status.py"
    if status_script.exists():
        run_cmd([sys.executable, status_script, "--root", root])

    print("\nPIPELINE CONCLUÍDO", flush=True)
    print("Entrada RAW preservada em:", root / "data" / "raw", flush=True)
    print("Dados processados em:", root / "data" / "processed", flush=True)
    print("Auditorias/resultados em:", root / "results", flush=True)


if __name__ == "__main__":
    main()
