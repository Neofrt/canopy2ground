from __future__ import annotations

import argparse
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd


SOURCES = ["FIELD", "INMET", "ERA5"]
SOURCE_LABELS = {"FIELD": "Campo", "INMET": "INMET", "ERA5": "ERA5-Land"}

VARIABLES = {
    "temperature": {"label": "Temperatura do ar", "unit": "°C"},
    "rh": {"label": "Umidade relativa do ar", "unit": "%"},
    "vpd": {"label": "VPD", "unit": "kPa"},
}

PAIR_TO_CONTRAST = {
    frozenset(("ERA5", "FIELD")): "ERA5 - FIELD",
    frozenset(("INMET", "FIELD")): "INMET - FIELD",
    frozenset(("ERA5", "INMET")): "ERA5 - INMET",
}


def read_csv(path: Path) -> pd.DataFrame:
    if not path.exists():
        raise FileNotFoundError(f"Arquivo não encontrado: {path}")
    return pd.read_csv(path, low_memory=False)


def source_col(source: str, variable: str) -> str:
    return f"{source}_{variable}"


def summarize_daily(daily: pd.DataFrame) -> pd.DataFrame:
    rows = []
    for variable, meta in VARIABLES.items():
        for source in SOURCES:
            col = source_col(source, variable)
            x = pd.to_numeric(daily[col], errors="coerce").dropna()
            if x.empty:
                continue
            rows.append(
                {
                    "variable": variable,
                    "variable_label": meta["label"],
                    "unit": meta["unit"],
                    "source": source,
                    "source_label": SOURCE_LABELS[source],
                    "n_days": len(x),
                    "mean": x.mean(),
                    "sd": x.std(ddof=1),
                    "median": x.median(),
                    "q25": x.quantile(0.25),
                    "q75": x.quantile(0.75),
                    "min": x.min(),
                    "max": x.max(),
                }
            )
    return pd.DataFrame(rows)


def summarize_diurnal(hourly: pd.DataFrame) -> pd.DataFrame:
    x = hourly.copy()
    x["datetime_local"] = pd.to_datetime(x["datetime_local"], errors="coerce")
    x = x[x["datetime_local"].notna()].copy()
    x["hour"] = x["datetime_local"].dt.hour

    rows = []
    for variable, meta in VARIABLES.items():
        for source in SOURCES:
            col = source_col(source, variable)
            grouped = x.groupby("hour")[col]
            tmp = grouped.agg(["count", "mean", "median"]).reset_index()
            q = grouped.quantile([0.25, 0.75]).unstack()
            q.columns = ["q25", "q75"]
            tmp = tmp.merge(q.reset_index(), on="hour", how="left")
            tmp["variable"] = variable
            tmp["variable_label"] = meta["label"]
            tmp["unit"] = meta["unit"]
            tmp["source"] = source
            tmp["source_label"] = SOURCE_LABELS[source]
            rows.append(tmp)

    return pd.concat(rows, ignore_index=True)


def p_for_pair(stats: pd.DataFrame, variable: str, a: str, b: str) -> float:
    contrast = PAIR_TO_CONTRAST[frozenset((a, b))]
    z = stats[(stats["variable"] == variable) & (stats["contrast"] == contrast)]
    if z.empty:
        raise ValueError(f"Contraste ausente para {variable}: {contrast}")
    return float(z.iloc[0]["p_holm_within_variable"])


