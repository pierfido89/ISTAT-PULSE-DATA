#!/usr/bin/env python3
from __future__ import annotations
import io, json, re, zipfile, urllib.request, tempfile
from pathlib import Path
import pandas as pd
from bs4 import BeautifulSoup

UA={"User-Agent":"Mozilla/5.0 ISTAT-PULSE-GREEN/0.2","Accept":"*/*"}

TARGETS={
 "ARERA_2021":"https://www.arera.it/fileadmin/allegati/dati/idr/RQSII_2021.xlsx",
 "ENEA_LAZIO":"https://www.efficienzaenergetica.enea.it/component/jdownloads/?task=download.send&id=804&catid=40&Itemid=101",
 "ISPRA_SUOLO":"https://www.isprambiente.gov.it/it/attivita/suolo-e-territorio/suolo/il-consumo-di-suolo/consumo_di_suolo_estratto_dati_2025_anni_2006_2024.xlsx",
 "ISPRA_BIODIV1":"https://indicatoriambientali.isprambiente.it/sites/default/files/indicatori_ambientali/2026-06-12/TAB%201_specie%20DH.xlsx",
 "BIGBANG_IT":"https://groupware.sinanet.isprambiente.it/bigbang-data/library/bigbang100/excel_tables/bigbang100_tables_italy_01/download/en/1/BIGBANG100_TABLES_ITALY_01.xlsx",
 "BIGBANG_REG":"https://groupware.sinanet.isprambiente.it/bigbang-data/library/bigbang100/excel_tables/bigbang100_tables_regions_02/download/en/1/BIGBANG100_TABLES_REGIONS_02.xlsx",
 "ISTAT_SDG":"https://www.istat.it/wp-content/uploads/2026/07/Misure-statistiche-2004-2026.xlsx",
 "ISTAT_SDG_META":"https://www.istat.it/wp-content/uploads/2026/07/Metadati-SDGs.xlsx",
 "ISTAT_AMBURB":"https://www.istat.it/wp-content/uploads/2026/09/TAVOLE_AMBURB_2024.zip",
 "ISTAT_ACQUA":"https://www.istat.it/wp-content/uploads/2026/03/Istat-GMA2026-Tavole-1.xlsx",
 "EEA_GHG":"https://www.eea.europa.eu/en/europe-environment-2025/countries/data-download/ee25-total-greenhouse-gas-emissions-all-eea38-countries.csv",
 "EEA_REN":"https://www.eea.europa.eu/en/europe-environment-2025/countries/data-download/ee25-renewable-energy-sources-all-eea38-countries.csv",
 "EEA_CIRC":"https://www.eea.europa.eu/en/europe-environment-2025/countries/data-download/ee25-circular-material-use-rate-all-eea38-countries.csv",
 "EEA_PROTECTED":"https://www.eea.europa.eu/en/europe-environment-2025/countries/data-download/ee25-terrestrial-protected-areas-all-eea38-countries.csv",
 "EEA_AIR":"https://www.eea.europa.eu/en/europe-environment-2025/countries/data-download/ee25-health-impacts-of-air-pollution-all-eea38-countries.csv",
 "EEA_WASTE":"https://www.eea.europa.eu/en/europe-environment-2025/countries/data-download/ee25-waste-generation-all-eea38-countries.csv",
}

def get(url):
    req=urllib.request.Request(url,headers=UA)
    with urllib.request.urlopen(req,timeout=120) as r:
        return r.read(),r.geturl(),r.headers.get_content_type()

def print_df(df,n=8):
    print("SHAPE",df.shape)
    print("COLS",json.dumps([str(c) for c in df.columns],ensure_ascii=False))
    print(df.head(n).to_string(index=False,max_cols=24,max_colwidth=60))

