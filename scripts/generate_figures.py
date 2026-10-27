#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

SOURCES = ["FIELD", "ERA5", "INMET"]
SOURCE_LABELS = {"FIELD": "Pastagem", "ERA5": "ERA5-Land", "INMET": "INMET"}
VARIABLES = {
    "temperature": {"label": "Temperatura do ar", "unit": "°C"},
    "rh": {"label": "Umidade relativa", "unit": "%"},
    "vpd": {"label": "VPD", "unit": "kPa"},
}
CONTRAST_TO_PAIR = {
    "ERA5 - FIELD": frozenset(("ERA5", "FIELD")),
    "INMET - FIELD": frozenset(("INMET", "FIELD")),
    "ERA5 - INMET": frozenset(("ERA5", "INMET")),
}


def _read(path: Path) -> pd.DataFrame:
    if not path.exists():
        raise FileNotFoundError(path)
    return pd.read_csv(path, low_memory=False)


def _load_json(path: Path) -> dict:
    if not path.exists():
        raise FileNotFoundError(path)
    return json.loads(path.read_text(encoding="utf-8"))


def _source_col(source: str, variable: str) -> str:
    return f"{source}_{variable}"


def _p_for_pair(stats: pd.DataFrame, variable: str, a: str, b: str) -> float:
    pair = frozenset((a, b))
    for contrast, cp in CONTRAST_TO_PAIR.items():
        if cp == pair:
            z = stats[(stats["variable"] == variable) & (stats["contrast"] == contrast)]
            if z.empty:
                raise KeyError(f"Contraste ausente: {variable} / {contrast}")
            return float(z.iloc[0]["p_holm_within_variable"])
    raise KeyError((a, b))


def _compact_letters(daily: pd.DataFrame, stats: pd.DataFrame, variable: str, alpha: float = 0.05) -> dict[str, str]:
    means = {s: float(pd.to_numeric(daily[_source_col(s, variable)], errors="coerce").mean()) for s in SOURCES}
    ordered = sorted(SOURCES, key=lambda s: means[s], reverse=True)
    sig = {frozenset((a, b)): _p_for_pair(stats, variable, a, b) < alpha for i, a in enumerate(SOURCES) for b in SOURCES[i + 1:]}
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
    nonsig = next(pair for pair, is_sig in sig.items() if not is_sig)
    pair_sources = list(nonsig)
    other = next(s for s in SOURCES if s not in nonsig)
    if np.mean([means[s] for s in pair_sources]) >= means[other]:
        out = {s: "a" for s in pair_sources}; out[other] = "b"
    else:
        out = {s: "b" for s in pair_sources}; out[other] = "a"
    return out


def figure_01(daily: pd.DataFrame, stats: pd.DataFrame, out: Path, table_dir: Path) -> None:
    fig, axes = plt.subplots(1, 3, figsize=(12.5, 4.2))
    letter_rows, summary_rows = [], []
    for panel, (ax, (var, meta)) in enumerate(zip(axes, VARIABLES.items())):
        letters = _compact_letters(daily, stats, var)
        values = []
        for source in SOURCES:
            x = pd.to_numeric(daily[_source_col(source, var)], errors="coerce").dropna().to_numpy()
            values.append(x)
            summary_rows.append({"variable": var, "source": source, "mean": np.mean(x), "median": np.median(x), "n": len(x)})
            letter_rows.append({"variable": var, "source": source, "letter": letters[source]})
        ax.boxplot(values, tick_labels=[SOURCE_LABELS[s] for s in SOURCES], showfliers=False)
        y0 = min(float(np.nanmin(v)) for v in values); y1 = max(float(np.nanmax(v)) for v in values)
        span = max(y1 - y0, 1e-9)
        for i, (source, vals) in enumerate(zip(SOURCES, values), 1):
            q1, q3 = np.nanpercentile(vals, [25, 75]); iqr = q3 - q1
            allowed = vals[vals <= q3 + 1.5 * iqr]
            upper = float(np.nanmax(allowed if len(allowed) else vals))
            ax.text(i, upper + 0.08 * span, letters[source], ha="center", va="bottom", fontweight="bold")
        ax.set_ylabel(f"{meta['label']} ({meta['unit']})")
        ax.grid(axis="y", alpha=0.2)
        ax.text(0.01, 0.99, chr(65 + panel), transform=ax.transAxes, va="top", fontweight="bold")
    fig.tight_layout(); fig.savefig(out, dpi=300, bbox_inches="tight"); plt.close(fig)
    pd.DataFrame(summary_rows).to_csv(table_dir / "table_01_microclimate_daily_summary.csv", index=False, encoding="utf-8-sig")
    pd.DataFrame(letter_rows).to_csv(table_dir / "table_02_microclimate_significance_letters.csv", index=False, encoding="utf-8-sig")
    stats.to_csv(table_dir / "table_03_microclimate_glsar_contrasts.csv", index=False, encoding="utf-8-sig")


