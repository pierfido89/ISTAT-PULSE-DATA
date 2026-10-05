#!/usr/bin/env python3
from __future__ import annotations
import hashlib,json,re,urllib.parse,urllib.request
from datetime import datetime,timezone
from pathlib import Path
from bs4 import BeautifulSoup

OUT=Path("data/invalsi_latest.json")
CAT=Path("data/sources_catalog.json")
PAGE="https://www.invalsi.it/rilevazioni-nazionali/materiali-approfondimento/"
UA="ISTAT-PULSE/INVALSI (+https://github.com/pierfido89/ISTAT-PULSE-DATA)"

def get(u,probe=False):
    h={"User-Agent":"Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 Chrome/154 Safari/537.36","Accept":"*/*","Accept-Language":"it-IT,it;q=0.9"}
    req=urllib.request.Request(u,headers=h)
    with urllib.request.urlopen(req,timeout=180) as r:
        return r.read(131072 if probe else -1),r.geturl(),r.headers.get("Content-Type","")

def main():
    raw,final,_=get(PAGE)
    s=BeautifulSoup(raw.decode("utf-8","ignore"),"html.parser")
    text=" ".join(s.stripped_strings)
    years=[int(y) for y in re.findall(r"I Risultati delle prove INVALSI\s+(20\d{2})",text,re.I)]
    if not years:
        years=[int(y) for y in re.findall(r"Rapporto prove INVALSI\s+(20\d{2})",text,re.I)]
    if not years: raise RuntimeError("INVALSI: no annual editions")
    year=max(years)
    resources=[]
    for a in s.find_all("a",href=True):
        lab=" ".join(a.stripped_strings)
        h=urllib.parse.urljoin(final,a["href"])
        ctx=(lab+" "+h).lower()
        if str(year) not in ctx and "rapporto" not in ctx: continue
        if not any(k in ctx for k in ("rapporto prove invalsi","sintesi primi risultati","comunicato stampa")): continue
        try:
            b,u,ct=get(h,True)
            if len(b)>50 and ("pdf" in ct.lower() or ".pdf" in u.lower()):
                resources.append({"title":lab[:180],"url":u,"content_type":ct,"probe_bytes":len(b),"sha256":hashlib.sha256(b).hexdigest()})
        except Exception:
            pass
    if not resources:
        raise RuntimeError("INVALSI: official annual materials not validated")
    snap={"source":"INVALSI","source_family":"INVALSI - Risultati rilevazioni nazionali","year":year,
          "release_url":PAGE,"validated_resource_count":len(resources),"resources":resources,
          "checked_at":datetime.now(timezone.utc).isoformat(),"status":"feed"}
    OUT.write_text(json.dumps(snap,ensure_ascii=False,indent=2)+"\n")
    root=json.loads(CAT.read_text()) if CAT.exists() else {"sources":[]}
    name="INVALSI - Risultati rilevazioni nazionali"
    src=next((x for x in root["sources"] if x.get("name")==name),None)
    if src is None:
        src={};root["sources"].append(src)
    src.update({"name":name,"category":"ISTRUZIONE_VALUTAZIONE_IT","topics":["INVALSI","APPRENDIMENTI","ITALIANO","MATEMATICA","INGLESE"],
      "official":True,"url":PAGE,"access_cost":"free","integration_status":"feed",
      "feed_status":"Attiva · rapporto nazionale e materiali INVALSI validati","frequency":"Annuale",
      "latest_period":str(year),"checked_at":snap["checked_at"]})
    CAT.write_text(json.dumps(root,ensure_ascii=False,indent=2)+"\n")
    print(json.dumps({"year":year,"resources":len(resources)},ensure_ascii=False))

if __name__=="__main__":
    main()
