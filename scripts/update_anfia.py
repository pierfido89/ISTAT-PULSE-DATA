#!/usr/bin/env python3
from __future__ import annotations
import hashlib,json,re,urllib.parse,urllib.request
from datetime import datetime,timezone
from pathlib import Path
from bs4 import BeautifulSoup

LANDING="https://www.anfia.it/it/attivita/studi-e-statistiche/dati-statistici/immatricolazioni/italia"
OUT=Path("data/anfia_latest.json")
CAT=Path("data/sources_catalog.json")
UA="ISTAT-PULSE/ANFIA (+https://github.com/pierfido89/ISTAT-PULSE-DATA)"
MONTHS={"gennaio":1,"febbraio":2,"marzo":3,"aprile":4,"maggio":5,"giugno":6,"luglio":7,"agosto":8,"settembre":9,"ottobre":10,"novembre":11,"dicembre":12}

def get(url,probe=False):
    headers={"User-Agent":UA,"Accept":"*/*","Accept-Language":"it-IT,it;q=0.9"}
    if probe: headers["Range"]="bytes=0-65535"
    req=urllib.request.Request(url,headers=headers)
    with urllib.request.urlopen(req,timeout=180) as r:
        raw=r.read(65536 if probe else -1)
        return raw,r.geturl(),r.headers.get("Content-Type","")

def iso_date(text):
    m=re.search(r"(\d{1,2})\s+([A-Za-zÀ-ÿ]+)\s+(20\d{2})",text,re.I)
    if not m or m.group(2).lower() not in MONTHS:return ""
    return f"{m.group(3)}-{MONTHS[m.group(2).lower()]:02d}-{int(m.group(1)):02d}"

def main():
    raw,final,_=get(LANDING)
    soup=BeautifulSoup(raw.decode("utf-8","ignore"),"html.parser")
    candidates=[]
    for a in soup.find_all("a",href=True):
        href=urllib.parse.urljoin(final,a["href"])
        parent=a.parent
        ctx=" ".join(parent.stripped_strings) if parent else " ".join(a.stripped_strings)
        if parent and parent.parent:
            ctx+=" "+" ".join(parent.parent.stripped_strings)
        low=ctx.lower()
        if "autovetture" not in low or "tabelle comunicato stampa" not in low:
            continue
        pub=iso_date(ctx)
        try:
            b,u,ct=get(href,True)
            if len(b)>50 and "text/html" not in ct.lower():
                candidates.append({"publication_date":pub,"url":u,"content_type":ct,"probe_bytes":len(b),
                  "probe_sha256":hashlib.sha256(b).hexdigest()})
        except Exception:
            pass
    if not candidates:
        raise RuntimeError("ANFIA: tabelle comunicato stampa non trovate")
    candidates.sort(key=lambda x:x["publication_date"],reverse=True)
    latest=candidates[0]
    if not latest["publication_date"]:
        raise RuntimeError("ANFIA: data pubblicazione mancante")
    y,m,_=map(int,latest["publication_date"].split("-"))
    m-=1
    if m==0:
        y-=1;m=12
    period=f"{y:04d}-{m:02d}"
    snap={"source":"ANFIA","source_family":"ANFIA - Immatricolazioni e mercato auto","period":period,
      "publication_date":latest["publication_date"],"dataset":latest,"checked_at":datetime.now(timezone.utc).isoformat(),"status":"feed"}
    OUT.write_text(json.dumps(snap,ensure_ascii=False,indent=2)+"\n")
    root=json.loads(CAT.read_text()) if CAT.exists() else {"sources":[]}
    name="ANFIA - Immatricolazioni e mercato auto"
    src=next((x for x in root["sources"] if x.get("name")==name),None)
    if src is None: src={};root["sources"].append(src)
    src.update({"name":name,"category":"MOBILITA_IT","topics":["AUTO","IMMATRICOLAZIONI","MOBILITA"],
      "official":True,"url":LANDING,"access_cost":"free","integration_status":"feed",
      "feed_status":"Attiva · tavole statistiche mensili ANFIA validate","frequency":"Mensile",
      "latest_period":period,"publication_date":latest["publication_date"],"checked_at":snap["checked_at"]})
    CAT.write_text(json.dumps(root,ensure_ascii=False,indent=2)+"\n")
    print(json.dumps({"period":period,"publication_date":latest["publication_date"]},ensure_ascii=False))

if __name__=="__main__":
    main()
