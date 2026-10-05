#!/usr/bin/env python3
"""Unioncamere / InfoCamere connector for ISTAT PULSE.

Sources:
- Unioncamere Open Government (CSV open data)
- Movimprese (quarterly business demography, downloadable CSV/documents)

Outputs:
- data/unioncamere_infocamere_latest.json
- updates data/sources_catalog.json
"""
from __future__ import annotations
import hashlib, json, re, urllib.parse, urllib.request
from datetime import datetime, timezone
from pathlib import Path
from bs4 import BeautifulSoup

OUT=Path("data/unioncamere_infocamere_latest.json")
CATALOG=Path("data/sources_catalog.json")
UA="ISTAT-PULSE/Unioncamere-InfoCamere (+https://github.com/pierfido89/ISTAT-PULSE-DATA)"
OPEN_GOV="https://opengovernment.unioncamere.gov.it/"
MOVIMPRESE="https://www.infocamere.it/movimprese"

def get(url, timeout=120, accept="*/*"):
    req=urllib.request.Request(url,headers={"User-Agent":UA,"Accept":accept,"Accept-Language":"it-IT,it;q=0.9,en;q=0.7"})
    with urllib.request.urlopen(req,timeout=timeout) as r:
        raw=r.read()
        return raw,r.geturl(),r.headers.get("Content-Type","")

def clean(x): return re.sub(r"\s+"," ",str(x or "")).strip()

def links(url):
    raw,final,ctype=get(url)
    html=raw.decode("utf-8","ignore")
    soup=BeautifulSoup(html,"html.parser")
    out=[]
    for a in soup.find_all("a",href=True):
        href=urllib.parse.urljoin(final,a["href"])
        title=clean(a.get_text(" ",strip=True))
        out.append((title,href))
    return raw,final,ctype,out

def probe_file(url):
    req=urllib.request.Request(url,headers={"User-Agent":UA,"Accept":"*/*","Range":"bytes=0-131071"})
    with urllib.request.urlopen(req,timeout=120) as r:
        raw=r.read(131072)
        return {
          "url":r.geturl(),
          "content_type":r.headers.get("Content-Type",""),
          "bytes_sampled":len(raw),
          "sha256":hashlib.sha256(raw).hexdigest(),
        }

def main():
    og_raw,og_final,og_type,og_links=links(OPEN_GOV)
    csvs=[]
    for title,href in og_links:
        h=href.lower()
        if ".csv" in h or "download" in h:
            if any(k in (title+" "+href).lower() for k in ("impres","demografia","startup","giovan","femmin","stranier")):
                csvs.append({"title":title[:200],"url":href})
    csvs=csvs[:20]

    mv_raw,mv_final,mv_type,mv_links=links(MOVIMPRESE)
    mv_candidates=[]
    for title,href in mv_links:
        text=(title+" "+href).lower()
        if any(k in text for k in ("csv","scarica","download","movimprese")):
            mv_candidates.append({"title":title[:200],"url":href})
    mv_candidates=mv_candidates[:30]

    validated=[]
    for item in csvs + mv_candidates:
        try:
            p=probe_file(item["url"])
            if p["bytes_sampled"]>0:
                validated.append({**item,**p})
        except Exception:
            pass
        if len(validated)>=8: break

    if len(validated)<1:
        raise RuntimeError("Unioncamere/InfoCamere: no downloadable public resources validated")

    snapshot={
      "source":"Unioncamere - InfoCamere",
      "source_family":"Unioncamere - InfoCamere - Demografia d'impresa",
      "open_government_url":og_final,
      "movimprese_url":mv_final,
      "validated_resource_count":len(validated),
      "resources":validated,
      "checked_at":datetime.now(timezone.utc).isoformat(),
      "status":"feed",
    }
    OUT.write_text(json.dumps(snapshot,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")

    root=json.loads(CATALOG.read_text(encoding="utf-8")) if CATALOG.exists() else {"sources":[]}
    name="Unioncamere - InfoCamere - Demografia d'impresa"
    src=next((x for x in root["sources"] if x.get("name")==name),None)
    if src is None: src={}; root["sources"].append(src)
    src.update({
      "name":name,
      "category":"IMPRESE_IT",
      "topics":["IMPRESE","DEMOGRAFIA_IMPRESE","STARTUP","IMPRENDITORIA"],
      "official":True,
      "url":MOVIMPRESE,
      "access_cost":"free",
      "access_note":"Dati pubblici Unioncamere/InfoCamere e dataset Open Government; verificare la licenza del singolo dataset.",
      "integration_status":"feed",
      "feed_status":"Attiva · risorse pubbliche CSV/download validate automaticamente",
      "notes":"Feed PULSE basato su Movimprese e Open Government Unioncamere per demografia d'impresa e dataset camerali.",
      "level":"Nazionale, regionale, provinciale e comunale secondo dataset",
      "frequency":"Trimestrale e secondo aggiornamento dataset",
      "checked_at":snapshot["checked_at"],
      "provides":[
        {"area":"Imprese","series":"Nati-mortalità e consistenza delle imprese","description":"Movimprese / Registro Imprese.","latest_period":"","status":"latest_public"},
        {"area":"Imprese","series":"Open data camerali su demografia e profili imprenditoriali","description":"Unioncamere Open Government.","latest_period":"","status":"latest_public"}
      ]
    })
    CATALOG.write_text(json.dumps(root,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
    print(json.dumps({"validated_resource_count":len(validated)},ensure_ascii=False))

if __name__=="__main__": main()
