#!/usr/bin/env python3
from __future__ import annotations
import argparse
from pathlib import Path
from datetime import datetime
import pandas as pd

def date_range(df, col="date"):
    if col not in df or df.empty:
        return ("NA", "NA")
    x = pd.to_datetime(df[col], errors="coerce").dropna()
    if x.empty:
        return ("NA", "NA")
    return (x.min().date().isoformat(), x.max().date().isoformat())

def safe_read(path):
    return pd.read_csv(path, low_memory=False) if path.exists() else None

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--root", default=".")
    ap.add_argument("--out", default="docs/STATUS_DADOS.md")
    args = ap.parse_args()

    root = Path(args.root).resolve()
    processed = root / "data" / "processed"
    out = root / args.out
    out.parent.mkdir(parents=True, exist_ok=True)

    specs = [
        ("Precipitação externa diária", processed/"precipitacao"/"04_precipitacao_diaria_pasto_externo.csv"),
        ("Microclima diário", processed/"integrated"/"microclima_diario_integrado.csv"),
        ("TMS diário hidrológico", processed/"tms"/"tms_diario_hidrologico.csv"),
        ("Poços - pressão diária", processed/"poco"/"pocos_diario_pressao_absoluta.csv"),
        ("Métricas diárias integradas", processed/"integrated"/"metricas_diarias_integradas.csv"),
        ("Dados integrados 30 min", processed/"integrated"/"dados_integrados_30min.csv"),
    ]

    rows = []
    for label, path in specs:
        df = safe_read(path)
        if df is None:
            rows.append((label, "não encontrado", "-", "-", "-"))
            continue
        start, end = date_range(df)
        rows.append((label, "disponível", f"{len(df):,}".replace(",","."), start, end))

    lines = [
        "# Status atual da base de dados",
        "",
        f"Atualizado automaticamente em: **{datetime.now().strftime('%Y-%m-%d %H:%M')}**",
        "",
        "Esta página é gerada a partir das saídas de `data/processed/` e pode ser atualizada após cada execução do pipeline.",
        "",
        "| Produto | Status | Registros | Início | Fim |",
        "|---|---|---:|---|---|",
    ]
    for r in rows:
        lines.append("| " + " | ".join(r) + " |")

    rain_path = processed/"precipitacao"/"05_precipitacao_mensal_pasto_externo.csv"
    if rain_path.exists():
        rain = pd.read_csv(rain_path, low_memory=False)
        if {"month","rain_mm_available"}.issubset(rain.columns):
            lines += ["", "## Precipitação mensal disponível", "",
                      "| Mês | Precipitação disponível (mm) |",
                      "|---|---:|"]
            for _, r in rain.iterrows():
                val = r["rain_mm_available"]
                lines.append(f"| {r['month']} | {val:.1f} |")

    lines += [
        "",
        "## Observações",
        "",
        "- Datas refletem a disponibilidade real de cada sensor; não é aplicado um corte temporal global.",
        "- Condições de alta umidade relativa na floresta primária são preservadas como observações válidas.",
        "- Grandes valores de `|Δθ|` são preservados como potenciais eventos eco-hidrológicos e não são excluídos automaticamente.",
        "- Os timestamps TMS devem ser interpretados conforme a convenção temporal documentada no pipeline.",
        "",
    ]
    out.write_text("\n".join(lines), encoding="utf-8")
    print("Status atualizado:", out)

if __name__ == "__main__":
    main()
