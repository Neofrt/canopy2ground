#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import re
from pathlib import Path
import numpy as np
import pandas as pd

SITE_DIRS = {"PASTO": "pasto", "SECUNDARIA": "cap", "PRIMARIA": "ref"}


def load_config(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


def position_from_name(path: Path):
    m = re.match(r"^0?([123])(?:_|\s|$)", path.name)
    return f"{int(m.group(1)):02d}" if m else None


def parse_datetime_utc_local(series, timezone):
    """Parse TOMST timestamps as UTC and convert explicitly to project local time.

    ``tz_q`` is kept separately as audit metadata and is never used to shift
    the timestamp. This prevents stale logger timezone settings from silently
    changing the scientific time axis.
    """
    s = series.astype(str).str.strip()
    parsed = pd.to_datetime(s, format="%d.%m.%Y %H:%M", errors="coerce")
    miss = parsed.isna()
    if miss.any():
        parsed.loc[miss] = pd.to_datetime(
            s.loc[miss], format="%Y.%m.%d %H:%M", errors="coerce"
        )
    utc = parsed.dt.tz_localize("UTC")
    local_aware = utc.dt.tz_convert(timezone)
    local = local_aware.dt.tz_localize(None)
    expected_offset_hours = local_aware.map(
        lambda x: np.nan if pd.isna(x) else x.utcoffset().total_seconds() / 3600.0
    )
    return utc, local, expected_offset_hours

def parse_one_datetime(text):
    s=str(text).strip()
    for fmt in ("%d.%m.%Y %H:%M","%Y.%m.%d %H:%M"):
        try: return pd.Timestamp(pd.to_datetime(s,format=fmt))
        except Exception: pass
    return pd.NaT

def quick_interval(path: Path):
    """Read first/last non-empty lines without loading the full cumulative TMS file."""
    try:
        with path.open("r",encoding="utf-8",errors="replace") as f:
            first=None
            for line in f:
                if line.strip(): first=line.strip(); break
        with path.open("rb") as f:
            f.seek(0,2); pos=f.tell(); buf=b""
            while pos>0 and buf.count(b"\n")<3:
                step=min(8192,pos);pos-=step;f.seek(pos);buf=f.read(step)+buf
            lines=[z.decode("utf-8",errors="replace").strip() for z in buf.splitlines() if z.strip()]
            last=lines[-1] if lines else None
        def getdt(line):
            if not line:return pd.NaT
            parts=line.split(";")
            return parse_one_datetime(parts[1]) if len(parts)>1 else pd.NaT
        return getdt(first),getdt(last)
    except Exception:
        return pd.NaT,pd.NaT


def read_one(path: Path, site: str, timezone: str):
    pos = position_from_name(path)
    if pos is None:
        return None, {"site": site, "file": str(path), "status": "ignored_position_unknown"}
    try:
        x = pd.read_csv(path, sep=";", header=None, encoding="utf-8", engine="python")
    except UnicodeDecodeError:
        x = pd.read_csv(path, sep=";", header=None, encoding="latin1", engine="python")
    except Exception as e:
        return None, {"site": site, "file": str(path), "status": "unreadable", "note": str(e)}
    # Trailing delimiter may create empty column. Drop fully empty columns.
    x = x.dropna(axis=1, how="all")
    ncol = x.shape[1]
    if ncol >= 9:
        x = x.iloc[:, :9].copy()
        x.columns = ["idx","datetime_txt","tz_q","TMS_T1","TMS_T2","TMS_T3","TMS_moist","shake","err"]
        fmt = 9
    elif ncol >= 8:
        x = x.iloc[:, :8].copy()
        x.columns = ["idx","datetime_txt","TMS_T1","TMS_T2","TMS_T3","TMS_moist","shake","err"]
        x["tz_q"] = np.nan
        fmt = 8
    else:
        return None, {"site": site, "file": str(path), "status": "ignored_columns", "ncol": ncol}
    dt_utc, dt_local, expected_offset_hours = parse_datetime_utc_local(x["datetime_txt"], timezone)
    tz_q_num = pd.to_numeric(x["tz_q"], errors="coerce")
    out = pd.DataFrame({
        "site": site, "position": pos,
        "datetime_utc": dt_utc,
        "datetime": dt_local,
        "tz_q": tz_q_num,
        "tz_offset_reported_hours": tz_q_num / 4.0,
        "TMS_T1": pd.to_numeric(x["TMS_T1"], errors="coerce"),
        "TMS_T2": pd.to_numeric(x["TMS_T2"], errors="coerce"),
        "TMS_T3": pd.to_numeric(x["TMS_T3"], errors="coerce"),
        "TMS_moist": pd.to_numeric(x["TMS_moist"], errors="coerce"),
        "err": pd.to_numeric(x["err"], errors="coerce"),
        "format_ncol": fmt, "source_file": str(path)
    })
    out = out[out["datetime"].notna()].copy()
    out["tz_offset_expected_hours"] = expected_offset_hours.loc[out.index].to_numpy()
    out["tz_reported_matches_project"] = pd.array(
        [
            pd.NA if pd.isna(rep) or pd.isna(exp) else bool(np.isclose(rep, exp))
            for rep, exp in zip(out["tz_offset_reported_hours"], out["tz_offset_expected_hours"])
        ],
        dtype="boolean",
    )
    out["timezone_conversion"] = f"UTC->{timezone}"
    if out.empty:
        return None, {"site": site, "file": str(path), "status": "no_valid_datetime", "ncol": ncol}
    out["file_end"] = out["datetime"].max()
    diffs = out["datetime"].sort_values().drop_duplicates().diff().dropna().dt.total_seconds()/60
    step = float(diffs.mode().iloc[0]) if len(diffs) else np.nan
    tzvals = sorted(out["tz_q"].dropna().unique().tolist())
    tzhrs = sorted(out["tz_offset_reported_hours"].dropna().unique().tolist())
    return out, {
        "site": site, "position": pos, "file": str(path), "status": "ok", "format_ncol": fmt,
        "start_local": out["datetime"].min(), "end_local": out["datetime"].max(), "n_rows": len(out),
        "native_resolution_minutes": step,
        "raw_timestamp_basis": "UTC",
        "project_timezone": timezone,
        "tz_q_values": ",".join(str(v) for v in tzvals) if tzvals else "",
        "tz_offset_reported_hours": ",".join(str(v) for v in tzhrs) if tzhrs else "",
        "timezone_note": "tz_q is audit metadata only; UTC timestamp converted explicitly to project timezone"
    }


def discover(root: Path, target_start=None):
    """Select the minimal cumulative RAW set needed to cover the project period.

    TMS downloads are cumulative within deployments; reading every historical copy is
    unnecessary and slow. If a future reset creates a new non-overlapping deployment,
    this selector keeps additional older files to preserve coverage.
    """
    candidates=[]
    for folder, site in SITE_DIRS.items():
        d=root/"data"/"raw"/folder/"TMS"
        if not d.exists():continue
        for p in d.rglob("*.csv"):
            pos=position_from_name(p)
            if pos is None:continue
            st,en=quick_interval(p)
            if pd.isna(en):continue
            candidates.append({"path":p,"site":site,"position":pos,"start":st,"end":en,"size":p.stat().st_size})
    selected=[];selection_audits=[]
    if not candidates:
        return [], pd.DataFrame(columns=[
            "site", "position", "file", "selection_status",
            "quick_start", "quick_end", "size_bytes"
        ])
    for (site,pos),arr_df in pd.DataFrame(candidates).groupby(["site","position"]):
        arr=arr_df.sort_values(["end","size"],ascending=[False,False]).to_dict("records")
        if not arr:continue
        chosen=[arr[0]];coverage_start=arr[0]["start"]
        remaining=arr[1:]
        while target_start is not None and (pd.isna(coverage_start) or coverage_start>target_start):
            overlap=[z for z in remaining if pd.notna(z["start"]) and z["start"]<coverage_start and z["end"]>=coverage_start-pd.Timedelta(days=1)]
            if overlap:
                z=min(overlap,key=lambda q:q["start"])
            else:
                older=[z for z in remaining if z["end"]<coverage_start]
                if not older:break
                z=max(older,key=lambda q:q["end"])
            chosen.append(z);remaining.remove(z);coverage_start=min(coverage_start,z["start"])
        chosen_paths={z["path"] for z in chosen}
        selected += [(z["path"],z["site"]) for z in chosen]
        for z in arr:
            selection_audits.append({"site":site,"position":pos,"file":str(z["path"]),
                                     "selection_status":"selected_cumulative_coverage" if z["path"] in chosen_paths else "skipped_redundant_cumulative",
                                     "quick_start":z["start"],"quick_end":z["end"],"size_bytes":z["size"]})
    return sorted(selected,key=lambda z:str(z[0]).lower()),pd.DataFrame(selection_audits)


def infer_step_minutes(g):
    diffs = g["datetime"].sort_values().drop_duplicates().diff().dropna().dt.total_seconds()/60
    if diffs.empty: return 10.0
    good=diffs[(diffs>0)&(diffs<=60)]
    return float(good.mode().iloc[0]) if len(good) else 10.0


def add_offsoil_and_vwc(g: pd.DataFrame, coeff: dict):
    g=g.sort_values("datetime").copy()
    step=infer_step_minutes(g)
    per_day=max(1,int(round(1440/step)))
    w1=per_day+1
    sd1=g["TMS_T1"].rolling(w1, center=True, min_periods=max(3,int(w1*0.7))).std()
    sd2=g["TMS_T2"].rolling(w1, center=True, min_periods=max(3,int(w1*0.7))).std()
    sdt12=sd1/sd2
    minmoist=g["TMS_moist"].rolling(w1, center=True, min_periods=max(3,int(w1*0.7))).min()
    # myClim TMS off-soil logic: 1 = off soil, 0 = in soil.
    off_raw=np.where((np.isfinite(sdt12) & (sdt12 < 0.76085)), 0,
                     np.where(minmoist >= 721.5, 0, 1)).astype(float)
    smooth_window=10*per_day+1
    smooth=pd.Series(off_raw,index=g.index).rolling(smooth_window,center=True,min_periods=max(3,int(smooth_window*0.5))).mean()
    off=np.where(smooth.notna(), (smooth>=0.5).astype(float), off_raw)
    g["off_soil"] = off

    raw=g["TMS_moist"].astype(float)
    temp=g["TMS_T1"].astype(float)
    a=float(coeff["a"]); b=float(coeff["b"]); c=float(coeff["c"])
    ref=float(coeff["reference_temperature_C"])
    acor=float(coeff["air_temperature_correction"]); wcor=float(coeff["water_temperature_correction"])
    v0=a*raw**2+b*raw+c
    dcor=wcor-acor
    tcor=raw + (ref-temp)*(acor+dcor*v0)
    v=a*tcor**2+b*tcor+c
    v=v.clip(lower=0, upper=1)
    # Frozen values and off-soil values are not valid VWC.
    v=v.where(temp>=0)
    v=v.where(g["off_soil"] != 1)
    g["tms_signal"] = raw
    g["vwc_m3m3_raw_formula"] = (a*tcor**2+b*tcor+c)
    g["vwc_m3m3"] = v
    g["swc_pct"] = 100*v
    g["soil_temp_C"] = temp
    g["native_step_minutes"] = step
    return g


def hydro_date_from_datetime(s):
    # 12:00 belongs to the day that closes at 12:00; >12:00 goes to next day.
    dates=s.dt.normalize()
    after_noon=(s.dt.hour>12)|((s.dt.hour==12)&((s.dt.minute>0)|(s.dt.second>0)))
    return (dates + pd.to_timedelta(after_noon.astype(int), unit="D")).dt.date


def process(root: Path, config_path: Path):
    cfg=load_config(config_path)
    inv=pd.DataFrame(cfg["tms"]["inventory"])
    inv["position"]=inv["position"].astype(str).str.zfill(2)
    inv["depth_cm"]=(inv["depth_m"]*100).round().astype(int)
    inv["tms_id"]=inv["site"]+"_"+inv["position"]
    if inv.duplicated(["site", "position"]).any():
        dup = inv.loc[inv.duplicated(["site", "position"], keep=False), ["site", "position"]]
        raise RuntimeError(
            "Configuração TMS inválida: site+position deve ser único. "
            f"Duplicatas: {dup.drop_duplicates().to_dict('records')}"
        )
    coeff=cfg["tms"]["universal_vwc_coefficients"]
    min_daily=int(cfg.get("hydrologic_day",{}).get("min_intervals_tms",39))
    ref100_start=pd.Timestamp(cfg["tms"]["ref_100cm_valid_from"])
    timezone = cfg.get("timezone", "America/Belem")

    frames=[]; audits=[]
    # Use the full temporal coverage available in the selected cumulative RAW
    # files; no arbitrary global analysis start date is imposed here.
    selected_files, selection_audit = discover(root, None)
    for p,site in selected_files:
        d,a=read_one(p,site,timezone); audits.append(a)
        if d is not None: frames.append(d)
    if not frames:
        raise RuntimeError(
            "Nenhum RAW TMS válido encontrado. Verifique data/raw/<SITE>/TMS, "
            "nomes iniciados por 1_, 2_ ou 3_ e o formato CSV TOMST."
        )
    base=pd.concat(frames,ignore_index=True)
    base=base.merge(
        inv[["site","position","depth_m","depth_cm","serial","tms_id"]],
        on=["site","position"], how="left", validate="many_to_one"
    )
    unmapped = base[base["tms_id"].isna()][["site", "position"]].drop_duplicates()
    if not unmapped.empty:
        raise RuntimeError(
            "Há arquivos TMS sem mapeamento no project_config.json: "
            f"{unmapped.to_dict('records')}"
        )
    base["ok_err"] = base["err"].isna() | base["err"].eq(0)
    # Prefer valid errors, richer format and the cumulative download extending furthest in time.
    base=base.sort_values(["tms_id","datetime","ok_err","format_ncol","file_end","source_file"], ascending=[True,True,False,False,False,False])
    base=base.drop_duplicates(["tms_id","datetime"],keep="first")
    base=base[base["ok_err"] & base["tms_id"].notna()].copy()

    processed_parts=[]
    for _,g in base.groupby("tms_id",sort=False):
        if not g.empty:
            processed_parts.append(add_offsoil_and_vwc(g,coeff))
    if not processed_parts:
        raise RuntimeError("TMS: nenhum registro permaneceu após validação de erro e inventário.")
    native=pd.concat(processed_parts,ignore_index=True).sort_values(["site","depth_cm","datetime"])

    # 30-min central grid after VWC conversion, as in the original R pipeline.
    x=native.copy(); x["datetime_30min"]=x["datetime"].dt.floor("30min")
    long30=x.groupby(["site","depth_cm","depth_m","serial","datetime_30min"],as_index=False).agg(
        tms_signal=("tms_signal","mean"), vwc_m3m3=("vwc_m3m3","mean"), swc_pct=("swc_pct","mean"),
        soil_temp_C=("soil_temp_C","mean"), off_soil_fraction=("off_soil","mean"), n_native=("datetime","count")
    ).rename(columns={"datetime_30min":"datetime"})
    long30["date"]=long30["datetime"].dt.date
    long30["hydro_date"]=hydro_date_from_datetime(long30["datetime"])
    long30["periodo_luz"]=(long30["datetime"].dt.hour>=6)&(long30["datetime"].dt.hour<18)
    long30["qa_tms_valido"]=~((long30["site"]=="ref")&(long30["depth_cm"]==100)&(long30["datetime"]<ref100_start))
    for c in ["tms_signal","vwc_m3m3","swc_pct","soil_temp_C"]:
        long30.loc[~long30["qa_tms_valido"],c]=np.nan

    # Daily hydrologic SWC and delta-theta.
    rows=[]
    daily_source=long30.copy()
    for (site,depth,dm,hdate),g in daily_source.groupby(["site","depth_cm","depth_m","hydro_date"]):
        n=int(g["vwc_m3m3"].notna().sum())
        valid=n>=min_daily
        rows.append({
            "date":hdate,"site":site,"depth_cm":depth,"depth_m":dm,"n_vwc":n,
            "tms_signal_mean":g["tms_signal"].mean() if valid else np.nan,
            "vwc_mean_m3m3":g["vwc_m3m3"].mean() if valid else np.nan,
            "swc_mean_pct":g["swc_pct"].mean() if valid else np.nan,
            "qa_tms_daily":"ok" if valid else "insufficient_coverage"
        })
    daily=pd.DataFrame(rows).sort_values(["site","depth_cm","date"])
    daily["delta_theta_m3m3"]=daily.groupby(["site","depth_cm"])["vwc_mean_m3m3"].diff()
    daily["delta_theta_pp"]=100*daily["delta_theta_m3m3"]
    # Descriptive event classification only. Large changes are retained as
    # potential ecohydrological responses and are never removed automatically.
    dth = daily["delta_theta_m3m3"]
    daily["delta_theta_event_class"] = np.select(
        [dth > 0.10, dth < -0.10, dth.isna()],
        ["large_wetting", "large_drying", "not_available"],
        default="ordinary"
    )

    # Light-period soil temperature summary.
    light_min=int(cfg.get("light_period",{}).get("min_intervals_daily",20))
    temp_rows=[]
    luz=daily_source[daily_source["periodo_luz"]]
    for (site,depth,date),g in luz.groupby(["site","depth_cm","date"]):
        n=int(g["soil_temp_C"].notna().sum())
        temp_rows.append({"date":date,"site":site,"depth_cm":depth,"n_soiltemp_luz":n,
                          "soil_temp_luz_C":g["soil_temp_C"].mean() if n>=light_min else np.nan})
    soil_light=pd.DataFrame(temp_rows)
    if not soil_light.empty:
        if soil_light.duplicated(["date", "site", "depth_cm"]).any():
            raise RuntimeError("TMS: duplicatas inesperadas no resumo de temperatura do solo 06-18 h.")
        daily=daily.merge(
            soil_light,on=["date","site","depth_cm"],how="left",validate="one_to_one"
        )

    processed=root/"data"/"processed"/"tms"; results=root/"results"/"tms"
    processed.mkdir(parents=True,exist_ok=True); results.mkdir(parents=True,exist_ok=True)
    native.drop(columns=["file_end"]).to_csv(processed/"tms_native.csv",index=False,encoding="utf-8-sig")
    long30.to_csv(processed/"tms_30min_long.csv",index=False,encoding="utf-8-sig")
    daily.to_csv(processed/"tms_diario_hidrologico.csv",index=False,encoding="utf-8-sig")
    pd.DataFrame(audits).to_csv(results/"inventario_arquivos_tms.csv",index=False,encoding="utf-8-sig")
    selection_audit.to_csv(results/"auditoria_selecao_downloads_tms.csv",index=False,encoding="utf-8-sig")
    inv.to_csv(results/"inventario_sensores_tms.csv",index=False,encoding="utf-8-sig")

    wide=long30.pivot(index="datetime",columns=["site","depth_cm"],values=["tms_signal","vwc_m3m3","swc_pct","soil_temp_C"])
    wide.columns=[f"{site}_{int(depth):03d}_{var}" for var,site,depth in wide.columns]
    wide=wide.reset_index().sort_values("datetime")
    wide.to_csv(processed/"tms_30min_wide.csv",index=False,encoding="utf-8-sig")
    return {"native":native,"long30":long30,"wide30":wide,"daily":daily,"audits":pd.DataFrame(audits),"inventory":inv}


def main():
    ap=argparse.ArgumentParser(); ap.add_argument("--root",required=True); ap.add_argument("--config",required=True)
    a=ap.parse_args(); r=process(Path(a.root),Path(a.config))
    print(f"TMS: {len(r['native']):,} registros nativos; {len(r['long30']):,} registros de 30 min; {len(r['daily']):,} resumos diários.")

if __name__=="__main__": main()
