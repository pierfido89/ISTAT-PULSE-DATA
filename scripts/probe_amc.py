#!/usr/bin/env python3
"""Inspect the real official A misura di Comune XLSX source layouts before parsing.

Only source-provided links are accepted: never fabricate a source spreadsheet URL.
"""
import io
import re
import urllib.request
from urllib.parse import urljoin,urlparse
from bs4 import BeautifulSoup
import pandas as pd

PAGE="https://www.istat.it/statistica-sperimentale/aggiornamento-degli-indicatori-del-sistema-informativo-a-misura-di-comune/"
def fetch(url):
    req=urllib.request.Request(url,headers={"User-Agent":"ISTAT-PULSE/0.9"})
    with urllib.request.urlopen(req,timeout=100) as r:
        result=r.read()
        print("HTTP",r.status,"bytes",len(result),"URL",r.url)
        return result
html=fetch(PAGE)
soup=BeautifulSoup(html,"html.parser")
links=[]
for a in soup.select("a[href]"):
    href=urljoin(PAGE,a.get("href",""))
    if urlparse(href).netloc not in {"www.istat.it","istat.it"}: continue
    label=a.get_text(" ",strip=True)
    if href.lower().split("?")[0].endswith(".xlsx"):
        links.append((label,href))
print("OFFICIAL XLSX LINKS:",len(links))
for i,(label,url) in enumerate(links):
    print("SOURCE",i,label[:90],url)
selection=[]
for keyword in ["famiglie","istruzione","benessere economico","territorio e ambiente","popolazione valori assoluti"]:
    choices=[(label,url) for label,url in links if keyword in label.casefold()]
    if choices: selection.append((keyword,choices[0][1]))
for label,url in selection:
    print("### INSPECT",label)
    try:
        data=fetch(url)
        xl=pd.ExcelFile(io.BytesIO(data))
        print("SHEETS",xl.sheet_names)
        for tab in xl.sheet_names[:3]:
            preview=pd.read_excel(io.BytesIO(data),sheet_name=tab,header=None,nrows=7,dtype=str)
            print("SHEET",tab,preview.iloc[:7,:12].to_string(index=False,header=False))
    except Exception as exc: print("INSPECTION ERROR",repr(exc))
if len(links)<10: raise RuntimeError("A misura di Comune download links not available in source page")