def figure_02(daily: pd.DataFrame, model: dict | None, out: Path, table_dir: Path) -> None:
    """Daily ERA5-Land x Pasture regressions for all harmonized atmospheric variables."""
    vars_plot = ["temperature", "rh", "vpd"]
    rows = []
    fig, axes = plt.subplots(1, 3, figsize=(12.6, 4.2))
    for panel, (ax, var) in enumerate(zip(axes, vars_plot)):
        meta = VARIABLES[var]
        x = pd.to_numeric(daily[f"ERA5_{var}"], errors="coerce")
        y = pd.to_numeric(daily[f"FIELD_{var}"], errors="coerce")
        z = pd.DataFrame({"x": x, "y": y}).dropna()
        if len(z) < 3:
            raise ValueError(f"Dados insuficientes para regressão {var}: n={len(z)}")
        slope, intercept = np.polyfit(z["x"], z["y"], 1)
        r = float(np.corrcoef(z["x"], z["y"])[0, 1])
        r2 = r ** 2
        lo = float(min(z["x"].min(), z["y"].min()))
        hi = float(max(z["x"].max(), z["y"].max()))
        pad = max((hi - lo) * 0.05, 1e-6)
        lo, hi = lo - pad, hi + pad
        xx = np.linspace(lo, hi, 100)
        ax.scatter(z["x"], z["y"], s=15, alpha=0.65)
        ax.plot([lo, hi], [lo, hi], linestyle="--", linewidth=1, label="1:1")
        ax.plot(xx, intercept + slope * xx, linewidth=1.5, label="Regressão")
        ax.set_xlim(lo, hi); ax.set_ylim(lo, hi)
        ax.set_xlabel(f"ERA5-Land ({meta['unit']})")
        ax.set_ylabel(f"Pastagem ({meta['unit']})")
        symbol = {"temperature": "T", "rh": "RH", "vpd": "VPD"}[var]
        ax.text(0.05, 0.92, f"${symbol}_{{pasto}}$ = {intercept:.3f} + {slope:.3f}${symbol}_{{ERA5}}$\nR² = {r2:.3f}\nn = {len(z)}", transform=ax.transAxes, va="top")
        ax.grid(alpha=0.2)
        ax.text(0.01, 0.99, chr(65 + panel), transform=ax.transAxes, va="top", fontweight="bold")
        op = None if model is None else model.get("variables", {}).get(var, {}).get("operational_method")
        rows.append({"variable": var, "n": len(z), "intercept": intercept, "slope": slope, "R2": r2, "operational_method": op})
    axes[-1].legend(frameon=False, loc="lower right")
    fig.tight_layout()
    fig.savefig(out, dpi=300, bbox_inches="tight")
    plt.close(fig)
    pd.DataFrame(rows).to_csv(table_dir / "table_04_era5_pasture_regressions.csv", index=False, encoding="utf-8-sig")