def compact_letters(
    stats: pd.DataFrame,
    summary: pd.DataFrame,
    variable: str,
    alpha: float = 0.05,
) -> dict[str, str]:
    means = {
        s: float(
            summary[(summary["variable"] == variable) & (summary["source"] == s)]
            .iloc[0]["mean"]
        )
        for s in SOURCES
    }
    ordered = sorted(SOURCES, key=lambda s: means[s], reverse=True)

    sig = {}
    for i, a in enumerate(SOURCES):
        for b in SOURCES[i + 1 :]:
            sig[frozenset((a, b))] = p_for_pair(stats, variable, a, b) < alpha

    n_sig = sum(sig.values())

    if n_sig == 0:
        return {s: "a" for s in SOURCES}

    if n_sig == 3:
        return {ordered[0]: "a", ordered[1]: "b", ordered[2]: "c"}

    if n_sig == 1:
        pair = next(pair for pair, is_sig in sig.items() if is_sig)
        a, b = sorted(pair, key=lambda s: means[s], reverse=True)
        c = next(s for s in SOURCES if s not in pair)
        return {a: "a", b: "b", c: "ab"}

    nonsig_pair = next(pair for pair, is_sig in sig.items() if not is_sig)
    pair_sources = list(nonsig_pair)
    other = next(s for s in SOURCES if s not in nonsig_pair)

    pair_mean = np.mean([means[s] for s in pair_sources])
    if pair_mean >= means[other]:
        letters = {s: "a" for s in pair_sources}
        letters[other] = "b"
    else:
        letters = {s: "b" for s in pair_sources}
        letters[other] = "a"

    return letters


def build_letter_table(
    stats: pd.DataFrame,
    summary: pd.DataFrame,
    alpha: float,
) -> pd.DataFrame:
    rows = []

    for variable, meta in VARIABLES.items():
        letters = compact_letters(stats, summary, variable, alpha)

        for source in SOURCES:
            row = summary[
                (summary["variable"] == variable)
                & (summary["source"] == source)
            ].iloc[0]

            rows.append(
                {
                    "variable": variable,
                    "variable_label": meta["label"],
                    "unit": meta["unit"],
                    "source": source,
                    "source_label": SOURCE_LABELS[source],
                    "mean": row["mean"],
                    "median": row["median"],
                    "letter": letters[source],
                    "alpha": alpha,
                }
            )

    return pd.DataFrame(rows)


def plot_diurnal(
    diurnal: pd.DataFrame,
    variable: str,
    outdir: Path,
) -> Path:
    meta = VARIABLES[variable]

    fig, ax = plt.subplots(figsize=(9, 5))

    for source in SOURCES:
        z = diurnal[
            (diurnal["variable"] == variable)
            & (diurnal["source"] == source)
        ].sort_values("hour")

        ax.plot(
            z["hour"],
            z["mean"],
            marker="o",
            linewidth=1.6,
            label=SOURCE_LABELS[source],
        )

        ax.fill_between(
            z["hour"],
            z["q25"],
            z["q75"],
            alpha=0.12,
        )

    ax.set_xlabel("Hora local")
    ax.set_ylabel(f"{meta['label']} ({meta['unit']})")
    ax.set_xticks(range(0, 24, 2))
    ax.legend(frameon=False)
    ax.grid(axis="y", alpha=0.2)

    fig.tight_layout()

    path = outdir / f"fig_diurnal_{variable}.png"

    fig.savefig(
        path,
        dpi=300,
        bbox_inches="tight",
    )

    plt.close(fig)

    return path


def plot_boxplot_with_letters(
    daily: pd.DataFrame,
    variable: str,
    letters: dict[str, str],
    outdir: Path,
) -> Path:
    meta = VARIABLES[variable]

    values = []
    labels = []

    for source in SOURCES:
        col = source_col(source, variable)

        x = pd.to_numeric(
            daily[col],
            errors="coerce",
        ).dropna()

        values.append(x.to_numpy())
        labels.append(SOURCE_LABELS[source])

    fig, ax = plt.subplots(figsize=(6.5, 5))

    ax.boxplot(
        values,
        tick_labels=labels,
        showfliers=False,
    )

    y_min = min(np.nanmin(v) for v in values)
    y_max = max(np.nanmax(v) for v in values)

    span = y_max - y_min

    if span == 0:
        span = max(abs(y_max), 1.0)

    letter_y = []

    for vals in values:
        q1 = np.nanpercentile(vals, 25)
        q3 = np.nanpercentile(vals, 75)
        iqr = q3 - q1

        allowed = vals[
            vals <= q3 + 1.5 * iqr
        ]

        upper_whisker = (
            np.nanmax(allowed)
            if len(allowed)
            else np.nanmax(vals)
        )

        letter_y.append(
            upper_whisker + 0.08 * span
        )

    for i, source in enumerate(SOURCES, start=1):
        ax.text(
            i,
            letter_y[i - 1],
            letters[source],
            ha="center",
            va="bottom",
            fontsize=12,
            fontweight="bold",
        )

    ax.set_ylim(
        y_min - 0.05 * span,
        max(letter_y) + 0.12 * span,
    )

    ax.set_ylabel(
        f"{meta['label']} ({meta['unit']})"
    )

    ax.grid(
        axis="y",
        alpha=0.2,
    )

    fig.tight_layout()

    path = outdir / f"fig_distribution_{variable}_24h.png"

    fig.savefig(
        path,
        dpi=300,
        bbox_inches="tight",
    )

    plt.close(fig)

    return path


