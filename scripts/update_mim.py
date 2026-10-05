#!/usr/bin/env python3
from __future__ import annotations
import hashlib,json,re,urllib.parse,urllib.request
from datetime import datetime,timezone
from pathlib import Path
from bs4 import BeautifulSoup

OUT=Path("data/mim_latest.json"); CAT=Path("data/sources_catalog.json")
UA="ISTAT-PULSE/MIM (+https://github.com/pierfido89/ISTAT-PULSE-DATA)"
CATALOG_URL="https://dati.istruzione.it/opendata/opendata/catalogo/elements1/?area=Scuole"
STATS_URL="https://dati.istruzione.it/opendata/approfondimenti/statistiche/?catalogo=Istruzione"

def get(url,probe=False):
    h={"User-Agent":UA,"Accept":"*/*","Accept-Language":"it-IT,it;q=0.9"}
    if probe: h["Range"]="bytes=0-131071"
    req=urllib.request.Request(url,headers=h)
    with urllib.request.urlopen(req,timeout=180) as r:
        raw=r.read(131072 if probe else -1)
        return raw,r.geturl(),r.headers.get("Content-Type","")

def main():
    raw,final,_=get(CATALOG_URL)
    soup=BeautifulSoup(raw.decode("utf-8","ignore"),"html.parser")
    datasets=[]
    for a in soup.find_all("a",href=True):
        href=urllib.parse.urljoin(final,a["href"])
        title=" ".join(a.stripped_strings)
        if "/leaf/" in href and href not in [x["url"] for x in datasets]:
            datasets.append({"title":title[:220],"url":href})
    validated=[]
    for d in datasets[:40]:
        try:
            b,u,_=get(d["url"]); ps=BeautifulSoup(b.decode("utf-8","ignore"),"html.parser")
        except Exception:
            continue
        title=(ps.find("h1").get_text(" ",strip=True) if ps.find("h1") else d["title"])
        files=[]
        text=" ".join(ps.stripped_strings)
        years=sorted(set(re.findall(r"ANNOSCOLASTICO\s+(20\d{4})|ANNOFINANZIARIO\s+(20\d{4})",text)))
        for a in ps.find_all("a",href=True):
            h=urllib.parse.urljoin(u,a["href"])
            lab=" ".join(a.stripped_strings)
            low=(lab+" "+h).lower()
            if not any(x in low for x in (".csv","csv","scarica il file")): continue
            try:
                rb,ru,ct=get(h,True)
                if len(rb)>50 and ("csv" in ct.lower() or ".csv" in ru.lower()) and "text/html" not in ct.lower():
                    files.append({"title":lab[:160],"url":ru,"content_type":ct,"probe_bytes":len(rb),"sha256":hashlib.sha256(rb).hexdigest()})
            except Exception: pass
        if files:
            validated.append({"title":title,"url":u,"files":files[:3]})
        if len(validated)>=8: break
    if len(validated)<3:
        raise RuntimeError("MIM: meno di 3 dataset CSV validati")
    sraw,sfinal,_=get(STATS_URL)
    stxt=" ".join(BeautifulSoup(sraw.decode("utf-8","ignore"),"html.parser").stripped_strings)
    upd=""
    m=re.search(r"Ultimo aggiornamento dati:\s*(\d{1,2})\s+([A-Za-zÀ-ÿ]+)\s+(20\d{2})",stxt,re.I)
    months={"gennaio":1,"febbraio":2,"marzo":3,"aprile":4,"maggio":5,"giugno":6,"luglio":7,"agosto":8,"settembre":9,"ottobre":10,"novembre":11,"dicembre":12}
    if m and m.group(2).lower() in months:
        upd=f"{m.group(3)}-{months[m.group(2).lower()]:02d}-{int(m.group(1)):02d}"
    snap={"source":"Ministero dell'Istruzione e del Merito","source_family":"MIM - Open Data scuola",
          "dataset_count":len(validated),"datasets":validated,"latest_update":upd,
          "checked_at":datetime.now(timezone.utc).isoformat(),"status":"feed"}
    OUT.write_text(json.dumps(snap,ensure_ascii=False,indent=2)+"\n")
    root=json.loads(CAT.read_text()) if CAT.exists() else {"sources":[]}; name="Ministero dell'Istruzione e del Merito - Open Data"
    src=next((x for x in root["sources"] if x.get("name")==name),None)
    if src is None: src={}; root["sources"].append(src)
    src.update({"name":name,"category":"ISTRUZIONE_IT","topics":["SCUOLE","STUDENTI","PERSONALE","EDILIZIA_SCOLASTICA"],
                "official":True,"url":"https://dati.istruzione.it/opendata/","access_cost":"free","integration_status":"feed",
                "feed_status":"Attiva · dataset CSV scuola validati","frequency":"Annuale e mensile secondo dataset",
                "latest_period":upd,"checked_at":snap["checked_at"]})
    CAT.write_text(json.dumps(root,ensure_ascii=False,indent=2)+"\n")
    print(json.dumps({"datasets":len(validated),"latest":upd},ensure_ascii=False))

if __name__=="__main__": main()