def figure_03(model: dict, out: Path, table_dir: Path) -> None:
    vars_ = ["temperature", "rh", "vpd"]
    labels = ["Temperatura", "RH", "VPD"]
    raw_rmse = [model["variables"][v]["cross_validation"]["raw_RMSE"] for v in vars_]
    lin_rmse = [model["variables"][v]["cross_validation"]["linear_RMSE"] for v in vars_]
    raw_ccc = [model["variables"][v]["cross_validation"]["raw_CCC"] for v in vars_]
    lin_ccc = [model["variables"][v]["cross_validation"]["linear_CCC"] for v in vars_]
    rmse_reduction = [100.0 * (r - l) / r if r else np.nan for r, l in zip(raw_rmse, lin_rmse)]
    x = np.arange(3); w = 0.35
    fig, axes = plt.subplots(1, 2, figsize=(9.5, 4.2))
    axes[0].bar(x, rmse_reduction, 0.55)
    axes[0].set_xticks(x, labels)
    axes[0].tick_params(axis="x", pad=10)
    axes[0].set_ylabel("Redução do RMSE (%)")
    axes[0].grid(axis="y", alpha=0.2)
    axes[0].text(0.01, 0.99, "A", transform=axes[0].transAxes, va="top", fontweight="bold")
    axes[1].bar(x - w/2, raw_ccc, w, label="ERA5 bruto")
    axes[1].bar(x + w/2, lin_ccc, w, label="ERA5 harmonizado")
    axes[1].set_xticks(x, labels)
    axes[1].tick_params(axis="x", pad=10)
    axes[1].set_ylabel("CCC de Lin")
    axes[1].set_ylim(0, 1)
    axes[1].grid(axis="y", alpha=0.2)
    axes[1].text(0.01, 0.99, "B", transform=axes[1].transAxes, va="top", fontweight="bold")
    axes[1].legend(frameon=False, loc="lower center", bbox_to_anchor=(0.5, 1.01), ncol=2)
    fig.subplots_adjust(bottom=0.20, top=0.88, wspace=0.28)
    fig.savefig(out, dpi=300, bbox_inches="tight")
    plt.close(fig)
    rows = []
    for i, v in enumerate(vars_):
        rows.append({"model_id": model.get("model_id"), "variable": v, "operational_method": model["variables"][v]["operational_method"], "raw_RMSE": raw_rmse[i], "linear_RMSE": lin_rmse[i], "RMSE_reduction_pct": rmse_reduction[i], "raw_CCC": raw_ccc[i], "linear_CCC": lin_ccc[i]})
    pd.DataFrame(rows).to_csv(table_dir / "table_05_harmonization_performance.csv", index=False, encoding="utf-8-sig")


def _selected_precipitation(root: Path) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    base = root / "results" / "validation" / "climate"
    pairs = _read(base / "precip_paired_daily.csv")
    monthly = _read(base / "precip_monthly_paired.csv")
    best = _read(base / "best_temporal_alignment.csv")
    selected_daily, selected_monthly = [], []
    for row in best.itertuples(index=False):
        d = pairs[(pairs["source"] == row.source) & (pairs["window"] == row.window) & (pairs["shift_days"] == row.shift_days)].copy()
        m = monthly[(monthly["source"] == row.source) & (monthly["window"] == row.window) & (monthly["shift_days"] == row.shift_days)].copy()
        if not d.empty: selected_daily.append(d)
        if not m.empty: selected_monthly.append(m)
    if not selected_daily or not selected_monthly:
        raise ValueError("Validação de precipitação sem pares selecionáveis.")
    return pd.concat(selected_daily, ignore_index=True), pd.concat(selected_monthly, ignore_index=True), best



def _eligible_precip_months(monthly: pd.DataFrame, source_order: list[str], min_coverage: float = 0.90) -> pd.DataFrame:
    x = monthly[monthly["source"].isin(source_order)].copy()
    x["field_coverage"] = np.where(
        pd.to_numeric(x["calendar_days"], errors="coerce") > 0,
        pd.to_numeric(x["n_field_valid_days"], errors="coerce") / pd.to_numeric(x["calendar_days"], errors="coerce"),
        np.nan,
    )
    x["paired_field_coverage"] = pd.to_numeric(x["paired_field_coverage"], errors="coerce")
    return x[(x["field_coverage"] >= min_coverage) & (x["paired_field_coverage"] >= min_coverage)].copy()