def plot_bias(
    stats: pd.DataFrame,
    variable: str,
    outdir: Path,
) -> Path:
    meta = VARIABLES[variable]

    contrasts = [
        "ERA5 - FIELD",
        "INMET - FIELD",
        "ERA5 - INMET",
    ]

    labels = [
        "ERA5 − Campo",
        "INMET − Campo",
        "ERA5 − INMET",
    ]

    z = stats[
        stats["variable"] == variable
    ].set_index("contrast")

    means = np.array(
        [z.loc[c, "bias_ar1"] for c in contrasts],
        dtype=float,
    )

    lows = np.array(
        [z.loc[c, "ci95_low"] for c in contrasts],
        dtype=float,
    )

    highs = np.array(
        [z.loc[c, "ci95_high"] for c in contrasts],
        dtype=float,
    )

    xerr = np.vstack(
        [
            means - lows,
            highs - means,
        ]
    )

    fig, ax = plt.subplots(figsize=(8, 4.8))

    ypos = np.arange(
        len(contrasts)
    )

    ax.errorbar(
        means,
        ypos,
        xerr=xerr,
        fmt="o",
        capsize=4,
    )

    ax.axvline(
        0,
        linewidth=1,
    )

    ax.set_yticks(
        ypos,
        labels,
    )

    ax.set_xlabel(
        f"Viés estimado ({meta['unit']})"
    )

    ax.grid(
        axis="x",
        alpha=0.2,
    )

    fig.tight_layout()

    path = outdir / f"fig_bias_ci_{variable}_24h.png"

    fig.savefig(
        path,
        dpi=300,
        bbox_inches="tight",
    )

    plt.close(fig)

    return path


def write_results_note(
    path: Path,
    stats: pd.DataFrame,
    letters: pd.DataFrame,
    diurnal: pd.DataFrame,
) -> None:
    lines = [
        "# Canopy2Ground v2 — microclimate results snapshot",
        "",
        "Análise principal: médias diárias de 24 h.",
        "Contrastes pareados avaliados por GLSAR com erros AR(1).",
        "P-valores ajustados por Holm dentro de cada variável.",
        "",
        (
            "Letras nos boxplots derivam desses contrastes ajustados: "
            "grupos que compartilham ao menos uma letra não diferem "
            "significativamente a alpha = 0.05."
        ),
        "",
        "## Comparações entre fontes",
    ]

    for variable in VARIABLES:
        lines.append(
            f"\n### {VARIABLES[variable]['label']}"
        )

        z = stats[
            stats["variable"] == variable
        ]

        for _, r in z.iterrows():
            lines.append(
                f"- {r['contrast']}: "
                f"bias={r['bias_ar1']:.3f} "
                f"[IC95% {r['ci95_low']:.3f}, "
                f"{r['ci95_high']:.3f}], "
                f"r={r['r']:.3f}, "
                f"CCC={r['ccc']:.3f}, "
                f"p_Holm={r['p_holm_within_variable']:.3g}"
            )

        lz = letters[
            letters["variable"] == variable
        ]

        label_txt = "; ".join(
            f"{row.source_label}={row.letter}"
            for row in lz.itertuples()
        )

        lines.append(
            f"- Letras: {label_txt}"
        )

    lines.append(
        "\n## Ciclo diurno médio"
    )

    for variable in VARIABLES:
        lines.append(
            f"\n### {VARIABLES[variable]['label']}"
        )

        for source in SOURCES:
            z = diurnal[
                (diurnal["variable"] == variable)
                & (diurnal["source"] == source)
            ]

            row_min = z.loc[
                z["mean"].idxmin()
            ]

            row_max = z.loc[
                z["mean"].idxmax()
            ]

            lines.append(
                f"- {SOURCE_LABELS[source]}: "
                f"mínimo médio={row_min['mean']:.3f} "
                f"às {int(row_min['hour']):02d}:00; "
                f"máximo médio={row_max['mean']:.3f} "
                f"às {int(row_max['hour']):02d}:00."
            )

    path.write_text(
        "\n".join(lines),
        encoding="utf-8",
    )


