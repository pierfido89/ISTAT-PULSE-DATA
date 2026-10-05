#!/usr/bin/env python3
"""Banca d'Italia BDS A2A connector for ISTAT PULSE.

Uses the official A2A REST export service documented by Banca d'Italia.
Monitored initial cubes:
- BSIB0400: banking / monetary statistics
- MIR0300: bank interest rates
- TUEE0140: gross public debt
- TCCE0200: public debt by sector

Outputs:
- data/bancaditalia_latest.json
- updates data/sources_catalog.json
"""
from __future__ import annotations

import hashlib
import io
import json
import re
import urllib.request
import zipfile
from datetime import datetime, timezone
from pathlib import Path

OUT=Path("data/bancaditalia_latest.json")
CATALOG=Path("data/sources_catalog.json")
UA="ISTAT-PULSE/BancaItalia-connector (+https://github.com/pierfido89/ISTAT-PULSE-DATA)"
A2A="https://a2a.bancaditalia.it/infostat/dataservices/export/IT/CSV/DATA/CUBE/BANKITALIA/DIFF"

CUBES={
  "banking_money":{
    "cube":"BSIB0400",
    "label":"Banche e moneta / statistiche bancarie",
    "topic":"MONETA_BANCHE"
  },
  "interest_rates":{
    "cube":"MIR0300",
    "label":"Tassi di interesse bancari",
    "topic":"TASSI_INTERESSE"
  },
  "gross_public_debt":{
    "cube":"TUEE0140",
    "label":"Debito pubblico lordo",
    "topic":"DEBITO_PUBBLICO"
  },
  "public_debt_by_sector":{
    "cube":"TCCE0200",
    "label":"Debito delle amministrazioni pubbliche per settore",
    "topic":"DEBITO_PUBBLICO"
  },
}

def get(url:str, timeout=180):
    req=urllib.request.Request(url,headers={"User-Agent":UA,"Accept":"application/zip,*/*"})
    with urllib.request.urlopen(req,timeout=timeout) as r:
        return r.read(),r.geturl(),r.headers.get("Content-Type","")

def clean(x):
    return re.sub(r"\s+"," ",str(x or "")).strip()

def detect_period(text:str)->str:
    # Prefer YYYY-MM, then quarters, then bare year.
    vals=[]
    for y,m in re.findall(r"\b(20\d{2})[-/](0?[1-9]|1[0-2])\b",text):
        vals.append((int(y)*100+int(m),f"{int(y):04d}-{int(m):02d}"))
    for y,q in re.findall(r"\b(20\d{2})[- ]?Q([1-4])\b",text,re.I):
        vals.append((int(y)*100+int(q)*3,f"{int(y):04d}-Q{int(q)}"))
    for y in re.findall(r"\b(20\d{2})\b",text):
        vals.append((int(y)*100+12,str(int(y))))
    return max(vals,key=lambda x:x[0])[1] if vals else ""

def inspect_zip(raw:bytes)->dict:
    if not raw.startswith(b"PK"):
        raise RuntimeError("A2A response is not a ZIP archive")
    with zipfile.ZipFile(io.BytesIO(raw)) as zf:
        names=[n for n in zf.namelist() if not n.endswith("/")]
        if not names:
            raise RuntimeError("empty BDS archive")
        sample=b""
        total_uncompressed=0
        for n in names[:20]:
            info=zf.getinfo(n)
            total_uncompressed+=info.file_size
            if len(sample)<400000:
                sample+=zf.read(n)[:200000]
        text=sample.decode("utf-8","ignore")
        if not text.strip():
            text=sample.decode("latin-1","ignore")
        return {
          "file_count":len(names),
          "files":names[:20],
          "uncompressed_bytes_sampled":total_uncompressed,
          "latest_period_detected":detect_period(text),
          "sample_sha256":hashlib.sha256(sample).hexdigest(),
        }

def acquire(key,cfg):
    url=f"{A2A}/{cfg['cube']}"
    raw,final,ctype=get(url)
    details=inspect_zip(raw)
    return {
      "key":key,
      "cube":cfg["cube"],
      "label":cfg["label"],
      "topic":cfg["topic"],
      "url":final,
      "content_type":ctype,
      "download_bytes":len(raw),
      "download_sha256":hashlib.sha256(raw).hexdigest(),
      "status":"ok",
      **details,
    }

def main():
    datasets={}
    failures={}
    for key,cfg in CUBES.items():
        try:
            datasets[key]=acquire(key,cfg)
        except Exception as exc:
            failures[key]=clean(exc)

    if len(datasets)<3:
        raise RuntimeError(f"Banca d'Italia: only {len(datasets)} validated cubes; failures={failures}")

    periods=[x.get("latest_period_detected","") for x in datasets.values() if x.get("latest_period_detected")]
    latest=max(periods) if periods else ""
    snapshot={
      "source":"Banca d'Italia",
      "source_family":"Banca d'Italia - Base Dati Statistica",
      "a2a_base":A2A,
      "dataset_count":len(datasets),
      "datasets":datasets,
      "failures":failures,
      "latest_period":latest,
      "checked_at":datetime.now(timezone.utc).isoformat(),
    }
    OUT.write_text(json.dumps(snapshot,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")

    root=json.loads(CATALOG.read_text(encoding="utf-8")) if CATALOG.exists() else {"sources":[]}
    name="Banca d'Italia - Base Dati Statistica"
    src=next((x for x in root["sources"] if x.get("name")==name),None)
    if src is None:
        src={}; root["sources"].append(src)
    src.update({
      "name":name,
      "category":"ECONOMIA_FINANZA_IT",
      "topics":["MONETA","BANCHE","TASSI","CREDITO","DEBITO_PUBBLICO"],
      "official":True,
      "url":"https://www.bancaditalia.it/statistiche/basi-dati/bds/index.html",
      "access_cost":"free",
      "access_note":"Servizi A2A REST ufficiali della Base Dati Statistica di Banca d'Italia.",
      "integration_status":"feed",
      "feed_status":"Attiva · acquisizione automatica BDS via servizi A2A ufficiali",
      "notes":f"Feed PULSE su {len(datasets)} cubi BDS validati: banche/moneta, tassi e debito pubblico.",
      "level":"Nazionale e territoriale secondo cubo BDS",
      "frequency":"Secondo calendario statistico di Banca d'Italia",
      "latest_period":latest,
      "checked_at":snapshot["checked_at"],
      "provides":[
        {"area":"Moneta e banche","series":"Statistiche bancarie e monetarie","description":"Cubo BDS ufficiale acquisito via A2A.","latest_period":datasets.get("banking_money",{}).get("latest_period_detected",""),"status":"latest_public"},
        {"area":"Tassi","series":"Tassi di interesse bancari","description":"Cubo BDS ufficiale acquisito via A2A.","latest_period":datasets.get("interest_rates",{}).get("latest_period_detected",""),"status":"latest_public"},
        {"area":"Finanza pubblica","series":"Debito pubblico","description":"Cubi BDS ufficiali acquisiti via A2A.","latest_period":max([datasets.get("gross_public_debt",{}).get("latest_period_detected",""),datasets.get("public_debt_by_sector",{}).get("latest_period_detected","")]),"status":"latest_public"}
      ]
    })
    CATALOG.write_text(json.dumps(root,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
    print(json.dumps({"dataset_count":len(datasets),"latest_period":latest,"failures":failures},ensure_ascii=False,indent=2))

if __name__=="__main__":
    main()
