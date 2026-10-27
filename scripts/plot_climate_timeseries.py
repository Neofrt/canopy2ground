from __future__ import annotations

import argparse
from pathlib import Path

import matplotlib.pyplot as plt
import pandas as pd


VARIABLES = {
    "temperature": {
        "field": "field_temp_C",
        "inmet": "temp_C",
        "era5": "temp_C",
        "ylabel": "Temperatura do ar (°C)",
        "title": "Temperatura do ar",
    },
    "rh": {
        "field": "field_rh_pct",
        "inmet": "rh_pct",
        "era5": "rh_pct",
        "ylabel": "Umidade relativa do ar (%)",
        "title": "Umidade relativa do ar",
    },
    "vpd": {
        "field": "field_vpd_kPa",
        "inmet": "vpd_kPa",
        "era5": "vpd_kPa",
        "ylabel": "VPD (kPa)",
        "title": "Déficit de pressão de vapor",
    },
}


def read_source(path: Path, source: str) -> pd.DataFrame:
    if not path.exists():
        return pd.DataFrame()

    df = pd.read_csv(path, low_memory=False)
    if "datetime_local" not in df.columns:
        raise ValueError(f"{source}: coluna datetime_local não encontrada em {path}")

    df["datetime_local"] = pd.to_datetime(df["datetime_local"], errors="coerce")
    df = df[df["datetime_local"].notna()].copy()

    keep = ["datetime_local"]
    rename = {}

    if source == "field":
        cols = ["field_temp_C", "field_rh_pct", "field_vpd_kPa"]
        keep += [c for c in cols if c in df.columns]
    elif source == "inmet":
        cols = ["temp_C", "rh_pct", "vpd_kPa"]
        keep += [c for c in cols if c in df.columns]
        rename = {c: f"inmet_{c}" for c in cols if c in df.columns}
    elif source == "era5":
        cols = ["temp_C", "rh_pct", "vpd_kPa"]
        keep += [c for c in cols if c in df.columns]
        rename = {c: f"era5_{c}" for c in cols if c in df.columns}
    else:
        raise ValueError(source)

    out = df[keep].rename(columns=rename)
    return out.sort_values("datetime_local").drop_duplicates("datetime_local", keep="last")


def merge_sources(root: Path) -> pd.DataFrame:
    proc = root / "data" / "processed" / "climate"

    field = read_source(proc / "field_microclimate_hourly.csv", "field")
    inmet = read_source(proc / "inmet_hourly.csv", "inmet")
    era5 = read_source(proc / "era5_land_hourly.csv", "era5")

    if field.empty:
        raise FileNotFoundError(
            f"Não encontrei dados de campo em {proc / 'field_microclimate_hourly.csv'}"
        )

    merged = field.copy()
    if not inmet.empty:
        merged = merged.merge(inmet, on="datetime_local", how="outer")
    if not era5.empty:
        merged = merged.merge(era5, on="datetime_local", how="outer")

    return merged.sort_values("datetime_local").reset_index(drop=True)


def aggregate(df: pd.DataFrame, freq: str) -> pd.DataFrame:
    if freq == "hourly":
        return df.copy()

    x = df.copy()
    x["date"] = x["datetime_local"].dt.floor("D")
    numeric = [c for c in x.columns if c not in {"datetime_local", "date"}]
    out = x.groupby("date", as_index=False)[numeric].mean()
    return out.rename(columns={"date": "datetime_local"})


def crop(df: pd.DataFrame, start: str | None, end: str | None) -> pd.DataFrame:
    out = df.copy()
    if start:
        out = out[out["datetime_local"] >= pd.Timestamp(start)]
    if end:
        out = out[out["datetime_local"] <= pd.Timestamp(end)]
    return out


def plot_one(df: pd.DataFrame, variable: str, outdir: Path, freq: str) -> Path:
    spec = VARIABLES[variable]

    candidates = [
        ("field_" + {"temperature": "temp_C", "rh": "rh_pct", "vpd": "vpd_kPa"}[variable], "Campo - pasto"),
        ("inmet_" + {"temperature": "temp_C", "rh": "rh_pct", "vpd": "vpd_kPa"}[variable], "INMET"),
        ("era5_" + {"temperature": "temp_C", "rh": "rh_pct", "vpd": "vpd_kPa"}[variable], "ERA5-Land"),
    ]

    fig, ax = plt.subplots(figsize=(12, 5))

    plotted = 0
    for col, label in candidates:
        if col in df.columns and df[col].notna().any():
            ax.plot(df["datetime_local"], df[col], label=label, linewidth=1.0)
            plotted += 1

    if plotted == 0:
        plt.close(fig)
        raise ValueError(f"Nenhuma série disponível para {variable}")

    suffix = "média diária" if freq == "daily" else "horária"
    ax.set_title(f"{spec['title']} — {suffix}")
    ax.set_xlabel("Data")
    ax.set_ylabel(spec["ylabel"])
    ax.legend()
    ax.grid(True, alpha=0.25)
    fig.autofmt_xdate()
    fig.tight_layout()

    out = outdir / f"timeseries_{variable}_{freq}.png"
    fig.savefig(out, dpi=300, bbox_inches="tight")
    plt.close(fig)
    return out


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Plota séries temporais de Tar, RH e VPD: campo, INMET e ERA5-Land."
    )
    parser.add_argument("--root", default=".", help="Raiz do projeto Canopy2Ground.")
    parser.add_argument(
        "--freq",
        choices=["hourly", "daily", "both"],
        default="both",
        help="Resolução das figuras. Padrão: both.",
    )
    parser.add_argument("--start", default=None, help="Data inicial opcional, YYYY-MM-DD.")
    parser.add_argument("--end", default=None, help="Data final opcional, YYYY-MM-DD.")
    args = parser.parse_args()

    root = Path(args.root).resolve()
    outdir = root / "results" / "climate_validation" / "figures"
    outdir.mkdir(parents=True, exist_ok=True)

    merged = crop(merge_sources(root), args.start, args.end)
    if merged.empty:
        raise ValueError("Nenhum dado no intervalo solicitado.")

    freqs = ["hourly", "daily"] if args.freq == "both" else [args.freq]

    outputs = []
    for freq in freqs:
        data = aggregate(merged, freq)
        data.to_csv(
            outdir / f"microclimate_timeseries_merged_{freq}.csv",
            index=False,
            encoding="utf-8-sig",
        )
        for variable in VARIABLES:
            outputs.append(plot_one(data, variable, outdir, freq))

    print("Figuras geradas:")
    for p in outputs:
        print(f"  {p}")
    print(f"Dados pareados: {outdir}")


if __name__ == "__main__":
    main()
