#!/usr/bin/env python3
"""Unioncamere Excelsior connector for ISTAT PULSE.

Discovers latest official monthly Excelsior release and downloadable statistical attachments.
Outputs:
- data/unioncamere_excelsior_latest.json
- updates data/sources_catalog.json
"""
from __future__ import annotations
import hashlib, json, re, urllib.parse, urllib.request
from datetime import datetime, timezone
from pathlib import Path
from bs4 import BeautifulSoup

OUT=Path("data/unioncamere_excelsior_latest.json")
CATALOG=Path("data/sources_catalog.json")
UA="ISTAT-PULSE/Excelsior (+https://github.com/pierfido89/ISTAT-PULSE-DATA)"
HOME="https://excelsior.unioncamere.net/"
MONTHLY="https://excelsior.unioncamere.net/excelsior-bts/geo/chooser/bollettini/month"

MONTHS={"gennaio":1,"febbraio":2,"marzo":3,"aprile":4,"maggio":5,"giugno":6,"luglio":7,"agosto":8,"settembre":9,"ottobre":10,"novembre":11,"dicembre":12}

def get(url,timeout=120,accept="*/*"):
    req=urllib.request.Request(url,headers={"User-Agent":UA,"Accept":accept,"Accept-Language":"it-IT,it;q=0.9,en;q=0.7"})
    with urllib.request.urlopen(req,timeout=timeout) as r:
        raw=r.read()
        return raw,r.geturl(),r.headers.get("Content-Type","")

def clean(x): return re.sub(r"\s+"," ",str(x or "")).strip()

def period(text):
    m=re.search(r"(gennaio|febbraio|marzo|aprile|maggio|giugno|luglio|agosto|settembre|ottobre|novembre|dicembre)\s+(20\d{2})",text,re.I)
    if not m:return ""
    return f"{int(m.group(2)):04d}-{MONTHS[m.group(1).lower()]:02d}"

def main():
    raw,final,ctype=get(HOME)
    soup=BeautifulSoup(raw.decode("utf-8","ignore"),"html.parser")
    candidates=[]
    for a in soup.find_all("a",href=True):
        title=clean(a.get_text(" ",strip=True))
        href=urllib.parse.urljoin(final,a["href"])
        p=period(title)
        if p and ("notizie" in href or "prevision" in title.lower() or "entrate" in title.lower()):
            candidates.append({"title":title[:250],"url":href,"period":p})
    if not candidates:
        # fallback known monthly page; parser may still discover docs from there
        candidates=[{"title":"Bollettini mensili Excelsior","url":MONTHLY,"period":""}]
    candidates.sort(key=lambda x:x["period"],reverse=True)
    latest=candidates[0]

    page_raw,page_final,page_type=get(latest["url"])
    psoup=BeautifulSoup(page_raw.decode("utf-8","ignore"),"html.parser")
    text=clean(psoup.get_text(" ",strip=True))
    p=latest["period"] or period(text)

    links=[]
    for a in psoup.find_all("a",href=True):
        href=urllib.parse.urljoin(page_final,a["href"])
        title=clean(a.get_text(" ",strip=True))
        low=(title+" "+href).lower()
        if any(k in low for k in (".pdf",".xlsx",".xls",".csv","bollettino","tavole","comunicato")):
            links.append({"title":title[:200],"url":href})
    uniq=[]; seen=set()
    for x in links:
        if x["url"] not in seen:
            seen.add(x["url"]); uniq.append(x)
    links=uniq[:30]

    validated=[]
    for item in links:
        try:
            b,u,ct=get(item["url"])
            if len(b)>500:
                validated.append({**item,"url":u,"content_type":ct,"bytes":len(b),"sha256":hashlib.sha256(b).hexdigest()})
        except Exception:
            pass
        if len(validated)>=10: break

    # Extract key headline numbers when present.
    entries=None
    m=re.search(r"(\d{3})\s*mila\s+(?:entrate|contratti)",text,re.I)
    if m: entries=int(m.group(1))*1000
    mismatch=None
    mm=re.search(r"(?:difficil[^%]{0,80}|mismatch[^%]{0,80})(\d{1,2}[,.]\d)%",text,re.I)
    if mm: mismatch=float(mm.group(1).replace(",","."))

    if not p:
        raise RuntimeError("Excelsior: cannot determine latest monthly period")

    snapshot={
      "source":"Unioncamere - Excelsior",
      "source_family":"Unioncamere - Excelsior",
      "period":p,
      "release_title":latest["title"],
      "release_url":page_final,
      "entrate_programmate":entries,
      "mismatch_percent":mismatch,
      "validated_attachment_count":len(validated),
      "attachments":validated,
      "checked_at":datetime.now(timezone.utc).isoformat(),
      "status":"feed" if validated else "connected",
    }
    if not validated:
        raise RuntimeError("Excelsior: no official attachments validated")
    OUT.write_text(json.dumps(snapshot,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")

    root=json.loads(CATALOG.read_text(encoding="utf-8")) if CATALOG.exists() else {"sources":[]}
    name="Unioncamere - Excelsior"
    src=next((x for x in root["sources"] if x.get("name")==name),None)
    if src is None: src={}; root["sources"].append(src)
    src.update({
      "name":name,
      "category":"LAVORO_IT",
      "topics":["LAVORO","PROFESSIONI","FABBISOGNI_OCCUPAZIONALI","MISMATCH"],
      "official":True,
      "url":HOME,
      "access_cost":"free",
      "access_note":"Pubblicazioni e tavole statistiche pubbliche Excelsior; citare integralmente la fonte richiesta.",
      "integration_status":"feed",
      "feed_status":"Attiva · pubblicazioni mensili Excelsior e allegati ufficiali acquisiti automaticamente",
      "notes":"Feed PULSE sulla domanda di lavoro delle imprese: entrate programmate, professioni, mismatch e dettaglio territoriale.",
      "level":"Nazionale, regionale e provinciale",
      "frequency":"Mensile",
      "latest_period":p,
      "checked_at":snapshot["checked_at"],
      "provides":[
        {"area":"Lavoro","series":"Entrate programmate dalle imprese","description":"Previsioni mensili Excelsior.","latest_period":p,"status":"latest_public"},
        {"area":"Lavoro","series":"Professioni richieste e difficoltà di reperimento","description":"Bollettini e tavole Excelsior.","latest_period":p,"status":"latest_public"},
        {"area":"Territorio","series":"Previsioni occupazionali regionali e provinciali","description":"Bollettini territoriali Excelsior.","latest_period":p,"status":"latest_public"}
      ]
    })
    CATALOG.write_text(json.dumps(root,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
    print(json.dumps({"period":p,"validated_attachment_count":len(validated),"entrate_programmate":entries},ensure_ascii=False))

if __name__=="__main__": main()
