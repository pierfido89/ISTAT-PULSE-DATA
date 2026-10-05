#!/usr/bin/env python3
"""INPS Open Data connector for ISTAT PULSE.

Uses the official INPS CKAN API to discover and validate public datasets.
Initial monitored families:
- labour market / employment flows
- pensions
- Assegno Unico Universale

Outputs:
- data/inps_latest.json
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

API="https://opendata.inps.it/opendata/api/3/action"
CATALOG=Path("data/sources_catalog.json")
OUT=Path("data/inps_latest.json")
UA="ISTAT-PULSE/INPS-connector (+https://github.com/pierfido89/ISTAT-PULSE-DATA)"

QUERIES={
  "labour_market":[
    "assunzioni trasformazioni cessazioni",
    "mercato del lavoro",
    "rapporti di lavoro"
  ],
  "pensions":[
    "pensioni",
    "flussi pensionamento"
  ],
  "single_allowance":[
    "assegno unico universale",
    "AUU"
  ]
}

PREFERRED_FORMATS=("CSV","JSON","XLSX","XLS","XML","SDMX-CSV","SDMX-JSON")

def http_json(url:str, timeout=120):
    req=urllib.request.Request(url,headers={"User-Agent":UA,"Accept":"application/json"})
    with urllib.request.urlopen(req,timeout=timeout) as r:
        return json.loads(r.read().decode("utf-8","ignore"))

def action(name:str, **params):
    url=API+"/"+name+"?"+urllib.parse.urlencode(params)
    payload=http_json(url)
    if not payload.get("success"):
        raise RuntimeError(f"INPS API {name} failed")
    return payload.get("result")

def clean(x):
    return re.sub(r"\s+"," ",str(x or "")).strip()

def date_key(s):
    if not s:return ""
    m=re.search(r"(20\d{2})[-/](\d{1,2})[-/](\d{1,2})",s)
    if m:return f"{int(m.group(1)):04d}-{int(m.group(2)):02d}-{int(m.group(3)):02d}"
    m=re.search(r"(20\d{2})[-/](\d{1,2})",s)
    if m:return f"{int(m.group(1)):04d}-{int(m.group(2)):02d}"
    return ""

def choose_resource(package):
    resources=package.get("resources") or []
    if not resources:return None
    def rank(r):
        fmt=clean(r.get("format")).upper()
        score=0
        if fmt in PREFERRED_FORMATS: score+=100-PREFERRED_FORMATS.index(fmt)
        url=clean(r.get("url")).lower()
        if any(x in url for x in (".csv",".json",".xlsx",".xls",".xml")): score+=25
        if clean(r.get("last_modified") or r.get("created")): score+=10
        return score
    return max(resources,key=rank)

def probe(url, timeout=120):
    if not url:return {}
    req=urllib.request.Request(url,headers={
      "User-Agent":UA,
      "Accept":"*/*",
      "Range":"bytes=0-65535",
    })
    with urllib.request.urlopen(req,timeout=timeout) as r:
        raw=r.read(65536)
        return {
          "probe_url":r.geturl(),
          "probe_bytes":len(raw),
          "probe_content_type":r.headers.get("Content-Type",""),
          "probe_sha256":hashlib.sha256(raw).hexdigest(),
        }

def search_family(terms):
    candidates={}
    for term in terms:
        result=action("package_search",q=term,rows=20)
        for pkg in result.get("results",[]):
            candidates[pkg.get("id") or pkg.get("name")]=pkg
    ranked=[]
    for pkg in candidates.values():
        text=(" "+clean(pkg.get("title"))+" "+clean(pkg.get("notes"))+" "+clean(pkg.get("name"))).lower()
        score=sum(5 for t in terms if t.lower() in text)
        score+=sum(1 for token in re.findall(r"[a-zà-ÿ]{4,}", " ".join(terms).lower()) if token in text)
        ranked.append((score,pkg))
    ranked.sort(key=lambda x:(x[0],date_key(x[1].get("metadata_modified"))),reverse=True)
    return [p for _,p in ranked[:5]]

def normalize_package(pkg):
    res=choose_resource(pkg)
    item={
      "id":pkg.get("id") or pkg.get("name"),
      "name":pkg.get("name"),
      "title":clean(pkg.get("title")),
      "notes":clean(pkg.get("notes"))[:500],
      "metadata_created":pkg.get("metadata_created",""),
      "metadata_modified":pkg.get("metadata_modified",""),
      "organization":clean((pkg.get("organization") or {}).get("title")),
      "resource_count":len(pkg.get("resources") or []),
    }
    if res:
        item["resource"]={
          "name":clean(res.get("name")),
          "format":clean(res.get("format")),
          "url":clean(res.get("url")),
          "last_modified":res.get("last_modified") or res.get("created") or "",
        }
        try:item["resource"].update(probe(item["resource"]["url"]))
        except Exception as exc:item["resource"]["probe_error"]=clean(exc)
    return item

def main():
    # Basic API liveness.
    package_ids=action("package_list")
    if not isinstance(package_ids,list) or len(package_ids)<10:
        raise RuntimeError("INPS package_list returned too few datasets")

    families={}
    for family,terms in QUERIES.items():
        packages=search_family(terms)
        normalized=[normalize_package(p) for p in packages]
        if not normalized:
            raise RuntimeError(f"INPS family {family}: no datasets found")
        families[family]=normalized

    # Require at least one downloadable/probeable resource in every monitored family.
    for family,items in families.items():
        if not any((x.get("resource") or {}).get("probe_bytes",0)>0 for x in items):
            raise RuntimeError(f"INPS family {family}: no validated public resource")

    all_items=[x for items in families.values() for x in items]
    latest=max((date_key(x.get("metadata_modified")) for x in all_items),default="")
    snapshot={
      "source":"INPS",
      "source_family":"INPS - Open Data e Osservatori statistici",
      "api_base":API,
      "dataset_catalog_count":len(package_ids),
      "families":families,
      "family_count":len(families),
      "validated_resource_count":sum(
        1 for x in all_items if (x.get("resource") or {}).get("probe_bytes",0)>0
      ),
      "latest_metadata_date":latest,
      "checked_at":datetime.now(timezone.utc).isoformat(),
    }
    OUT.write_text(json.dumps(snapshot,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")

    root=json.loads(CATALOG.read_text(encoding="utf-8")) if CATALOG.exists() else {"sources":[]}
    name="INPS - Open Data e Osservatori statistici"
    src=next((x for x in root["sources"] if x.get("name")==name),None)
    if src is None:
        src={}; root["sources"].append(src)
    src.update({
      "name":name,
      "category":"SOCIALE_LAVORO_IT",
      "topics":["LAVORO","PENSIONI","WELFARE","ASSEGNO_UNICO"],
      "official":True,
      "url":"https://www.inps.it/it/it/dati-e-bilanci/open-data.html",
      "access_cost":"free",
      "access_note":"API e dataset Open Data ufficiali INPS; rispettare la licenza specifica di ciascun dataset.",
      "integration_status":"feed",
      "feed_status":"Attiva · API Open Data INPS validate e risorse ufficiali acquisite automaticamente",
      "notes":"Feed PULSE basato sulle API ufficiali INPS. Monitora mercato del lavoro, pensioni e Assegno Unico; l'architettura è estendibile agli altri osservatori.",
      "level":"Nazionale e territoriale secondo dataset",
      "frequency":"Secondo calendario di pubblicazione INPS",
      "latest_period":latest,
      "checked_at":snapshot["checked_at"],
      "provides":[
        {"area":"Lavoro","series":"Assunzioni, trasformazioni e cessazioni","description":"Dataset ufficiali INPS sul mercato del lavoro.","latest_period":latest,"status":"latest_public"},
        {"area":"Pensioni","series":"Prestazioni e flussi di pensionamento","description":"Dataset ufficiali INPS sugli osservatori pensionistici.","latest_period":latest,"status":"latest_public"},
        {"area":"Welfare","series":"Assegno Unico Universale","description":"Dataset ufficiali INPS sull'Assegno Unico Universale.","latest_period":latest,"status":"latest_public"}
      ]
    })
    CATALOG.write_text(json.dumps(root,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
    print(json.dumps({
      "dataset_catalog_count":snapshot["dataset_catalog_count"],
      "family_count":snapshot["family_count"],
      "validated_resource_count":snapshot["validated_resource_count"],
      "latest_metadata_date":latest,
    },ensure_ascii=False,indent=2))

if __name__=="__main__":
    main()
