#!/usr/bin/env python3
"""Acquire verified ISTAT 'A misura di Comune' municipal observations.

The source is a multi-topic municipal statistical system. Its statistical
reference years are mostly 2023/2024 even though the release was updated on
2026-05-26. Therefore these values belong to PULSE's observed-data catalogue,
not to the current-news feed.
"""
from __future__ import annotations

from pathlib import Path
from urllib.parse import urljoin,urlparse
import io,math,re,urllib.request
import pandas as pd
from bs4 import BeautifulSoup

PAGE="https://www.istat.it/statistica-sperimentale/aggiornamento-degli-indicatori-del-sistema-informativo-a-misura-di-comune/"
OUT=Path("app/src/main/assets/pulse_observations_amc.tsv")
SOURCE="ISTAT - A misura di Comune"
FIELDS=["area","indicator","territory","period","value","unit","source","url","note","status"]

# Explicit table-level semantic mapping. Each selected table is municipality
# level and carries stable ISTAT municipality codes in the official workbook.
TABLES=[
    {
      "book":"5 – Lavoro","sheet":"Tav. 1.1 Comuni","area":"Lavoro",
      "indicator":"Tasso di occupazione","unit":"%",
    },
    {
      "book":"5 – Lavoro","sheet":"Tav. 2.1 Comuni","area":"Lavoro",
      "indicator":"Tasso di disoccupazione","unit":"%",
    },
    {
      "book":"6 – Benessere economico","sheet":"Tav. 1.1 Comuni","area":"Redditi",
      "indicator":"Contribuenti con reddito complessivo inferiore a 10.000 euro","unit":"%",
    },
    {
      "book":"6 – Benessere economico","sheet":"Tav. 2.1 Comuni","area":"Redditi",
      "indicator":"Reddito imponibile per contribuente","unit":"euro",
    },
    {
      "book":"11 – Territorio e ambiente","sheet":"Tav. 6.1 Comuni","area":"Ambiente",
      "indicator":"Raccolta differenziata dei rifiuti urbani","unit":"%",
    },
    {
      "book":"11 – Territorio e ambiente","sheet":"Tav. 8.1 Comuni","area":"Mobilità sostenibile",
      "indicator":"Autovetture con standard di emissioni inferiore a Euro 4","unit":"%",
    },
]

def download(url):
    req=urllib.request.Request(url,headers={"User-Agent":"ISTAT-PULSE/1.0"})
    with urllib.request.urlopen(req,timeout=180) as response:
        data=response.read()
        if response.status!=200:
            raise RuntimeError(f"HTTP {response.status}: {url}")
        return data

def official_urls():
    soup=BeautifulSoup(download(PAGE),"html.parser")
    mapping={}
    for a in soup.select("a[href]"):
        label=a.get_text(" ",strip=True)
        url=urljoin(PAGE,a.get("href",""))
        if urlparse(url).netloc not in {"www.istat.it","istat.it"}:
            continue
        if url.lower().split("?")[0].endswith(".xlsx"):
            mapping[label]=url
    if len(mapping)<20:
        raise RuntimeError(f"Too few official XLSX links found: {len(mapping)}")
    return mapping

def parse_number(raw):
    if raw is None or pd.isna(raw): return None
    text=str(raw).strip()
    if text in {"","-","..","....","nan","NaN",".","n.d.","nd"}: return None
    # Excel cells normally arrive as numeric strings with decimal dot.
    try:
        val=float(text)
        return val if math.isfinite(val) else None
    except Exception:
        pass
    # Fallback for Italian-formatted text.
    if "," in text and "." in text:
        if text.rfind(",")>text.rfind("."):
            text=text.replace(".","").replace(",",".")
        else:
            text=text.replace(",","")
    elif "," in text:
        text=text.replace(",",".")
    text=re.sub(r"[^0-9+\-.eE]","",text)
    try:
        val=float(text)
        return val if math.isfinite(val) else None
    except Exception:
        return None

def year_columns(frame):
    result=[]
    for col in frame.columns:
        text=str(col).strip()
        m=re.fullmatch(r"(20\d{2})(?:\.0+)?",text)
        if m:
            result.append((int(m.group(1)),col))
    return sorted(result)

