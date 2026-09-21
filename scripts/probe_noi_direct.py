#!/usr/bin/env python3
import io, zipfile, urllib.request, time, pandas as pd
URL="https://noi-italia.istat.it/documenti/Dati.zip"
def get(url):
    last=None
    for attempt in range(1,6):
        try:
            req=urllib.request.Request(url,headers={"User-Agent":"Mozilla/5.0 ISTAT-PULSE/0.10"})
            with urllib.request.urlopen(req,timeout=150) as r:
                raw=r.read(); print("HTTP",r.status,len(raw),r.url,flush=True); return raw
        except Exception as e:
            last=e; print("retry",attempt,repr(e),flush=True); time.sleep(attempt*5)
    raise last
raw=get(URL)
outer=zipfile.ZipFile(io.BytesIO(raw))
targets=["Sanità e Salute.zip","Istruzione.zip","Condizioni economiche delle famiglie.zip","Ambiente.zip","Mercato del lavoro.zip","Popolazione.zip","Turismo.zip"]
for target in targets:
    nested=zipfile.ZipFile(io.BytesIO(outer.read(target)))
    print("\n### DOMAIN",target,"FILES",nested.namelist(),flush=True)
    for filename in nested.namelist():
        if not filename.lower().endswith(".xlsx"): continue
        data=nested.read(filename)
        xls=pd.ExcelFile(io.BytesIO(data))
        print("## BOOK",filename,"SHEETS",xls.sheet_names,flush=True)
        for sheet in xls.sheet_names[:3]:
            df=pd.read_excel(io.BytesIO(data),sheet_name=sheet,header=None,nrows=12,dtype=str)
            print("# SHEET",sheet,"shape",df.shape,flush=True)
            print(df.iloc[:12,:14].fillna("").to_string(index=False,header=False),flush=True)
