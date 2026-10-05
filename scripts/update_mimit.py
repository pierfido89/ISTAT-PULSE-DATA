#!/usr/bin/env python3
"""MIMIT fuel prices connector for ISTAT PULSE.

Uses official MIMIT open-data pages for:
- daily fuel prices at 08:00
- active filling-station registry
- regional average fuel prices

Outputs:
- data/mimit_latest.json
- updates data/sources_catalog.json
"""
from __future__ import annotations
import csv, hashlib, io, json, re, urllib.parse, urllib.request
from datetime import datetime, timezone
from pathlib import Path
from bs4 import BeautifulSoup

OUT=Path("data/mimit_latest.json")
CATALOG=Path("data/sources_catalog.json")
UA="ISTAT-PULSE/MIMIT-connector (+https://github.com/pierfido89/ISTAT-PULSE-DATA)"
OPEN_DATA="https://www.mimit.gov.it/index.php/it/open-data/elenco-dataset/carburanti-prezzi-praticati-e-anagrafica-degli-impianti"
REGIONS="https://www.mimit.gov.it/it/prezzo-medio-carburanti/regioni"

def get(url,timeout=180):
    req=urllib.request.Request(url,headers={"User-Agent":UA,"Accept":"*/*","Accept-Language":"it-IT,it;q=0.9"})
    with urllib.request.urlopen(req,timeout=timeout) as r:
        raw=r.read()
        return raw,r.geturl(),r.headers.get("Content-Type","")

def clean(x): return re.sub(r"\s+"," ",str(x or "")).strip()

def discover_downloads(html,base):
    soup=BeautifulSoup(html,"html.parser")
    out=[]
    for a in soup.find_all("a",href=True):
        title=clean(a.get_text(" ",strip=True))
        href=urllib.parse.urljoin(base,a["href"])
        low=(title+" "+href).lower()
        if "prezzo alle 8" in low or ("prezz" in low and ".csv" in low):
            out.append(("prices",title,href))
        elif "anagrafica" in low and (".csv" in low or "download" in low):
            out.append(("stations",title,href))
    return out

def sample_csv(raw):
    text=raw.decode("utf-8-sig","ignore")
    lines=text.splitlines()
    if not lines: return {"rows_sampled":0,"header":[]}
    delim="|" if "|" in lines[0] else ";" if ";" in lines[0] else ","
    reader=csv.reader(io.StringIO(text),delimiter=delim)
    rows=[]
    for i,row in enumerate(reader):
        rows.append(row)
        if i>=100: break
    return {"rows_sampled":max(0,len(rows)-1),"header":rows[0] if rows else [],"delimiter":delim}

def parse_regional_averages(html):
    soup=BeautifulSoup(html,"html.parser")
    text=clean(soup.get_text(" ",strip=True))
    date=""
    m=re.search(r"Aggiornamento\s+(\d{1,2}-\d{1,2}-20\d{2})",text,re.I)
    if m:
        d,mn,y=m.group(1).split("-"); date=f"{y}-{int(mn):02d}-{int(d):02d}"
    rows=[]
    for tr in soup.find_all("tr"):
        cells=[clean(x.get_text(" ",strip=True)) for x in tr.find_all(["th","td"])]
        if len(cells)>=3 and cells[0].lower() not in ("tipologia",""):
            val=re.sub(r"[^0-9,\.]","",cells[2]).replace(",",".")
            try: price=float(val)
            except: continue
            rows.append({"fuel":cells[0],"service":cells[1],"price":price})
    return date,rows

def main():
    raw,final,ctype=get(OPEN_DATA)
    html=raw.decode("utf-8","ignore")
    downloads=discover_downloads(html,final)
    found={}
    for kind,title,url in downloads:
        if kind in found: continue
        try:
            b,u,ct=get(url)
            if len(b)>100:
                found[kind]={
                  "title":title,"url":u,"content_type":ct,"bytes":len(b),
                  "sha256":hashlib.sha256(b).hexdigest(),
                  **sample_csv(b)
                }
        except Exception:
            pass
    if "prices" not in found:
        raise RuntimeError("MIMIT: daily fuel price CSV not validated")

    rr,rfinal,rct=get(REGIONS)
    avg_date,avg_rows=parse_regional_averages(rr.decode("utf-8","ignore"))

    snap={
      "source":"MIMIT",
      "source_family":"MIMIT - Prezzi carburanti",
      "open_data_url":final,
      "regional_average_url":rfinal,
      "datasets":found,
      "regional_average_date":avg_date,
      "regional_average_rows":avg_rows[:200],
      "regional_average_count":len(avg_rows),
      "checked_at":datetime.now(timezone.utc).isoformat(),
      "status":"feed"
    }
    OUT.write_text(json.dumps(snap,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")

    root=json.loads(CATALOG.read_text(encoding="utf-8")) if CATALOG.exists() else {"sources":[]}
    name="MIMIT - Prezzi carburanti"
    src=next((x for x in root["sources"] if x.get("name")==name),None)
    if src is None: src={}; root["sources"].append(src)
    src.update({
      "name":name,
      "category":"PREZZI_ENERGIA_IT",
      "topics":["CARBURANTI","PREZZI","ENERGIA","MOBILITA"],
      "official":True,
      "url":OPEN_DATA,
      "access_cost":"free",
      "access_note":"Open data MIMIT, licenza IODL 2.0.",
      "integration_status":"feed",
      "feed_status":"Attiva · CSV carburanti MIMIT acquisiti automaticamente",
      "notes":"Feed quotidiano sui prezzi praticati alle 8 e anagrafica impianti, con prezzi medi regionali.",
      "level":"Nazionale, regionale e impianto",
      "frequency":"Quotidiana",
      "latest_period":avg_date,
      "checked_at":snap["checked_at"],
      "provides":[
        {"area":"Prezzi","series":"Prezzi carburanti praticati","description":"CSV quotidiano ufficiale MIMIT.","latest_period":avg_date,"status":"latest_public"},
        {"area":"Territorio","series":"Prezzi medi regionali carburanti","description":"Medie regionali pubblicate giornalmente.","latest_period":avg_date,"status":"latest_public"}
      ]
    })
    CATALOG.write_text(json.dumps(root,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
    print(json.dumps({"validated":list(found),"regional_average_date":avg_date,"regional_average_count":len(avg_rows)},ensure_ascii=False))

if __name__=="__main__": main()
