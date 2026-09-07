#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Reconstrução auditável da precipitação observada — SEDAP, Capitão Poço (PA)

Objetivo
--------
Ler os CSVs brutos de pluviômetros em um ZIP/pasta, reconhecer mudanças de
formato/configuração e produzir séries de precipitação em janela hidrológica
12:00–12:00, preservando lacunas e a troca física dos equipamentos.

Regras centrais
---------------
1) Serial 22376832:
   - PASTO: equipamento externo histórico; arquivos disponíveis até 27/06/2026.
   - CAP/SECUNDARIA: mesmo equipamento após transferência; RAW inicia 18/07/2026.
2) Serial 22094687:
   - novo pluviômetro externo do PASTO; RAW inicia 23/07/2026.
   - arquivos "Soma Acum.: Event, units/mm" em grade de 15 min representam
     contagens de tombamentos; 1 tombamento = 0,2 mm.
   - arquivo "Evento, mm" registra o acumulado do evento em passos de 0,2 mm;
     convertemos para incrementos por diferença, sem multiplicar novamente.
3) Serial 22376831: pluviômetro da floresta primária (REF).
4) O dia hidrológico termina às 12:00. Ex.: 01/08 12:15 pertence a 02/08.
5) Lacunas não são preenchidas com zero.

Saídas CSV
----------
- 01_auditoria_arquivos.csv
- 02_registros_normalizados.csv
- 03_precipitacao_diaria_todos_sites.csv
- 04_precipitacao_diaria_pasto_externo.csv
- 05_precipitacao_mensal_pasto_externo.csv
- 06_conflitos_duplicatas.csv
- 07_transicoes_e_lacunas.csv
- 08_alteracoes_desde_execucao_anterior.csv
- 09_resumo_execucao.csv

Uso
---
python pipeline_precipitacao_continuo.py \
    --entrada RAW_INBOX \
    --saida resultados_precipitacao
