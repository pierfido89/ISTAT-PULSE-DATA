#!/usr/bin/env python3
"""INAIL Open Data connector for ISTAT PULSE.

Uses official INAIL REST Open API endpoints returning JSON.
Monitors:
- monthly workplace accidents
- half-year workplace accidents
- monthly occupational diseases
- half-year occupational diseases (protocol date)

Outputs:
- data/inail_latest.json
- updates data/sources_catalog.json
"""
from __future__ import annotations

import hashlib
import json
import re
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

OUT=Path("data/inail_latest.json")
CATALOG=Path("data/sources_catalog.json")
UA="ISTAT-PULSE/INAIL-connector (+https://github.com/pierfido89/ISTAT-PULSE-DATA)"
BASE="https://dati.inail.it/api/OpenData"

ENDPOINTS={
  "accidents_monthly":"DatiConCadenzaMensileInfortuni",
  "accidents_halfyear":"DatiConCadenzaSemestraleInfortuni",
  "diseases_monthly":"DatiMensiliMalattieProfessionaliDataProt",
  "diseases_halfyear":"DatiSemestraliMalattieProfessionaliDataProt",
}

def get_json(url:str,timeout=180):
    req=urllib.request.Request(url,headers={"User-Agent":UA,"Accept":"application/json"})
    with urllib.request.urlopen(req,timeout=timeout) as r:
        raw=r.read()
        if not raw:
            raise RuntimeError("empty response")
        return json.loads(raw.decode("utf-8","ignore")),r.geturl(),r.headers.get("Content-Type",""),raw

def clean(x): return re.sub(r"\s+"," ",str(x or "")).strip()

def first_list(payload):
    if isinstance(payload,list): return payload
    if isinstance(payload,dict):
        for key in ("result","results","data","items","value"):
            v=payload.get(key)
            if isinstance(v,list): return v
        # sometimes API returns a dict keyed by row ids
        vals=[v for v in payload.values() if isinstance(v,dict)]
        if vals:return vals
    return []

def date_candidates(row):
    vals=[]
    if not isinstance(row,dict): return vals
    for k,v in row.items():
        if v is None: continue
        key=str(k).lower()
        if any(t in key for t in ("data","date","rilev","aggiorn","pubblic","protocollo","accad")):
            s=str(v)
            for y,m,d in re.findall(r"(20\d{2})[-/](\d{1,2})[-/](\d{1,2})",s):
                vals.append((int(y),int(m),int(d)))
            for d,m,y in re.findall(r"(\d{1,2})[-/](\d{1,2})[-/](20\d{2})",s):
                vals.append((int(y),int(m),int(d)))
    return vals

def latest_date(rows):
    vals=[]
    for row in rows[:5000]:
        vals.extend(date_candidates(row))
    return f"{max(vals)[0]:04d}-{max(vals)[1]:02d}-{max(vals)[2]:02d}" if vals else ""

def try_params(endpoint):
    # First try the documented endpoint without filters; if the API requires filters,
    # try recent national periods. Keep the successful call only.
    attempts=[
      {},
      {"Regione":"Italia"},
      {"Anno":2026,"Regione":"Italia"},
      {"AnnoAccadimento":2026,"Regione":"Italia"},
      {"AnnoProtocollo":2026,"Regione":"Italia"},
      {"Anno":2026,"Mese":7,"Regione":"Italia"},
      {"AnnoAccadimento":2026,"MeseAccadimento":7,"Regione":"Italia"},
      {"AnnoProtocollo":2026,"MeseProtocollo":7,"Regione":"Italia"},
    ]
    errors=[]
    for params in attempts:
        url=f"{BASE}/{endpoint}"
        if params:url+="?"+urllib.parse.urlencode(params)
        try:
            payload,final,ctype,raw=get_json(url)
            rows=first_list(payload)
            if rows:
                return payload,rows,final,ctype,raw,params
            errors.append(f"{params}: no rows")
        except Exception as exc:
            errors.append(f"{params}: {clean(exc)}")
    raise RuntimeError("; ".join(errors[-4:]))

