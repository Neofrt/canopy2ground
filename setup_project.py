#!/usr/bin/env python3
from __future__ import annotations

import argparse
from pathlib import Path

DEFAULT_ROOT = Path(__file__).resolve().parent

# Only derived/output directories are created automatically.
# data/raw is intentionally absent from this list: field RAW is user-managed and immutable.
DIRS = [
    "data/processed/precipitacao",
    "data/processed/microclima",
    "data/processed/tms",
    "data/processed/poco",
    "data/processed/integrated",
    "data/external/CHIRPS/netcdf",
    "data/external/CHIRPS/extracted",
    "data/external/CHIRPS/harmonized",
    "data/external/INMET",
    "results/precipitacao",
    "results/microclima",
    "results/tms",
    "results/poco",
    "results/integrated",
    "results/validation",
    "results/harmonizacao_CHIRPS",
    "results/modelos",
    "results/figuras",
    "results/tabelas",
    "config",
]


def main():
    ap = argparse.ArgumentParser(description="Create Canopy2Ground derived/output directories.")
    ap.add_argument("--root", default=str(DEFAULT_ROOT))
    args = ap.parse_args()
    root = Path(args.root).resolve()
    for rel in DIRS:
        (root / rel).mkdir(parents=True, exist_ok=True)
    print(f"Estrutura complementar criada em: {root}")
    print("data/raw NÃO foi criado, alterado ou sobrescrito.")


if __name__ == "__main__":
    main()