def main() -> None:
    parser = argparse.ArgumentParser(
        description=(
            "Gera resultados de microclima para Canopy2Ground v2 "
            "usando exclusivamente médias diárias de 24 h."
        )
    )

    parser.add_argument(
        "--root",
        default=".",
        help="Raiz do projeto Canopy2Ground.",
    )

    parser.add_argument(
        "--alpha",
        type=float,
        default=0.05,
        help="Nível de significância usado nas letras.",
    )

    args = parser.parse_args()

    root = Path(
        args.root
    ).resolve()

    base = (
        root
        / "results"
        / "climate_validation"
        / "microclimate_statistics"
    )

    outdir = (
        root
        / "results"
        / "v2_microclimate"
    )

    outdir.mkdir(
        parents=True,
        exist_ok=True,
    )

    hourly = read_csv(
        base
        / "microclimate_common_hourly_all.csv"
    )

    daily = read_csv(
        base
        / "microclimate_common_daily_all.csv"
    )

    stats = read_csv(
        base
        / "microclimate_source_comparison_all.csv"
    )

    diurnal = summarize_diurnal(
        hourly
    )

    summary = summarize_daily(
        daily
    )

    letters = build_letter_table(
        stats,
        summary,
        args.alpha,
    )

    diurnal.to_csv(
        outdir
        / "table_diurnal_cycle.csv",
        index=False,
        encoding="utf-8-sig",
    )

    summary.to_csv(
        outdir
        / "table_daily_distribution_summary.csv",
        index=False,
        encoding="utf-8-sig",
    )

    stats.to_csv(
        outdir
        / "table_comparison_24h.csv",
        index=False,
        encoding="utf-8-sig",
    )

    letters.to_csv(
        outdir
        / "table_significance_letters_24h.csv",
        index=False,
        encoding="utf-8-sig",
    )

    outputs = []

    for variable in VARIABLES:
        letter_map = {
            row.source: row.letter
            for row in letters[
                letters["variable"] == variable
            ].itertuples()
        }

        outputs.append(
            plot_diurnal(
                diurnal,
                variable,
                outdir,
            )
        )

        outputs.append(
            plot_boxplot_with_letters(
                daily,
                variable,
                letter_map,
                outdir,
            )
        )

        outputs.append(
            plot_bias(
                stats,
                variable,
                outdir,
            )
        )

    write_results_note(
        outdir
        / "RESULTS_SNAPSHOT.md",
        stats,
        letters,
        diurnal,
    )

    pd.DataFrame(
        {
            "file": [
                p.name
                for p in outputs
            ],
            "type": [
                "figure"
            ]
            * len(outputs),
        }
    ).to_csv(
        outdir
        / "manifest.csv",
        index=False,
        encoding="utf-8-sig",
    )

    print(
        "\nCANOPY2GROUND V2 — MICROCLIMATE 24 H"
    )

    print(
        f"Outputs: {outdir}"
    )

    print(
        f"Figuras geradas: {len(outputs)}"
    )

    print(
        "Tabelas geradas: 4"
    )

    print(
        (
            "Boxplots: letras de significância baseadas nos "
            "contrastes GLSAR-AR(1) com ajuste de Holm."
        )
    )

    print(
        "Snapshot: RESULTS_SNAPSHOT.md"
    )


if __name__ == "__main__":
    main()