def figure_04(root: Path, out: Path, table_dir: Path) -> None:
    daily, monthly, best = _selected_precipitation(root)
    source_order = [s for s in ["ERA5-Land", "INMET"] if s in set(daily["source"])]
    if not source_order:
        raise ValueError("ERA5-Land e/ou INMET não estão disponíveis para a figura de precipitação.")
    daily["date"] = pd.to_datetime(daily["date"])
    field = daily.groupby("date", as_index=False)["field_rain_mm"].first().sort_values("date")
    wide = daily.pivot_table(index="date", columns="source", values="product_rain_mm", aggfunc="first").reset_index()
    ts = field.merge(wide, on="date", how="left")

    # Monthly panel: retain months with at least 90% valid field days and at least
    # 90% paired coverage for the product. Requiring 100% of the calendar month
    # was too restrictive for a field series with documented sensor transitions
    # and removed scientifically useful months (e.g., 27/30 or 29/31 valid days).
    complete = _eligible_precip_months(monthly, source_order, min_coverage=0.90)
    months = sorted(complete["month"].dropna().unique())

    fig, axes = plt.subplots(2, 1, figsize=(11, 7.2), gridspec_kw={"height_ratios": [1.2, 1]})
    axes[0].bar(ts["date"], ts["field_rain_mm"], width=0.8, alpha=0.35, label="Pastagem")
    for source in source_order:
        if source in ts:
            axes[0].plot(ts["date"], ts[source], linewidth=1, label=source)
    axes[0].set_ylabel("Precipitação diária (mm)"); axes[0].grid(axis="y", alpha=0.2); axes[0].legend(frameon=False, ncol=3); axes[0].text(0.01, 0.98, "A", transform=axes[0].transAxes, va="top", fontweight="bold")

    if months:
        x = np.arange(len(months)); all_sources = ["Pastagem"] + source_order; w = 0.8 / len(all_sources)
        field_month = complete.groupby("month")["field_rain_mm"].first()
        axes[1].bar(x - 0.4 + w/2, [field_month.get(m, np.nan) for m in months], w, label="Pastagem")
        for j, source in enumerate(source_order, 1):
            z = complete[complete["source"] == source].set_index("month")["product_rain_mm"]
            axes[1].bar(x - 0.4 + w/2 + j*w, [z.get(m, np.nan) for m in months], w, label=source)
        axes[1].set_xticks(x, months)
    else:
        axes[1].text(0.5, 0.5, "Sem mês com ≥90% de cobertura para comparação mensal", ha="center", va="center", transform=axes[1].transAxes)
        axes[1].set_xticks([])
    axes[1].set_ylabel("Precipitação mensal (mm)"); axes[1].set_xlabel("Mês"); axes[1].grid(axis="y", alpha=0.2); axes[1].legend(frameon=False, ncol=3); axes[1].text(0.01, 0.98, "B", transform=axes[1].transAxes, va="top", fontweight="bold")
    fig.tight_layout(); fig.savefig(out, dpi=300, bbox_inches="tight"); plt.close(fig)
    best.to_csv(table_dir / "table_06_precipitation_selected_metrics.csv", index=False, encoding="utf-8-sig")
    complete.to_csv(table_dir / "table_07_precipitation_complete_months.csv", index=False, encoding="utf-8-sig")


def write_captions(path: Path, generated: set[int]) -> None:
    captions = {
        1: "**Figura 1.** Distribuição das médias diárias de (A) temperatura do ar, (B) umidade relativa e (C) déficit de pressão de vapor (VPD) observadas na pastagem e obtidas pelo ERA5-Land e INMET. Letras diferentes indicam diferenças entre as fontes com base em contrastes diários pareados ajustados por GLSAR com estrutura autorregressiva de primeira ordem [AR(1)], com correção de Holm para comparações múltiplas.",
        2: "**Figura 2.** Relação entre valores diários de (A) temperatura do ar, (B) umidade relativa e (C) déficit de pressão de vapor (VPD) obtidos pelo ERA5-Land e observados na pastagem. A linha contínua representa a regressão linear ajustada e a linha tracejada representa a relação 1:1. São apresentadas as equações dos modelos, os respectivos coeficientes de determinação (R²) e o número de dias pareados utilizados em cada ajuste.",
        3: "**Figura 3.** Desempenho da regressão linear em relação ao ERA5-Land bruto, avaliado por validação cruzada leave-one-day-out com embargo temporal de um dia. São apresentados (A) redução percentual do RMSE e (B) coeficiente de concordância de Lin (CCC). Os coeficientes são reestimados cumulativamente à medida que novos dias pareados Pastagem + ERA5-Land são incorporados.",
        4: "**Figura 4.** Comparação da precipitação observada na pastagem com ERA5-Land e INMET. (A) precipitação diária para o melhor alinhamento temporal identificado para cada produto; (B) totais mensais para meses com pelo menos 90% de cobertura dos dias válidos no campo e 90% de cobertura pareada com o respectivo produto. CHIRPS-v3 permanece disponível nas tabelas técnicas de validação, mas não é apresentado nesta figura.",
    }
    lines = ["# Legendas das figuras", ""]
    for i in sorted(generated):
        lines.extend([captions[i], ""])
    path.write_text("\n".join(lines).rstrip() + "\n", encoding="utf-8")


def _remove_stale(paths: list[Path]) -> None:
    for p in paths:
        try:
            if p.exists():
                p.unlink()
        except OSError:
            pass


