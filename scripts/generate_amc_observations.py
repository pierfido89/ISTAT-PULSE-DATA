#!/usr/bin/env python3
"""Import selected, independently verified official municipal-system XLSX tables.

A misura di Comune published 2026-05-26 contains reference years as old as
2023/2024: these records go ONLY to the observed-data catalogue, never the news.
"""
from __future__ import annotations
from pathlib import Path
from urllib.parse import urljoin,urlparse
import io,math,re,urllib.request
import pandas as pd
from bs4 import BeautifulSoup

PAGE="https://www.istat.it/statistica-sperimentale/aggiornamento-degli-indicatori-del-sistema-informativo-a-misura-di-comune/"
OUT=Path("app/src/main/assets/pulse_observations_amc.tsv")
FIELDS=["area","indicator","territory","period","value","unit","source","url","note","status"]
# Explicit semantic mapping of each official TABLE, not an inference from data values.
TABLES=[
    ("3 – Famiglie","Tav. 1.2 Province e regioni","Famiglie","Numero famiglie"),
    ("4 – Istruzione","Tav. 2.2 Province e regioni","Istruzione","Competenze alfabetiche degli studenti"),
    ("4 – Istruzione","Tav. 1.2 Province e regioni","Servizi e qualità locale","Bambini nei servizi comunali per l'infanzia"),
    ("6 – Benessere economico","Tav. 2.2 Province e regioni","Redditi","Reddito imponibile per contribuente"),
    ("6 – Benessere economico","Tav. 1.2 Province e regioni","Redditi","Incidenza di contribuenti con reddito inferiore a 10.000 euro"),
    ("11 – Territorio e ambiente","Tav. 6.2 Province e regioni","Ambiente","Indicatore ambientale"),
]
def download(url):
    request=urllib.request.Request(url,headers={"User-Agent":"ISTAT-PULSE/0.9"})
    with urllib.request.urlopen(request,timeout=180) as response:
        return response.read()
def find_official_urls():
    soup=BeautifulSoup(download(PAGE),"html.parser")
    mapping={}
    for a in soup.select("a[href]"):
        label=a.get_text(" ",strip=True)
        url=urljoin(PAGE,a.get("href",""))
        if urlparse(url).netloc not in {"www.istat.it","istat.it"} or not url.lower().split("?")[0].endswith(".xlsx"): continue
        mapping[label]=url
    return mapping
def latest(row,year_columns):
    for year,column in sorted(year_columns,reverse=True):
        raw=row.get(column)
        if pd.isna(raw): continue
        raw=str(raw).strip()
        try:
            value=float(raw.replace(".","").replace(",",".")) if "," in raw else float(raw)
            if math.isfinite(value): return year,value
        except (ValueError,TypeError): continue
    return None
def main():
    official_urls=find_official_urls()
    books={}
    observations=[]
    for label,sheet,area,indicator in TABLES:
        if label not in official_urls: raise RuntimeError(f"Official XLSX not found for {label}")
        url=official_urls[label]
        if label not in books:
            raw=download(url)
            if raw[:2]!=b"PK": raise RuntimeError(f"Not a valid XLSX: {url}")
            books[label]=raw
            print(f"OFFICIAL {label}: {len(raw):,} bytes from {url}",flush=True)
        book=books[label]
        xl=pd.ExcelFile(io.BytesIO(book))
        matching=[s for s in xl.sheet_names if s.strip()==sheet]
        if len(matching)!=1: raise RuntimeError(f"Unexpected table layout for {label}: {sheet}")
        frame=pd.read_excel(io.BytesIO(book),sheet_name=matching[0],header=3,dtype=str)
        frame.columns=[str(x).strip() for x in frame.columns]
        if "Denominazione regione" not in frame or "Codice regione" not in frame:
            raise RuntimeError(f"Missing region keys in {label}/{sheet}: {frame.columns.tolist()}")
        # Only source's explicit *regional totals*. Never sum provinces or use
        # one province as a region. Grouping errors invalidate the entire import.
        if "Provincia" in frame:
            province=frame["Provincia"].fillna("").astype(str).str.strip()
            regional=frame.loc[province.eq("")].copy()
        else:
            regional=frame.copy()
        years=[(int(x),x) for x in frame.columns if re.fullmatch(r"20\d{2}",x)]
        if not years: raise RuntimeError(f"No year columns in {label}/{sheet}")
        added=0; codes=set()
        for _,row in regional.iterrows():
            code=str(row.get("Codice regione","")).strip()
            if code.endswith(".0"): code=code[:-2]
            code=code.zfill(2)
            name=str(row.get("Denominazione regione","")).strip()
            if not re.fullmatch(r"(0[1-9]|1\d|20)",code) or not name or name.casefold()=="nan": continue
            result=latest(row,years)
            if result is None: continue
            year,value=result
            if year>2026: raise RuntimeError(f"Future year in source {label}: {year}")
            codes.add(code);added+=1
            title=indicator
            if indicator=="Indicatore ambientale":
                first=frame.iloc[0]
                title=str(pd.read_excel(io.BytesIO(book),sheet_name=matching[0],header=None,nrows=1).iloc[0,0])
                title=re.sub(r"^Tavola\s+\d+(?:\.\d+)?\s*-\s*","",title).split(". Anni ")[0].strip()
            observations.append({
                "area":area,"indicator":title,"territory":name,
                "period":str(year),"value":format(value,".10g"),
                "unit":"Valore nella tavola ISTAT; verificare unita e definizione nel file ufficiale.",
                "source":"A misura di Comune — ISTAT","url":url,
                "note":"Serie annuale ufficiale. Data di riferimento precedente al 2026; non notizia PULSE.",
                "status":"ultimo valore osservato, non segnale corrente"
            })
        print("TABLE",label,sheet,"REGIONAL VALUES",added,"REGION CODES",len(codes),flush=True)
        if len(codes)<17: raise RuntimeError(f"Not enough verified regional totals for {label}/{sheet} ({len(codes)})")
    OUT.parent.mkdir(parents=True,exist_ok=True)
    pd.DataFrame(observations,columns=FIELDS).to_csv(OUT,sep="\t",index=False)
    print("A misura di Comune observed regional values:",len(observations),flush=True)
if __name__=="__main__":
    main()
