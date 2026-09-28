#!/usr/bin/env python3
from __future__ import annotations
import io, zipfile, urllib.request, re
import pandas as pd
from bs4 import BeautifulSoup

UA="ISTAT-PULSE-GREEN-PROBE/1.0"
TARGETS={
 "ACI":"https://aci.gov.it//app/uploads/2026/05/Annuario-statistico-2026-OD.zip",
 "ARERA":"https://www.arera.it/fileadmin/allegati/dati/idr/RQSII_2021.xlsx",
 "ISPRA_GHG":"https://emissioni.sina.isprambiente.it/wp-content/uploads/2026/04/Emissioni-GHG-Sintesi-2026.xlsx",
 "ISPRA_ELECTRIC":"https://emissioni.sina.isprambiente.it/wp-content/uploads/2026/07/FE_energia_elettrica_2025-V2.xlsx",
 "ISTAT_SDG":"https://www.istat.it/wp-content/uploads/2026/07/Misure-statistiche-2004-2026.xlsx",
 "ISTAT_WATER":"https://www.istat.it/wp-content/uploads/2026/03/Istat-GMA2026-Tavole-1.xlsx",
 "ENEA_LAZIO":"https://www.efficienzaenergetica.enea.it/component/jdownloads/?Itemid=101&catid=40&id=804&task=download.send",
}
def fetch(url):
    req=urllib.request.Request(url,headers={"User-Agent":UA,"Accept":"*/*","Accept-Language":"it-IT,it;q=0.9"})
    with urllib.request.urlopen(req,timeout=180) as r:
        return r.read(),r.geturl(),r.headers.get("Content-Type","")
def show_excel(label,raw):
    try:
        book=pd.ExcelFile(io.BytesIO(raw))
    except Exception as exc:
        print(label,"NOT EXCEL",type(exc).__name__,exc); return
    print(label,"SHEETS",book.sheet_names)
    for sheet in book.sheet_names[:8]:
        try:
            df=pd.read_excel(book,sheet_name=sheet,header=None,nrows=14)
            print("\n",label,"SHEET",sheet,"SHAPE_HEAD",df.shape)
            print(df.fillna("").astype(str).to_string(index=False,header=False,max_cols=18))
        except Exception as exc:
            print(label,sheet,"READ ERROR",exc)
def main():
    for label,url in TARGETS.items():
        print("\n"+"="*88+"\nTARGET",label,url)
        try:
            raw,final,ct=fetch(url)
            print("FINAL",final,"TYPE",ct,"BYTES",len(raw),"MAGIC",raw[:8].hex())
            if raw.startswith(b"PK") and label=="ACI":
                z=zipfile.ZipFile(io.BytesIO(raw))
                names=z.namelist()
                print("ZIP FILES",len(names))
                for n in names[:120]: print(" ",n)
                # inspect first spreadsheet-like member
                for n in names:
                    if n.lower().endswith((".xlsx",".xls",".ods")):
                        b=z.read(n)
                        print("INSPECT MEMBER",n,len(b))
                        show_excel(label+"::"+n,b)
                        break
            else:
                show_excel(label,raw)
        except Exception as exc:
            print("ERROR",label,type(exc).__name__,repr(exc))
if __name__=="__main__":main()