def main() -> None:
    ap = argparse.ArgumentParser(description="Generate available Canopy2Ground v2 figures independently.")
    ap.add_argument("--root", default=".")
    args = ap.parse_args()
    root = Path(args.root).resolve()
    micro = root / "results" / "validation" / "climate" / "microclimate"
    figdir = root / "results" / "figures"; tabdir = root / "results" / "tables"
    figdir.mkdir(parents=True, exist_ok=True); tabdir.mkdir(parents=True, exist_ok=True)
    model_path = root / "results" / "harmonization" / "current_model.json"
    model = _load_json(model_path) if model_path.exists() else None

    status = []
    generated: set[int] = set()

    f1 = figdir / "figure_01_microclimate_sources.png"
    f2 = figdir / "figure_02_era5_pasture_regressions.png"
    f3 = figdir / "figure_03_harmonization_performance.png"
    f4 = figdir / "figure_04_precipitation_comparison.png"

    # Figure 1: requires all three atmospheric sources and inferential contrasts.
    tri_daily = micro / "microclimate_common_daily_all.csv"
    tri_stats = micro / "microclimate_source_comparison_all.csv"
    if tri_daily.exists() and tri_stats.exists():
        try:
            figure_01(_read(tri_daily), _read(tri_stats), f1, tabdir)
            status.append((1, "GENERATED", "Pastagem + ERA5-Land + INMET")); generated.add(1)
        except Exception as exc:
            _remove_stale([f1, tabdir / "table_01_microclimate_daily_summary.csv", tabdir / "table_02_microclimate_significance_letters.csv", tabdir / "table_03_microclimate_glsar_contrasts.csv"])
            status.append((1, "SKIPPED", f"erro na geração: {exc}"))
    else:
        _remove_stale([f1, tabdir / "table_01_microclimate_daily_summary.csv", tabdir / "table_02_microclimate_significance_letters.csv", tabdir / "table_03_microclimate_glsar_contrasts.csv"])
        status.append((1, "SKIPPED", "comparação Pastagem + ERA5-Land + INMET indisponível"))

    # Figure 2: independent of INMET.
    pair_daily = micro / "era5_field_common_daily_all.csv"
    if pair_daily.exists():
        try:
            figure_02(_read(pair_daily), model, f2, tabdir)
            status.append((2, "GENERATED", "Pastagem + ERA5-Land")); generated.add(2)
        except Exception as exc:
            _remove_stale([f2, tabdir / "table_04_era5_pasture_regressions.csv"])
            status.append((2, "SKIPPED", f"erro na geração: {exc}"))
    else:
        _remove_stale([f2, tabdir / "table_04_era5_pasture_regressions.csv"])
        status.append((2, "SKIPPED", "pareamento diário Pastagem + ERA5-Land indisponível"))

    # Figure 3: requires only the current harmonization model/CV results.
    if model is not None:
        try:
            figure_03(model, f3, tabdir)
            status.append((3, "GENERATED", model.get("model_id", "current_model"))); generated.add(3)
        except Exception as exc:
            _remove_stale([f3, tabdir / "table_05_harmonization_performance.csv"])
            status.append((3, "SKIPPED", f"erro na geração: {exc}"))
    else:
        _remove_stale([f3, tabdir / "table_05_harmonization_performance.csv"])
        status.append((3, "SKIPPED", "modelo corrente de harmonização indisponível"))

    # Figure 4: temporal and monthly comparison only; no precipitation regression.
    # Remove obsolete regression/event tables so stale diagnostics cannot be mistaken for current outputs.
    _remove_stale([
        tabdir / "table_06_precipitation_daily_regression.csv",
        tabdir / "table_07_precipitation_event_detection.csv",
    ])
    try:
        figure_04(root, f4, tabdir)
        status.append((4, "GENERATED", "daily + monthly precipitation comparison")); generated.add(4)
    except Exception as exc:
        _remove_stale([f4, tabdir / "table_06_precipitation_daily_regression.csv", tabdir / "table_07_precipitation_event_detection.csv", tabdir / "table_06_precipitation_selected_metrics.csv", tabdir / "table_07_precipitation_complete_months.csv"])
        status.append((4, "SKIPPED", f"validação de precipitação insuficiente: {exc}"))

    pd.DataFrame(status, columns=["figure", "status", "detail"]).to_csv(figdir / "FIGURE_STATUS.csv", index=False, encoding="utf-8-sig")
    write_captions(figdir / "FIGURE_CAPTIONS.md", generated)

    print("\nCANOPY2GROUND — FIGURE STATUS")
    for fig, st, detail in status:
        print(f"Figura {fig}: {st} — {detail}")
    print(f"Figuras: {figdir}")
    print(f"Tabelas: {tabdir}")


if __name__ == "__main__":
    main()
