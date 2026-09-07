#!/usr/bin/env python3
from __future__ import annotations
import argparse, json, re
from pathlib import Path
import numpy as np
import pandas as pd

SITE_DIRS={"PASTO":"pasto","SECUNDARIA":"cap"}
DT_RE=re.compile(r"^(\d{2})/(\d{2})/(\d{2})\s+(\d{1,2})H(\d+)min(\d+)s$",re.I)

def parse_dt(v):
    m=DT_RE.match(str(v).strip())
    if not m: return pd.NaT
    d,mn,y,h,mi,s=map(int,m.groups())
    try:return pd.Timestamp(year=2000+y,month=mn,day=d,hour=h,minute=mi,second=s)
    except:return pd.NaT

def find_col(cols, patterns):
    for c in cols:
        lo=str(c).lower()
        if all(p.lower() in lo for p in patterns): return c
    return None

def serial_from_cols(cols):
    m=re.search(r"LGR S/N:\s*(\d+)"," | ".join(map(str,cols)))
    return m.group(1) if m else None

def read_one(path:Path,site:str):
    try:x=pd.read_csv(path,skiprows=1,encoding="utf-8-sig")
    except UnicodeDecodeError:x=pd.read_csv(path,skiprows=1,encoding="latin1")
    except Exception as e:return None,{"site":site,"file":str(path),"status":"unreadable","note":str(e)}
    cols=list(x.columns); cdt=find_col(cols,["data hora"])
    cp=find_col(cols,["press","kpa"]) or find_col(cols,["pres.","kpa"])
    ct=find_col(cols,["temp","°c"])
    if cdt is None or cp is None:
        return None,{"site":site,"file":str(path),"status":"ignored_missing_datetime_pressure","note":""}
    dt=x[cdt].map(parse_dt)
    serial=serial_from_cols(cols)
    out=pd.DataFrame({"site":site,"serial":serial,"datetime":dt,
                      "pressure_abs_kPa":pd.to_numeric(x[cp],errors="coerce"),
                      "temperature_C":pd.to_numeric(x[ct],errors="coerce") if ct else np.nan,
                      "source_file":str(path)})
    out=out[out["datetime"].notna()].copy()
    meas=out[out["pressure_abs_kPa"].notna()].copy()
    if meas.empty:return None,{"site":site,"file":str(path),"status":"no_measurements","serial":serial}
    nuniq=meas["datetime"].nunique(); ratio=nuniq/len(meas)
    # A valid logger series should have mostly unique measurement timestamps.
    structurally_valid=(ratio>=0.90 or len(meas)<10)
    out["file_end"]=meas["datetime"].max(); out["source_valid_datetime_structure"]=structurally_valid
    dif=meas["datetime"].sort_values().drop_duplicates().diff().dropna().dt.total_seconds()/60
    step=float(dif[(dif>0)&(dif<=120)].mode().iloc[0]) if len(dif[(dif>0)&(dif<=120)]) else np.nan
    audit={"site":site,"file":str(path),"serial":serial,"status":"ok" if structurally_valid else "excluded_invalid_datetime_structure",
           "start":meas["datetime"].min(),"end":meas["datetime"].max(),"n_measurements":len(meas),
           "unique_datetime_fraction":ratio,"native_resolution_minutes":step,
           "pressure_min_kPa":meas["pressure_abs_kPa"].min(),"pressure_max_kPa":meas["pressure_abs_kPa"].max()}
    return out,audit

def discover(root):
    out=[]
    for folder,site in SITE_DIRS.items():
        d=root/"data"/"raw"/folder/"Poço"
        if d.exists():out += [(p,site) for p in d.rglob("*.csv")]
    return sorted(out,key=lambda z:str(z[0]).lower())