def acquire(key,endpoint):
    payload,rows,final,ctype,raw,params=try_params(endpoint)
    sample=rows[:3]
    return {
      "key":key,
      "endpoint":endpoint,
      "url":final,
      "params":params,
      "content_type":ctype,
      "row_count":len(rows),
      "latest_date_detected":latest_date(rows),
      "response_sha256":hashlib.sha256(raw).hexdigest(),
      "sample":sample,
      "status":"ok",
    }

def main():
    datasets={}
    failures={}
    for key,endpoint in ENDPOINTS.items():
        try:
            datasets[key]=acquire(key,endpoint)
        except Exception as exc:
            failures[key]=clean(exc)

    if len(datasets)<3:
        raise RuntimeError(f"INAIL: only {len(datasets)} validated endpoints; failures={failures}")

    dates=[v.get("latest_date_detected","") for v in datasets.values() if v.get("latest_date_detected")]
    latest=max(dates) if dates else ""
    snapshot={
      "source":"INAIL",
      "source_family":"INAIL - Open Data infortuni e malattie professionali",
      "api_base":BASE,
      "dataset_count":len(datasets),
      "datasets":datasets,
      "failures":failures,
      "latest_date":latest,
      "checked_at":datetime.now(timezone.utc).isoformat(),
    }
    OUT.write_text(json.dumps(snapshot,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")

    root=json.loads(CATALOG.read_text(encoding="utf-8")) if CATALOG.exists() else {"sources":[]}
    name="INAIL - Open Data infortuni e malattie professionali"
    src=next((x for x in root["sources"] if x.get("name")==name),None)
    if src is None:
        src={}; root["sources"].append(src)
    src.update({
      "name":name,
      "category":"LAVORO_SICUREZZA_IT",
      "topics":["INFORTUNI","MALATTIE_PROFESSIONALI","LAVORO","SALUTE_OCCUPAZIONALE"],
      "official":True,
      "url":"https://dati.inail.it/portale/it.html",
      "access_cost":"free",
      "access_note":"Open API REST e dataset Open Data ufficiali INAIL; licenze secondo dataset.",
      "integration_status":"feed",
      "feed_status":"Attiva · Open API INAIL validate e dati JSON acquisiti automaticamente",
      "notes":f"Feed PULSE su {len(datasets)} endpoint ufficiali INAIL: infortuni e malattie professionali, mensili e semestrali.",
      "level":"Nazionale e regionale secondo endpoint/dataset",
      "frequency":"Mensile e semestrale",
      "latest_period":latest,
      "checked_at":snapshot["checked_at"],
      "provides":[
        {"area":"Lavoro e sicurezza","series":"Infortuni sul lavoro - mensile","description":"Open API INAIL.","latest_period":datasets.get("accidents_monthly",{}).get("latest_date_detected",""),"status":"latest_public"},
        {"area":"Lavoro e sicurezza","series":"Infortuni sul lavoro - semestrale","description":"Open API INAIL.","latest_period":datasets.get("accidents_halfyear",{}).get("latest_date_detected",""),"status":"latest_public"},
        {"area":"Salute occupazionale","series":"Malattie professionali - mensile","description":"Open API INAIL.","latest_period":datasets.get("diseases_monthly",{}).get("latest_date_detected",""),"status":"latest_public"},
        {"area":"Salute occupazionale","series":"Malattie professionali - semestrale","description":"Open API INAIL.","latest_period":datasets.get("diseases_halfyear",{}).get("latest_date_detected",""),"status":"latest_public"}
      ]
    })
    CATALOG.write_text(json.dumps(root,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
    print(json.dumps({"dataset_count":len(datasets),"latest_date":latest,"failures":failures},ensure_ascii=False,indent=2))

if __name__=="__main__":
    main()
