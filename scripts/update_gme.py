#!/usr/bin/env python3
"""GME public market-data connector for ISTAT PULSE.

Uses public GME pages without API credentials:
- PUN Index GME public results
- MGP daily reports
- MGP historical ZIP archive

The authenticated GME API is intentionally not required for this connector.

Outputs:
- data/gme_latest.json
- updates data/sources_catalog.json
"""
from __future__ import annotations
import hashlib, json, re, urllib.parse, urllib.request
from datetime import datetime, timezone
from pathlib import Path
from bs4 import BeautifulSoup

OUT=Path("data/gme_latest.json")
CATALOG=Path("data/sources_catalog.json")
UA="ISTAT-PULSE/GME-connector (+https://github.com/pierfido89/ISTAT-PULSE-DATA)"
PUN="https://gme.mercatoelettrico.org/it-it/Home/Esiti/Elettricita/MGP/Esiti/PUN"
REPORTS="https://gme.mercatoelettrico.org/it-it/Home/Esiti/Elettricita/MGP/Statistiche/Rapporti"
HISTORY="https://gme.mercatoelettrico.org/Home/Esiti/Elettricita/MGP/Statistiche/DatiStorici"

def get(url,timeout=180):
    req=urllib.request.Request(url,headers={"User-Agent":UA,"Accept":"*/*","Accept-Language":"it-IT,it;q=0.9"})
    with urllib.request.urlopen(req,timeout=timeout) as r:
        raw=r.read()
        return raw,r.geturl(),r.headers.get("Content-Type","")

def clean(x): return re.sub(r"\s+"," ",str(x or "")).strip()

def parse_pun(html):
    soup=BeautifulSoup(html,"html.parser")
    rows=[]
    for tr in soup.find_all("tr"):
        cells=[clean(x.get_text(" ",strip=True)) for x in tr.find_all(["th","td"])]
        if len(cells)>=4 and re.fullmatch(r"\d{2}/\d{2}/20\d{2}",cells[0]):
            try:
                price=float(cells[3].replace(".","").replace(",","."))
            except:
                try: price=float(cells[3])
                except: continue
            rows.append({"date":cells[0],"hour":cells[1],"period":cells[2],"eur_mwh":price})
    latest=""
    if rows:
        d,m,y=rows[-1]["date"].split("/")
        latest=f"{y}-{m}-{d}"
    return latest,rows

def discover_reports(html,base):
    soup=BeautifulSoup(html,"html.parser")
    out=[]
    for a in soup.find_all("a",href=True):
        title=clean(a.get_text(" ",strip=True))
        href=urllib.parse.urljoin(base,a["href"])
        low=(title+" "+href).lower()
        if "report" in low and (".pdf" in low or "download" in low):
            out.append({"title":title[:220],"url":href})
    return out

def discover_history(html,base):
    soup=BeautifulSoup(html,"html.parser")
    out=[]
    for a in soup.find_all("a",href=True):
        title=clean(a.get_text(" ",strip=True))
        href=urllib.parse.urljoin(base,a["href"])
        if re.search(r"Anno\s+20\d{2}",title,re.I) or ".zip" in href.lower():
            out.append({"title":title[:100],"url":href})
    return out

def probe(url):
    req=urllib.request.Request(url,headers={"User-Agent":UA,"Accept":"*/*","Range":"bytes=0-65535"})
    with urllib.request.urlopen(req,timeout=120) as r:
        b=r.read(65536)
        return {"url":r.geturl(),"content_type":r.headers.get("Content-Type",""),"bytes_sampled":len(b),"sha256":hashlib.sha256(b).hexdigest()}

def main():
    praw,pfinal,pct=get(PUN)
    pun_date,pun_rows=parse_pun(praw.decode("utf-8","ignore"))

    rraw,rfinal,rct=get(REPORTS)
    reports=discover_reports(rraw.decode("utf-8","ignore"),rfinal)
    validated_reports=[]
    for x in reports[:8]:
        try:
            p=probe(x["url"])
            if p["bytes_sampled"]>0: validated_reports.append({**x,**p})
        except Exception: pass

    hraw,hfinal,hct=get(HISTORY)
    history=discover_history(hraw.decode("utf-8","ignore"),hfinal)
    validated_history=[]
    for x in history[:5]:
        try:
            p=probe(x["url"])
            if p["bytes_sampled"]>0: validated_history.append({**x,**p})
        except Exception: pass

    if not pun_rows and not validated_reports and not validated_history:
        raise RuntimeError("GME: no public market dataset validated")

    snap={
      "source":"GME",
      "source_family":"GME - Mercati Energetici",
      "pun_url":pfinal,
      "pun_latest_date":pun_date,
      "pun_rows_sample":pun_rows[:400],
      "pun_row_count":len(pun_rows),
      "daily_reports":validated_reports,
      "historical_archives":validated_history,
      "api_requires_credentials":True,
      "checked_at":datetime.now(timezone.utc).isoformat(),
      "status":"feed"
    }
    OUT.write_text(json.dumps(snap,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")

    root=json.loads(CATALOG.read_text(encoding="utf-8")) if CATALOG.exists() else {"sources":[]}
    name="GME - Gestore Mercati Energetici"
    src=next((x for x in root["sources"] if x.get("name")==name),None)
    if src is None: src={}; root["sources"].append(src)
    src.update({
      "name":name,
      "category":"ENERGIA_MERCATI_IT",
      "topics":["ELETTRICITA","PUN","MGP","GAS","MERCATI_ENERGETICI"],
      "official":True,
      "url":"https://gme.mercatoelettrico.org/",
      "access_cost":"free",
      "access_note":"Dati pubblici GME accessibili dal sito; l'API ufficiale avanzata richiede registrazione e credenziali.",
      "integration_status":"feed",
      "feed_status":"Attiva · dati pubblici GME acquisiti automaticamente; API autenticata opzionale",
      "notes":"Feed PULSE su PUN Index GME, report giornalieri MGP e archivi storici pubblici. API GME non necessaria per il feed base.",
      "level":"Nazionale e zone di mercato secondo dataset",
      "frequency":"Giornaliera/infragiornaliera secondo mercato",
      "latest_period":pun_date,
      "checked_at":snap["checked_at"],
      "provides":[
        {"area":"Energia","series":"PUN Index GME","description":"Indice di riferimento del mercato elettrico italiano.","latest_period":pun_date,"status":"latest_public"},
        {"area":"Energia","series":"Mercato del Giorno Prima - report","description":"Report ufficiali MGP.","latest_period":pun_date,"status":"latest_public"},
        {"area":"Energia","series":"Storico MGP","description":"Archivi storici GME pubblici.","latest_period":pun_date,"status":"latest_public"}
      ]
    })
    CATALOG.write_text(json.dumps(root,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
    print(json.dumps({"pun_latest_date":pun_date,"pun_row_count":len(pun_rows),"reports":len(validated_reports),"history":len(validated_history)},ensure_ascii=False))

if __name__=="__main__": main()