def process(root:Path,config_path:Path):
    cfg=json.loads(config_path.read_text(encoding="utf-8"))
    frames=[];audits=[]
    for p,site in discover(root):
        d,a=read_one(p,site);audits.append(a)
        if d is not None and bool(d["source_valid_datetime_structure"].iloc[0]):frames.append(d)
    if not frames:raise RuntimeError("Nenhum RAW válido de Poço encontrado.")
    native=pd.concat(frames,ignore_index=True)
    # Cumulative downloads: file reaching furthest in time wins for same site+serial+timestamp.
    native=native.sort_values(["site","serial","datetime","file_end","source_file"],ascending=[True,True,True,False,False])
    native=native.drop_duplicates(["site","serial","datetime"],keep="first").sort_values(["site","datetime"])
    native["pressure_change_kPa"]=native.groupby(["site","serial"])["pressure_abs_kPa"].diff()
    native["temp_change_C"]=native.groupby(["site","serial"])["temperature_C"].diff()
    native["qa_abrupt_pressure_change"]=native["pressure_change_kPa"].abs()>20
    native["qa_possible_out_of_water"]=native["pressure_abs_kPa"].between(90,110) & (native["temp_change_C"].abs()>2)
    native["qa_review"]=native["qa_abrupt_pressure_change"]|native["qa_possible_out_of_water"]

    meas=native[native["pressure_abs_kPa"].notna()].copy()
    meas["datetime_30min"]=meas["datetime"].dt.floor("30min")
    long30=meas.groupby(["site","serial","datetime_30min"],as_index=False).agg(
        pressure_abs_kPa=("pressure_abs_kPa","mean"),temperature_C=("temperature_C","mean"),
        pressure_min_kPa=("pressure_abs_kPa","min"),pressure_max_kPa=("pressure_abs_kPa","max"),
        qa_review=("qa_review","max"),n_native=("datetime","count")
    ).rename(columns={"datetime_30min":"datetime"})
    long30["date"]=long30["datetime"].dt.date

    daily=long30.groupby(["date","site","serial"],as_index=False).agg(
        pressure_abs_mean_kPa=("pressure_abs_kPa","mean"),pressure_abs_min_kPa=("pressure_abs_kPa","min"),
        pressure_abs_max_kPa=("pressure_abs_kPa","max"),temperature_mean_C=("temperature_C","mean"),
        n_30min=("datetime","count"),qa_review_any=("qa_review","max")
    )
    # Relative pressure change can be examined before barometric compensation, but is not water-table depth.
    daily=daily.sort_values(["site","date"])
    daily["delta_pressure_abs_kPa"]=daily.groupby("site")["pressure_abs_mean_kPa"].diff()

    proc=root/"data"/"processed"/"poco";res=root/"results"/"poco";proc.mkdir(parents=True,exist_ok=True);res.mkdir(parents=True,exist_ok=True)
    native.drop(columns=["file_end"]).to_csv(proc/"pocos_native.csv",index=False,encoding="utf-8-sig")
    long30.to_csv(proc/"pocos_30min.csv",index=False,encoding="utf-8-sig")
    daily.to_csv(proc/"pocos_diario_pressao_absoluta.csv",index=False,encoding="utf-8-sig")
    pd.DataFrame(audits).to_csv(res/"inventario_arquivos_pocos.csv",index=False,encoding="utf-8-sig")
    native[native["qa_review"]].drop(columns=["file_end"]).to_csv(res/"qa_revisar_pocos.csv",index=False,encoding="utf-8-sig")
    # Configuration reminder: do not compute water table from provisional total well depths.
    notes=[]
    for site,z in cfg.get("wells",{}).items():
        notes.append({"site":site,"reported_well_depth_m":z.get("reported_well_depth_m"),"depth_status":z.get("depth_status"),
                      "sensor_depth_below_ground_m":z.get("sensor_depth_below_ground_m"),
                      "water_table_depth_computed":False,
                      "reason":"requires barometric compensation and confirmed sensor depth"})
    pd.DataFrame(notes).to_csv(res/"estado_calibracao_pocos.csv",index=False,encoding="utf-8-sig")
    return {"native":native,"long30":long30,"daily":daily,"audits":pd.DataFrame(audits)}

def main():
    ap=argparse.ArgumentParser();ap.add_argument("--root",required=True);ap.add_argument("--config",required=True);a=ap.parse_args()
    r=process(Path(a.root),Path(a.config));print(f"Poços: {len(r['native']):,} registros normalizados; {len(r['long30']):,} registros de 30 min.")
if __name__=="__main__":main()
