#!/usr/bin/env python3
from __future__ import annotations

import argparse
from pathlib import Path

DEFAULT_ROOT = Path(__file__).resolve().parent

DIRS = [
    'data/raw/PASTO/Pluviometro',
    'data/raw/PASTO/Poço',
    'data/raw/PASTO/Termohigrometro',
    'data/raw/PASTO/TMS',
    'data/raw/SECUNDARIA/Pluviometro',
    'data/raw/SECUNDARIA/Poço',
    'data/raw/SECUNDARIA/Termohigrometro',
    'data/raw/SECUNDARIA/TMS',
    'data/raw/PRIMARIA/Pluviometro',
    'data/raw/PRIMARIA/Termohigrometro',
    'data/raw/PRIMARIA/TMS',
    'data/external/ERA5',
    'data/external/INMET',
    'data/external/CHIRPS/sat/extracted',
    'data/external/CHIRPS/rnl/extracted',
    'data/processed/precipitacao',
    'data/processed/microclima',
    'data/processed/tms',
    'data/processed/poco',
    'data/processed/integrated',
    'data/processed/climate',
    'results/validation/field',
    'results/validation/climate/microclimate',
    'results/harmonization',
    'results/figures',
    'results/tables',
    'results/report',
    'config',
]


def create_structure(root: Path) -> None:
    """Create only the expected directory scaffold; never change data files."""
    for rel in DIRS:
        (root / rel).mkdir(parents=True, exist_ok=True)


def main() -> None:
    ap = argparse.ArgumentParser(description="Create the Canopy2Ground v2 directory scaffold.")
    ap.add_argument("--root", default=str(DEFAULT_ROOT))
    args = ap.parse_args()
    root = Path(args.root).resolve()
    create_structure(root)
    print(f"Estrutura do projeto verificada/criada em: {root}")
    print("Apenas diretórios são criados; arquivos em data/raw nunca são alterados.")


if __name__ == "__main__":
    main()