def latest_value(row,years):
    for year,col in reversed(years):
        value=parse_number(row.get(col))
        if value is not None:
            return year,value
    return None

def main():
    urls=official_urls()
    books={}
    observations=[]
    validation={}

    for spec in TABLES:
        label=spec["book"]
        if label not in urls:
            raise RuntimeError(f"Official XLSX not found for {label}")
        url=urls[label]

        if label not in books:
            raw=download(url)
            if raw[:2]!=b"PK":
                raise RuntimeError(f"Invalid XLSX payload: {url}")
            books[label]=raw
            print(f"OFFICIAL {label}: {len(raw):,} bytes from {url}",flush=True)

        raw=books[label]
        xl=pd.ExcelFile(io.BytesIO(raw))
        if spec["sheet"] not in xl.sheet_names:
            raise RuntimeError(f"Missing sheet {spec['sheet']} in {label}")

        frame=pd.read_excel(io.BytesIO(raw),sheet_name=spec["sheet"],header=3,dtype=str)
        frame.columns=[str(x).strip() for x in frame.columns]

        required={"Denominazione comune","Codice comune Istat","Denominazione regione"}
        if not required.issubset(frame.columns):
            raise RuntimeError(
                f"Missing municipality keys in {label}/{spec['sheet']}: {frame.columns.tolist()}"
            )

        years=year_columns(frame)
        if len(years)<2:
            raise RuntimeError(f"Insufficient year columns in {label}/{spec['sheet']}")

        added=0
        codes=set()
        latest_year=0
        for _,row in frame.iterrows():
            code=str(row.get("Codice comune Istat","")).strip()
            if code.endswith(".0"): code=code[:-2]
            code=re.sub(r"\D","",code).zfill(6)
            comune=str(row.get("Denominazione comune","")).strip()
            regione=str(row.get("Denominazione regione","")).strip()
            if not re.fullmatch(r"\d{6}",code) or not comune or comune.casefold()=="nan":
                continue
            result=latest_value(row,years)
            if result is None: continue
            year,value=result
            if year>2026:
                raise RuntimeError(f"Future statistical year {year} in {label}/{spec['sheet']}")
            latest_year=max(latest_year,year)
            codes.add(code)
            added+=1
            observations.append({
                "area":spec["area"],
                "indicator":spec["indicator"],
                "territory":f"{comune} [{code}]",
                "period":str(year),
                "value":format(value,".10g"),
                "unit":spec["unit"],
                "source":SOURCE,
                "url":url,
                "note":(
                    f"Comune: {comune}; codice ISTAT: {code}; regione: {regione}. "
                    "Valore osservato nella tavola ufficiale A misura di Comune; "
                    "non è una notizia corrente."
                ),
                "status":"ultimo valore osservato, non segnale corrente",
            })

        validation[spec["indicator"]]={
            "rows":added,"municipalities":len(codes),"latest_year":latest_year,
            "first_year":years[0][0],
        }
        print(
            "TABLE",spec["indicator"],"ROWS",added,"MUNICIPALITIES",len(codes),
            "COVERAGE",f"{years[0][0]}-{latest_year}",flush=True
        )
        # Municipality counts differ slightly by source year/geography, but a
        # national municipal table must still cover essentially all Italy.
        if len(codes)<7700:
            raise RuntimeError(
                f"Municipal coverage too low for {spec['indicator']}: {len(codes)}"
            )

    out=pd.DataFrame(observations,columns=FIELDS)
    if out.empty:
        raise RuntimeError("No A misura di Comune observations generated")
    if out.duplicated(["source","indicator","territory","period"]).any():
        raise RuntimeError("Duplicate A misura di Comune observations")
    OUT.parent.mkdir(parents=True,exist_ok=True)
    out.to_csv(OUT,sep="\t",index=False)

    print("A MISURA DI COMUNE OBSERVATIONS",len(out),flush=True)
    print("INDICATORS",len(validation),flush=True)
    print("VALIDATION",validation,flush=True)

if __name__=="__main__":
    main()