def inspect_bytes(name,raw,final,ctype):
    print("\n### FILE",name,len(raw),ctype,final,raw[:12])
    low=final.lower()
    if raw[:2]==b"PK" or low.endswith((".xlsx",".zip")):
        z=zipfile.ZipFile(io.BytesIO(raw))
        names=z.namelist()
        xlsx_inside=[n for n in names if n.lower().endswith((".xlsx",".xls",".ods",".csv"))]
        # XLSX itself has xl/workbook.xml
        if "xl/workbook.xml" in names:
            xls=pd.ExcelFile(io.BytesIO(raw),engine="openpyxl")
            print("SHEETS",json.dumps(xls.sheet_names,ensure_ascii=False))
            for sheet in xls.sheet_names[:12]:
                try:
                    df=pd.read_excel(io.BytesIO(raw),sheet_name=sheet,header=None,engine="openpyxl",nrows=12)
                    print("--SHEET",sheet,df.shape)
                    print(df.to_string(index=False,header=False,max_cols=18,max_colwidth=50))
                except Exception as e: print("SHEETERR",sheet,repr(e))
        else:
            print("ZIP CONTENT",json.dumps(names[:80],ensure_ascii=False))
            for member in xlsx_inside[:20]:
                print("MEMBER",member)
                b=z.read(member)
                try:
                    if member.lower().endswith(".xlsx"):
                        xls=pd.ExcelFile(io.BytesIO(b),engine="openpyxl")
                        print("  SHEETS",xls.sheet_names)
                        for sh in xls.sheet_names[:3]:
                            df=pd.read_excel(io.BytesIO(b),sheet_name=sh,header=None,engine="openpyxl",nrows=8)
                            print(df.to_string(index=False,header=False,max_cols=14,max_colwidth=45))
                    elif member.lower().endswith(".csv"):
                        df=pd.read_csv(io.BytesIO(b),sep=None,engine="python",nrows=10)
                        print_df(df)
                except Exception as e: print("  MEMBERERR",repr(e))
    elif "csv" in ctype or low.endswith(".csv"):
        df=pd.read_csv(io.BytesIO(raw),sep=None,engine="python")
        print_df(df,10)
    else:
        # Try legacy Excel
        try:
            df=pd.read_excel(io.BytesIO(raw),sheet_name=None,header=None,engine="xlrd")
            print("LEGACY SHEETS",list(df))
            for sh,x in list(df.items())[:8]:
                print("--SHEET",sh,x.shape)
                print(x.head(10).to_string(index=False,header=False,max_cols=16,max_colwidth=50))
        except Exception as e: print("UNPARSED",repr(e))

def inspect_aci():
    url="https://aci.gov.it//app/uploads/2026/05/Annuario-statistico-2026-OD.zip"
    raw,final,ctype=get(url)
    print("\n### ACI ZIP",len(raw),final)
    z=zipfile.ZipFile(io.BytesIO(raw))
    names=z.namelist()
    print("CONTENT",json.dumps(names[:100],ensure_ascii=False))
    for n in names:
        if n.lower().endswith((".ods",".xlsx",".xls",".csv")) and any(k in n.lower() for k in ["parco","aliment","autovett","immatric","consisten","veic"]):
            print("CANDIDATE",n)
            b=z.read(n)
            try:
                with tempfile.NamedTemporaryFile(suffix=Path(n).suffix) as tmp:
                    tmp.write(b); tmp.flush()
                    xls=pd.ExcelFile(tmp.name,engine="odf" if n.lower().endswith(".ods") else None)
                    print("SHEETS",xls.sheet_names[:20])
                    for sh in xls.sheet_names[:3]:
                        df=pd.read_excel(tmp.name,sheet_name=sh,header=None,engine="odf" if n.lower().endswith(".ods") else None,nrows=10)
                        print(df.to_string(index=False,header=False,max_cols=18,max_colwidth=45))
            except Exception as e: print("ACIERR",repr(e))

def inspect_rifiuti_page():
    url="https://www.catasto-rifiuti.isprambiente.it/index.php?advice=si&pg=downloadComune"
    raw,final,_=get(url); text=raw.decode("utf-8","ignore")
    print("\n### RIFIUTI FORM")
    soup=BeautifulSoup(text,"html.parser")
    for form in soup.find_all("form"):
        print("FORM",form.get("method"),form.get("action"))
        for inp in form.find_all(["input","select","button"]):
            print(" FIELD",inp.name,inp.get("name"),inp.get("value"),[o.get("value") for o in inp.find_all("option")[:8]])
    for pat in ["csv","download","anno","Comune","ajax","export"]:
        print("\nPATTERN",pat)
        for m in list(re.finditer(pat,text,re.I))[:12]:
            print(text[max(0,m.start()-240):m.start()+500].replace("\n"," ")[:800])

def inspect_rischi_js():
    url="https://www.istat.it/wp-content/themes/EGPbs5-child/inc/mappa-rischi/js/atlrsk.js"
    raw,final,_=get(url); text=raw.decode("utf-8","ignore")
    print("\n### RISCHI JS",len(text))
    for line in text.splitlines():
        if any(k in line.lower() for k in ["ajax","csv","json","download","php","url:","export"]):
            print(line[:1200])

def inspect_idrogeo():
    raw,_,_=get("https://idrogeo.isprambiente.it/api/"); api=json.loads(raw)
    print("\n### IDROGEO selected endpoints")
    for p in ["/pir/regioni","/pir/province","/pir/comuni","/iffi/regioni","/iffi/province","/iffi/comuni"]:
        if p in api["paths"]:
            print("ENDPOINT",p,json.dumps(api["paths"][p],ensure_ascii=False)[:8000])
            try:
                b,u,c=get("https://idrogeo.isprambiente.it/api"+p)
                print(" SAMPLE",len(b),c,b[:1500].decode("utf-8","ignore"))
            except Exception as e: print(" SAMPLEERR",repr(e))

def main():
    inspect_aci()
    for name,url in TARGETS.items():
        try:
            raw,final,ctype=get(url); inspect_bytes(name,raw,final,ctype)
        except Exception as e: print("\n### FILE",name,"ERROR",repr(e))
    inspect_rifiuti_page()
    inspect_rischi_js()
    inspect_idrogeo()

if __name__=="__main__": main()