"""

from __future__ import annotations

import argparse
import csv
import io
import math
import re
import statistics
import zipfile
from collections import defaultdict
from dataclasses import dataclass
from datetime import date, datetime, time, timedelta
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Tuple

TZ_NAME = "America/Belem"
TIP_MM = 0.2
MOVE_22376832_TO_CAP = datetime(2026, 7, 18, 15, 0, 0)
NEW_PASTO_22094687_START = datetime(2026, 7, 23, 11, 0, 0)

SERIAL_EXPECTED_SITE = {
    "22376831": "ref",
    "22094687": "pasto",
}


def site_from_path(name: str) -> Optional[str]:
    """Identifica o site mesmo quando o ZIP contém uma pasta-raiz extra."""
    p = name.replace("\\", "/").upper().strip("/")
    padded = f"/{p}/"
    if "/PLUVIOMETRO/" not in padded:
        return None
    if "/PASTO/" in padded:
        return "pasto"
    if "/SECUNDARIA/" in padded or "/CAP/" in padded:
        return "cap"
    if "/PRIMARIA/" in padded or "/REF/" in padded:
        return "ref"
    return None


def parse_rain_datetime(text: str) -> Optional[datetime]:
    """Replica a lógica do R para os formatos HOBO observados."""
    s = str(text).strip()
    m = re.match(r"^(\d{2})/(\d{2})/(\d{2})\s+(\d{1,2})[Hh](\d+)min(\d+)s$", s)
    if not m:
        return None
    a, b, c, hh, mm, ss = map(int, m.groups())
    lower_h = bool(re.search(r"\dh", s))
    ymd_exception = (not lower_h) and a == 26 and c != 26
    if ymd_exception:
        year, month, day = 2000 + a, b, c
    elif lower_h:
        # exports antigos: mm/dd/yy
        year, month, day = 2000 + c, a, b
    else:
        # exports novos: dd/mm/yy
        year, month, day = 2000 + c, b, a
    try:
        return datetime(year, month, day, hh, mm, ss)
    except ValueError:
        return None


def hydro_date(dt: datetime) -> date:
    """Janela de 24 h encerrada às 12:00, compatível com o pipeline R."""
    if dt.time() <= time(12, 0, 0):
        return dt.date()
    return dt.date() + timedelta(days=1)


def serial_from_headers(headers: List[str]) -> Optional[str]:
    for h in headers:
        m = re.search(r"LGR S/N:\s*(\d+)", h or "")
        if m:
            return m.group(1)
    return None


def numeric_or_none(x: str) -> Optional[float]:
    s = (x or "").strip().replace(",", ".")
    if not s:
        return None
    try:
        return float(s)
    except ValueError:
        return None


def precip_column(headers: List[str]) -> Tuple[Optional[int], Optional[str]]:
    for i, h in enumerate(headers):
        hl = (h or "").lower()
        if "evento, mm" in hl and "soma acum" not in hl:
            return i, "event_cumulative_mm"
    for i, h in enumerate(headers):
        hl = (h or "").lower()
        if "soma acum" in hl and "event" in hl:
            return i, "tip_counts_15min"
    for i, h in enumerate(headers):
        hl = (h or "").lower()
        if "soma acum" in hl and "rainfall" in hl:
            return i, "rainfall_sum_unknown_step"
    return None, None


def datetime_column(headers: List[str]) -> Optional[int]:
    for i, h in enumerate(headers):
        if "data hora" in (h or "").lower():
            return i
    return None


def temp_column(headers: List[str]) -> Optional[int]:
    for i, h in enumerate(headers):
        if "temp." in (h or "").lower():
            return i
    return None


@dataclass
class FileAudit:
    source_file: str
    site: str
    serial: str
    raw_mode: str
    interpreted_mode: str
    first_datetime: Optional[datetime]
    last_datetime: Optional[datetime]
    n_rows: int
    n_precip_numeric: int
    median_step_min: Optional[float]
    note: str


@dataclass
class Record:
    site: str
    serial: str
    datetime: datetime
    hydro_date: date
    rain_mm: float
    raw_value: Optional[float]
    mode: str
    source_file: str
    coverage_marker: bool = True


def classify_rainfall_sum_step(dts: List[datetime]) -> str:
    if len(dts) < 2:
        return "daily_24h_mm"
    ds = sorted(set(dts))
    gaps = [(b - a).total_seconds() / 60 for a, b in zip(ds, ds[1:]) if b > a]
    if not gaps:
        return "daily_24h_mm"
    med = statistics.median(gaps)
    return "daily_24h_mm" if med >= 12 * 60 else "interval_mm"


def read_csv_bytes(raw: bytes, source_file: str, site: str) -> Tuple[FileAudit, List[Record], Dict[date, set]]:
    text = raw.decode("utf-8-sig", errors="replace")
    rows = list(csv.reader(io.StringIO(text)))
    if len(rows) < 2:
        raise ValueError(f"CSV sem cabeçalho utilizável: {source_file}")
    headers = rows[1]
    data = rows[2:]
    serial = serial_from_headers(headers) or "unknown"
    dt_i = datetime_column(headers)
    pr_i, raw_mode = precip_column(headers)
    t_i = temp_column(headers)
    if dt_i is None or pr_i is None or raw_mode is None:
        audit = FileAudit(source_file, site, serial, raw_mode or "unknown", "ignored",
                          None, None, len(data), 0, None, "Sem coluna de data/precipitação reconhecida")
        return audit, [], defaultdict(set)

    parsed = []
    coverage_times: Dict[date, set] = defaultdict(set)
    for row in data:
        if dt_i >= len(row):
            continue
        dt = parse_rain_datetime(row[dt_i])
        if dt is None:
            continue
        v = numeric_or_none(row[pr_i] if pr_i < len(row) else "")
        temp_v = numeric_or_none(row[t_i] if t_i is not None and t_i < len(row) else "")
        parsed.append((dt, v, temp_v))

    numeric_dts = [dt for dt, v, _ in parsed if v is not None]
    interpreted = raw_mode
    if raw_mode == "rainfall_sum_unknown_step":
        interpreted = classify_rainfall_sum_step(numeric_dts)

    med_step = None
    if len(numeric_dts) >= 2:
        ds = sorted(set(numeric_dts))
        gaps = [(b-a).total_seconds()/60 for a,b in zip(ds, ds[1:]) if b>a]
        if gaps:
            med_step = statistics.median(gaps)

    records: List[Record] = []

    # Cobertura: para grade regular, cada valor numérico de precipitação é um slot.
    # No modo Evento, mm, a temperatura fornece a grade regular de 15 min.
    if interpreted in ("tip_counts_15min", "interval_mm"):
        for dt, v, _ in parsed:
            if v is not None and dt.second == 0 and dt.minute in (0,15,30,45):
                coverage_times[hydro_date(dt)].add(dt)
    elif interpreted == "event_cumulative_mm":
        for dt, _, tv in parsed:
            if tv is not None and dt.second == 0 and dt.minute in (0,15,30,45):
                coverage_times[hydro_date(dt)].add(dt)

    if interpreted == "daily_24h_mm":
        for dt, v, _ in parsed:
            if v is None:
                continue
            records.append(Record(site, serial, dt, hydro_date(dt), v, v, interpreted, source_file, True))

    elif interpreted == "interval_mm":
        for dt, v, _ in parsed:
            if v is None:
                continue
            records.append(Record(site, serial, dt, hydro_date(dt), v, v, interpreted, source_file, True))

    elif interpreted == "tip_counts_15min":
        for dt, v, _ in parsed:
            if v is None:
                continue
            # Mesmo quando o cabeçalho posterior diz "mm", os valores observados
            # são contagens inteiras por intervalo (ex.: 40, 38, 4). A resolução
            # do tipping bucket é 0,2 mm por tombamento.
            mm = v * TIP_MM
            records.append(Record(site, serial, dt, hydro_date(dt), mm, v, interpreted, source_file, True))

    elif interpreted == "event_cumulative_mm":
        # Valores são acumulados dentro do evento (0.2, 0.4, ..., 8.0).
        # Converte para incrementos. Se houver reset entre eventos, o primeiro
        # valor do novo evento é o próprio incremento.
        ev = [(dt, v) for dt, v, _ in parsed if v is not None]
        ev.sort(key=lambda x: x[0])
        prev = None
        for dt, cur in ev:
            if prev is None:
                inc = max(cur, 0.0)
            elif cur > prev + 1e-9:
                inc = cur - prev
            elif cur < prev - 1e-9:
                inc = max(cur, 0.0)
            else:
                inc = 0.0
            # O registro final de download pode repetir o acumulado; inc=0 e é seguro.
            if inc > 1e-12:
                records.append(Record(site, serial, dt, hydro_date(dt), inc, cur, interpreted, source_file, True))
            prev = cur

    note = ""
    if serial == "22376832" and site == "pasto":
        note = "22376832 como pluviômetro externo histórico do pasto"
    elif serial == "22376832" and site == "cap":
        note = "22376832 após transferência para capoeira"
    elif serial == "22094687":
        note = "novo pluviômetro externo do pasto"
    elif serial == "22376831":
        note = "pluviômetro local da floresta primária"

    audit = FileAudit(
        source_file=source_file, site=site, serial=serial,
        raw_mode=raw_mode, interpreted_mode=interpreted,
        first_datetime=min((x[0] for x in parsed), default=None),
        last_datetime=max((x[0] for x in parsed), default=None),
        n_rows=len(data), n_precip_numeric=len(numeric_dts),
        median_step_min=med_step, note=note
    )
    return audit, records, coverage_times


def iter_csv_sources(input_path: Path) -> Iterable[Tuple[str, str, bytes]]:
    """
    Lê:
      1) um ZIP único; ou
      2) uma pasta-inbox contendo CSVs e/ou vários ZIPs de downloads sucessivos.

    Assim, a cada ~10 dias basta copiar o novo download para a mesma pasta.
    """
    if input_path.is_file() and input_path.suffix.lower() == ".zip":
        with zipfile.ZipFile(input_path) as z:
            for name in sorted(z.namelist()):
                site = site_from_path(name)
                if site and name.lower().endswith(".csv"):
                    yield f"{input_path.name}::{name}", site, z.read(name)
        return

    if input_path.is_dir():
        # CSVs já extraídos.
        for p in sorted(input_path.rglob("*.csv")):
            rel = p.relative_to(input_path).as_posix()
            site = site_from_path(rel)
            if site:
                yield rel, site, p.read_bytes()

        # ZIPs de campanhas/downloads sucessivos; não precisam ser extraídos.
        for zp in sorted(input_path.rglob("*.zip")):
            try:
                with zipfile.ZipFile(zp) as z:
                    zip_rel = zp.relative_to(input_path).as_posix()
                    for name in sorted(z.namelist()):
                        if not name.lower().endswith(".csv"):
                            continue
                        site = site_from_path(name)
                        if site:
                            yield f"{zip_rel}::{name}", site, z.read(name)
            except zipfile.BadZipFile:
                print(f"AVISO: ZIP inválido ignorado: {zp}")
        return

    raise ValueError("--entrada deve ser um ZIP ou uma pasta")


def date_range(a: date, b: date) -> Iterable[date]:
    d = a
    while d <= b:
        yield d
        d += timedelta(days=1)


def month_days(y: int, m: int) -> List[date]:
    first = date(y,m,1)
    if m == 12:
        nxt = date(y+1,1,1)
    else:
        nxt = date(y,m+1,1)
    return list(date_range(first, nxt-timedelta(days=1)))


def write_csv(path: Path, headers: List[str], rows: Iterable[Iterable]):
    with path.open("w", encoding="utf-8-sig", newline="") as f:
        w = csv.writer(f)
        w.writerow(headers)
        for row in rows:
            w.writerow(row)


def load_previous_daily(path: Path) -> Dict[str, dict]:
    if not path.exists():
        return {}
    out = {}
    with path.open("r", encoding="utf-8-sig", newline="") as f:
        for r in csv.DictReader(f):
            out[r.get("date", "")] = r
    return out


def as_float_or_none(x):
    try:
        if x is None or str(x).strip() == "":
            return None
        return float(x)
    except Exception:
        return None


def main():
    ap = argparse.ArgumentParser(
        description="Pipeline contínuo e auditável de precipitação SEDAP"
    )
    ap.add_argument(
        "--entrada", required=True,
        help="ZIP único OU pasta-inbox com CSVs/ZIPs acumulados de todos os downloads"
    )
    ap.add_argument("--saida", default="resultados_precipitacao")
    ap.add_argument(
        "--qa-relaxed", type=float, default=0.90,
        help="Cobertura mínima do dia de 15 min para QA relaxado (default 0.90)"
    )
    args = ap.parse_args()

    if not (0 < args.qa_relaxed <= 1):
        raise ValueError("--qa-relaxed deve estar entre 0 e 1")

    entrada = Path(args.entrada)
    out = Path(args.saida)
    out.mkdir(parents=True, exist_ok=True)

    # Snapshot da execução anterior para relatar o que mudou após um novo download.
    previous_daily = load_previous_daily(out / "04_precipitacao_diaria_pasto_externo.csv")

    audits: List[FileAudit] = []
    all_records: List[Record] = []
    coverage_union: Dict[Tuple[str,str,date], set] = defaultdict(set)
    source_end: Dict[str, datetime] = {}

    for src, site, raw in iter_csv_sources(entrada):
        audit, recs, cov = read_csv_bytes(raw, src, site)
        audits.append(audit)
        if audit.last_datetime is not None:
            source_end[src] = audit.last_datetime
        all_records.extend(recs)
        for hd, times in cov.items():
            coverage_union[(site, audit.serial, hd)].update(times)

    # Validação física da troca de instrumentos.
    filtered: List[Record] = []
    rejected = []
    for r in all_records:
        ok = True
        reason = ""
        if r.serial == "22376832":
            if r.site == "pasto" and r.datetime >= MOVE_22376832_TO_CAP:
                ok = False; reason = "22376832 não pode permanecer no pasto após a transferência"
            if r.site == "cap" and r.datetime < MOVE_22376832_TO_CAP:
                ok = False; reason = "22376832 ainda não estava na capoeira"
        elif r.serial == "22094687":
            if r.site != "pasto" or r.datetime < NEW_PASTO_22094687_START:
                ok = False; reason = "22094687 válido apenas no pasto após instalação"
        elif r.serial in SERIAL_EXPECTED_SITE and r.site != SERIAL_EXPECTED_SITE[r.serial]:
            ok = False; reason = "serial em site inesperado"
        if ok:
            filtered.append(r)
        else:
            rejected.append((r, reason))

    # Deduplicação entre downloads. Mesma observação pode existir em vários CSVs.
    by_key: Dict[Tuple[str,str,datetime,str], List[Record]] = defaultdict(list)
    for r in filtered:
        by_key[(r.site,r.serial,r.datetime,r.mode)].append(r)

    dedup: List[Record] = []
    conflicts = []
    resolved_conflicts = []
    for key, rr in by_key.items():
        vals = sorted({round(x.rain_mm, 10) for x in rr})
        # Downloads sucessivos do HOBO podem reexportar o mesmo timestamp com
        # um valor atualizado (o download anterior pode ter ocorrido antes do
        # fechamento completo do intervalo). Portanto, em conflito, a cópia do
        # arquivo que alcança a data/hora mais recente é a autoridade.
        x = max(rr, key=lambda z: source_end.get(z.source_file, datetime.min))
        mm = x.rain_mm
        if len(vals) > 1:
            conflicts.append((key, vals, [z.source_file for z in rr]))
            resolved_conflicts.append((key, vals, [z.source_file for z in rr], mm, x.source_file, source_end.get(x.source_file)))
        dedup.append(Record(x.site,x.serial,x.datetime,x.hydro_date,mm,x.raw_value,x.mode,"; ".join(sorted({z.source_file for z in rr}))))

    dedup.sort(key=lambda r:(r.site,r.serial,r.datetime,r.mode))

    # Agregação diária por site/serial/modo.
    daily_parts: Dict[Tuple[str,str,date], List[Record]] = defaultdict(list)
    for r in dedup:
        daily_parts[(r.site,r.serial,r.hydro_date)].append(r)

    daily_site = []
    for (site, serial, hd), rr in sorted(daily_parts.items()):
        modes = sorted({r.mode for r in rr})
        # daily_24h já contém o total diário; não somar múltiplas cópias.
        if modes == ["daily_24h_mm"]:
            vals = [r.rain_mm for r in rr]
            rain = statistics.median(vals)
            cov = 1.0
            nslots = 1
            expected = 1
        else:
            rain = sum(r.rain_mm for r in rr)
            # cobertura de grade regular por serial/dia; une downloads sobrepostos.
            times = coverage_union.get((site, serial, hd), set())
            nslots = len(times)
            expected = 96
            cov = min(nslots/expected, 1.0) if expected else None
        daily_site.append({
            "date": hd, "site": site, "serial": serial,
            "rain_mm": rain, "coverage": cov, "n_slots": nslots,
            "expected_slots": expected, "modes": "+".join(modes),
            "sources": "; ".join(sorted({r.source_file for r in rr}))
        })

    # Cria uma linha para dias com cobertura regular mas chuva zero no modo Evento, mm.
    existing_keys = {(d["site"],d["serial"],d["date"]) for d in daily_site}
    for (site,serial,hd), times in sorted(coverage_union.items()):
        key=(site,serial,hd)
        if key in existing_keys:
            continue
        nslots=len(times); expected=96
        daily_site.append({
            "date":hd,"site":site,"serial":serial,"rain_mm":0.0,
            "coverage":min(nslots/expected,1.0),"n_slots":nslots,"expected_slots":expected,
            "modes":"event_cumulative_mm_zero_day","sources":""
        })
    daily_site.sort(key=lambda d:(d["date"],d["site"],d["serial"]))

    # Série canônica do pasto externo, do primeiro ao último dia realmente disponível.
    # Não é imposto corte global de data; lacunas internas permanecem explícitas como NA.
    pasto_by_date: Dict[date, dict] = {}
    for d in daily_site:
        if d["site"] != "pasto":
            continue
        if d["serial"] == "22376832":
            pasto_by_date[d["date"]] = d
        elif d["serial"] == "22094687":
            # novo equipamento tem precedência após sua instalação
            pasto_by_date[d["date"]] = d

    if not pasto_by_date:
        raise RuntimeError(
            "Nenhuma observação válida de precipitação externa do pasto foi encontrada nos RAW."
        )
    first_pasto = min(pasto_by_date)
    last_pasto = max(pasto_by_date)
    canonical = []
    for hd in date_range(first_pasto, last_pasto):
        d = pasto_by_date.get(hd)
        if d is None:
            canonical.append({
                "date": hd, "rain_ext_mm": None, "serial": None,
                "coverage": 0.0, "status": "missing",
                "use_for_calibration_strict": False,
                "use_for_calibration_relaxed": False,
                "use_for_calibration": False,
                "note": "sem observação do pasto nos RAW"
            })
        else:
            cov = d["coverage"]
            if d["expected_slots"] == 1:
                status = "complete_daily_record"
            elif cov >= 0.999999:
                status = "complete_15min"
            elif cov >= args.qa_relaxed:
                status = "near_complete_15min"
            else:
                status = "partial_15min"
            note = ""
            if d["serial"] == "22376832":
                note = "pluviômetro histórico do pasto; total de 24 h já encerrado às 12:00"
            elif d["serial"] == "22094687":
                note = "novo tipping bucket do pasto; 0,2 mm/tombamento ou Evento, mm convertido a incrementos"
            strict_ok = status in ("complete_daily_record", "complete_15min")
            relaxed_ok = status in ("complete_daily_record", "complete_15min", "near_complete_15min")
            canonical.append({
                "date": hd, "rain_ext_mm": d["rain_mm"], "serial": d["serial"],
                "coverage": cov, "status": status,
                "use_for_calibration_strict": strict_ok,
                "use_for_calibration_relaxed": relaxed_ok,
                # alias mantido para compatibilidade com o módulo CHIRPS anterior
                "use_for_calibration": relaxed_ok,
                "note": note
            })

    # Mensal: não inventa dias ausentes. Total disponível + QA de completude.
    months = sorted({(r["date"].year,r["date"].month) for r in canonical})
    monthly = []
    can_by_date = {r["date"]:r for r in canonical}
    for y,m in months:
        days = month_days(y,m)
        rows = [can_by_date.get(d) for d in days if first_pasto <= d <= last_pasto]
        obs = [r for r in rows if r and r["rain_ext_mm"] is not None]
        qa_relaxed = [r for r in obs if r["use_for_calibration_relaxed"]]
        strict = [r for r in obs if r["use_for_calibration_strict"]]
        total = sum(r["rain_ext_mm"] for r in obs) if obs else None
        expected_in_scope = len(rows)
        calendar_n = len(days)
        full_calendar_in_scope = (rows and rows[0]["date"] == days[0] and rows[-1]["date"] == days[-1])
        monthly.append({
            "month": f"{y:04d}-{m:02d}",
            "rain_mm_available": total,
            "calendar_days": calendar_n,
            "n_days_in_scope": expected_in_scope,
            "n_days_observed": len(obs),
            "n_days_strict_100pct": len(strict),
            "n_days_qa_relaxed": len(qa_relaxed),
            "day_coverage": (len(obs)/expected_in_scope if expected_in_scope else None),
            "qa_relaxed_coverage": (len(qa_relaxed)/expected_in_scope if expected_in_scope else None),
            "strict_coverage": (len(strict)/expected_in_scope if expected_in_scope else None),
            "complete_scope_relaxed": (len(obs)==expected_in_scope and len(qa_relaxed)==expected_in_scope),
            "complete_scope_strict": (len(obs)==expected_in_scope and len(strict)==expected_in_scope),
            "complete_calendar_month_strict": bool(full_calendar_in_scope and len(obs)==calendar_n and len(strict)==calendar_n),
            "complete_calendar_month_relaxed": bool(full_calendar_in_scope and len(obs)==calendar_n and len(qa_relaxed)==calendar_n),
            "rain_mm_if_strict_complete": total if bool(full_calendar_in_scope and len(obs)==calendar_n and len(strict)==calendar_n) else None,
            "rain_mm_if_relaxed_complete": total if bool(full_calendar_in_scope and len(obs)==calendar_n and len(qa_relaxed)==calendar_n) else None,
        })

    # Saídas
    write_csv(out/"01_auditoria_arquivos.csv",
              ["source_file","site","serial","raw_mode","interpreted_mode","first_datetime","last_datetime","n_rows","n_precip_numeric","median_step_min","note"],
              [[a.source_file,a.site,a.serial,a.raw_mode,a.interpreted_mode,
                a.first_datetime.isoformat(sep=' ') if a.first_datetime else "",
                a.last_datetime.isoformat(sep=' ') if a.last_datetime else "",
                a.n_rows,a.n_precip_numeric,"" if a.median_step_min is None else round(a.median_step_min,3),a.note]
               for a in audits])

    write_csv(out/"02_registros_normalizados.csv",
              ["site","serial","datetime","hydro_date","rain_mm","raw_value","mode","source_file"],
              [[r.site,r.serial,r.datetime.isoformat(sep=' '),r.hydro_date.isoformat(),round(r.rain_mm,4),
                "" if r.raw_value is None else r.raw_value,r.mode,r.source_file] for r in dedup])

    write_csv(out/"03_precipitacao_diaria_todos_sites.csv",
              ["date","site","serial","rain_mm","coverage","n_slots","expected_slots","modes","sources"],
              [[d["date"].isoformat(),d["site"],d["serial"],round(d["rain_mm"],4),
                round(d["coverage"],4) if d["coverage"] is not None else "",d["n_slots"],d["expected_slots"],d["modes"],d["sources"]]
               for d in daily_site])

    write_csv(out/"04_precipitacao_diaria_pasto_externo.csv",
              ["date","rain_ext_mm","serial","coverage","status",
               "use_for_calibration_strict","use_for_calibration_relaxed","use_for_calibration","note"],
              [[r["date"].isoformat(),"" if r["rain_ext_mm"] is None else round(r["rain_ext_mm"],4),
                r["serial"] or "",round(r["coverage"],4),r["status"],
                r["use_for_calibration_strict"],r["use_for_calibration_relaxed"],r["use_for_calibration"],r["note"]]
               for r in canonical])

    write_csv(out/"05_precipitacao_mensal_pasto_externo.csv",
              ["month","rain_mm_available","calendar_days","n_days_in_scope","n_days_observed",
               "n_days_strict_100pct","n_days_qa_relaxed","day_coverage","strict_coverage","qa_relaxed_coverage",
               "complete_scope_strict","complete_scope_relaxed","complete_calendar_month_strict",
               "complete_calendar_month_relaxed","rain_mm_if_strict_complete","rain_mm_if_relaxed_complete"],
              [[r["month"],"" if r["rain_mm_available"] is None else round(r["rain_mm_available"],4),
                r["calendar_days"],r["n_days_in_scope"],r["n_days_observed"],r["n_days_strict_100pct"],
                r["n_days_qa_relaxed"],round(r["day_coverage"],4),round(r["strict_coverage"],4),
                round(r["qa_relaxed_coverage"],4),r["complete_scope_strict"],r["complete_scope_relaxed"],
                r["complete_calendar_month_strict"],r["complete_calendar_month_relaxed"],
                "" if r["rain_mm_if_strict_complete"] is None else round(r["rain_mm_if_strict_complete"],4),
                "" if r["rain_mm_if_relaxed_complete"] is None else round(r["rain_mm_if_relaxed_complete"],4)]
               for r in monthly])

    write_csv(out/"06_conflitos_duplicatas.csv",
              ["site","serial","datetime","mode","distinct_rain_mm","source_files","chosen_rain_mm","authoritative_source","authoritative_file_end","rule"],
              [[k[0],k[1],k[2].isoformat(sep=' '),k[3],";".join(map(str,vals)),"; ".join(srcs),
                chosen,auth,auth_end.isoformat(sep=' ') if auth_end else "",
                "usar o download que alcança a data/hora mais recente"]
               for k,vals,srcs,chosen,auth,auth_end in resolved_conflicts])

    # O que mudou desde a execução anterior? Útil quando chegam novos RAW a cada ~10 dias.
    current_by_date = {r["date"].isoformat(): r for r in canonical}
    changes = []
    all_dates = sorted(set(previous_daily) | set(current_by_date))
    for ds in all_dates:
        old = previous_daily.get(ds)
        new = current_by_date.get(ds)
        if old is None and new is not None:
            kind = "added"
        elif old is not None and new is None:
            kind = "removed"
        else:
            old_rain = as_float_or_none(old.get("rain_ext_mm"))
            new_rain = new.get("rain_ext_mm")
            same_rain = (old_rain is None and new_rain is None) or (old_rain is not None and new_rain is not None and abs(old_rain-new_rain) < 1e-9)
            same_serial = (old.get("serial", "") or "") == (new.get("serial") or "")
            same_status = (old.get("status", "") or "") == new.get("status", "")
            if same_rain and same_serial and same_status:
                continue
            kind = "changed"
        changes.append([
            ds, kind,
            "" if old is None else old.get("rain_ext_mm", ""),
            "" if new is None or new.get("rain_ext_mm") is None else round(new["rain_ext_mm"],4),
            "" if old is None else old.get("serial", ""),
            "" if new is None else (new.get("serial") or ""),
            "" if old is None else old.get("status", ""),
            "" if new is None else new.get("status", ""),
        ])
    write_csv(out/"08_alteracoes_desde_execucao_anterior.csv",
              ["date","change_type","old_rain_mm","new_rain_mm","old_serial","new_serial","old_status","new_status"],
              changes)

    # Resumo de execução para rastreabilidade.
    now = datetime.now().isoformat(timespec="seconds")
    write_csv(out/"09_resumo_execucao.csv", ["item","value"], [
        ["executed_at_local", now],
        ["input", str(entrada)],
        ["qa_relaxed_threshold", args.qa_relaxed],
        ["tip_resolution_mm", TIP_MM],
        ["n_files_audited", len(audits)],
        ["n_normalized_records", len(dedup)],
        ["n_duplicate_conflicts", len(conflicts)],
        ["n_daily_changes_vs_previous_run", len(changes)],
        ["canonical_start", canonical[0]["date"].isoformat() if canonical else ""],
        ["canonical_start_rule", "first available pasture observation; no fixed global start date"],
        ["canonical_end", canonical[-1]["date"].isoformat() if canonical else ""],
        ["qa_strict_definition", "daily legacy record present OR 96/96 intervals in 15-min sensor"],
        ["qa_relaxed_definition", f"daily legacy record present OR coverage >= {args.qa_relaxed:.0%} in 15-min sensor"],
    ])

    # Transições/lacunas relevantes para a série externa do pasto.
    transitions = [
        ["22376832_pasto_last", "2026-06-27 12:00:00", "último total diário disponível do pluviômetro histórico no pasto"],
        ["pasto_gap_start", "2026-06-28 00:00:00", "início do hiato sem observação externa do pasto nos RAW"],
        ["22376832_cap_first", "2026-07-18 15:00:00", "mesmo serial 22376832 aparece na capoeira após transferência"],
        ["22094687_pasto_first", "2026-07-23 11:00:00", "novo pluviômetro externo do pasto"],
        ["pasto_gap_end", "2026-07-22 23:59:59", "fim do hiato; 23/07 ainda é dia hidrológico parcial"],
        ["22094687_event_mode_first", "2026-08-19 14:00:00", "início do arquivo Evento, mm; acumulado convertido em incrementos"],
    ]
    write_csv(out/"07_transicoes_e_lacunas.csv", ["event","datetime","note"], transitions)

    # Resumo no console
    print("Arquivos auditados:", len(audits))
    print("Registros normalizados/deduplicados:", len(dedup))
    print("Conflitos de duplicatas:", len(conflicts))
    print("Série canônica do pasto:", canonical[0]["date"], "a", canonical[-1]["date"])
    print("\nMensal — pasto externo:")
    for r in monthly:
        print(r)


if __name__ == "__main__":
    main()
