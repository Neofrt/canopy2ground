#!/usr/bin/env python3
"""Optional migration audit: compare Python daily TMS metrics with an R-generated workbook."""
import argparse
from pathlib import Path
import numpy as np
import pandas as pd


def main():
    ap=argparse.ArgumentParser()
    ap.add_argument("--root",required=True)
    ap.add_argument("--r-xlsx",required=True)
    ap.add_argument("--sheet",default="metricas_diarias")
    args=ap.parse_args()
    py_path=Path(args.root)/"data"/"processed"/"tms"/"tms_diario_hidrologico.csv"
    py=pd.read_csv(py_path);py["date"]=pd.to_datetime(py["date"])
    rr=pd.read_excel(args.r_xlsx,sheet_name=args.sheet,engine="openpyxl")
    rr["date"]=pd.to_datetime(rr["date"])
    cols=[c for c in ["vwc_mean_m3m3","swc_mean_pct","delta_theta_m3m3","delta_theta_pp"] if c in rr.columns and c in py.columns]
    z=py.merge(rr[["date","site","depth_cm"]+cols],on=["date","site","depth_cm"],how="inner",suffixes=("_python","_R"))
    rows=[]
    for c in cols:
        a=z[f"{c}_python"];b=z[f"{c}_R"];ok=a.notna()&b.notna();d=(a[ok]-b[ok])
        rows.append({"variable":c,"n":int(ok.sum()),"bias_python_minus_R":d.mean() if len(d) else np.nan,
                     "mae":d.abs().mean() if len(d) else np.nan,"rmse":np.sqrt(np.mean(d**2)) if len(d) else np.nan,
                     "max_abs_diff":d.abs().max() if len(d) else np.nan,"correlation":a[ok].corr(b[ok]) if ok.sum()>2 else np.nan})
    out=Path(args.root)/"results"/"tms"/"comparacao_python_vs_R.csv";out.parent.mkdir(parents=True,exist_ok=True)
    pd.DataFrame(rows).to_csv(out,index=False,encoding="utf-8-sig")
    print(pd.DataFrame(rows).to_string(index=False));print("\nSalvo em:",out)

if __name__=="__main__":main()
