#!/usr/bin/env python3
import io, urllib.request, pandas as pd, json
UA={"User-Agent":"ISTAT-PULSE-GREEN/diagnostic"}
def get(url):
    with urllib.request.urlopen(urllib.request.Request(url,headers=UA),timeout=120) as r:return r.read()
print("### RIFIUTI")
raw=get("https://www.catasto-rifiuti.isprambiente.it/get/getDettaglioComunale.csv.php?&aa=2024")
text=raw.decode("utf-8-sig","replace")
print(repr(text[:1200]))
for skip in [0,1,2,3]:
    try:
        d=pd.read_csv(io.StringIO(text),sep=";",skiprows=skip,nrows=4,dtype=str)
        print("SKIP",skip,"SHAPE",d.shape)
        print(json.dumps(list(d.columns),ensure_ascii=False))
        print(d.head(2).to_string(index=False,max_cols=60))
    except Exception as e:print("RERR",skip,repr(e))

for label,url in [
 ("NO2","https://indicatoriambientali.isprambiente.it/sites/default/files/indicatori_ambientali/2025-12-12/TABELLA_4_NO2_TREND%20%282015-2024%29.xlsx"),
 ("PM25","https://indicatoriambientali.isprambiente.it/sites/default/files/indicatori_ambientali/2025-12-10/TABELLA_3_PM25_TREND%20%282015-2024%29_rev.xlsx"),
]:
 print("\\n###",label)
 raw=get(url); x=pd.ExcelFile(io.BytesIO(raw),engine="openpyxl")
 print("SHEETS",x.sheet_names)
 for sh in x.sheet_names[:8]:
   d=pd.read_excel(io.BytesIO(raw),sheet_name=sh,header=None,engine="openpyxl",nrows=20)
   print("--",sh,d.shape)
   print(d.to_string(index=False,header=False,max_cols=30,max_colwidth=80))
