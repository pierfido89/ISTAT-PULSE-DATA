#!/usr/bin/env python3
from __future__ import annotations
import hashlib,json,re,urllib.parse,urllib.request
from datetime import datetime,timezone
from pathlib import Path

API="https://opendata.inps.it/opendata/api/3/action"
OUT=Path("data/inps_latest.json")
CAT=Path("data/sources_catalog.json")
UA="ISTAT-PULSE/INPS (+https://github.com/pierfido89/ISTAT-PULSE-DATA)"
FAMILIES={
 "labour_market":["assunzioni","cessazioni","rapporti di lavoro","occupazione"],
 "pensions":["pensioni","pensionamento","pensionati"],
 "single_allowance":["assegno unico","universale","auu"],
}

def get_json(url):
    req=urllib.request.Request(url,headers={"User-Agent":UA,"Accept":"application/json"})
    with urllib.request.urlopen(req,timeout=120) as r:
        return json.loads(r.read().decode("utf-8","ignore"))

def action(name,**params):
    d=get_json(API+"/"+name+"?"+urllib.parse.urlencode(params))
    if not d.get("success"): raise RuntimeError(name+" failed")
    return d["result"]

def probe(url):
    req=urllib.request.Request(url,headers={"User-Agent":UA,"Accept":"*/*","Range":"bytes=0-65535"})
    with urllib.request.urlopen(req,timeout=120) as r:
        raw=r.read(65536)
        return {"url":r.geturl(),"bytes":len(raw),"content_type":r.headers.get("Content-Type",""),"sha256":hashlib.sha256(raw).hexdigest()}

def main():
    ids=action("package_list")
    if not isinstance(ids,list) or not ids: raise RuntimeError("INPS package_list vuoto")
    families={k:[] for k in FAMILIES}
    validated=0
    for did in ids:
        try: pkg=action("package_show",id=did)
        except Exception: continue
        text=(" ".join([str(pkg.get("title","")),str(pkg.get("notes","")),str(pkg.get("name",""))])).lower()
        hits=[k for k,words in FAMILIES.items() if any(w in text for w in words)]
        if not hits: continue
        good=[]
        for r in pkg.get("resources",[]):
            url=r.get("url") or ""
            if not url: continue
            fmt=str(r.get("format","")).upper()
            try:
                p=probe(url)
                if p["bytes"]<=0 or "text/html" in p["content_type"].lower(): continue
                good.append({"name":r.get("name",""),"format":fmt,"last_modified":r.get("last_modified") or r.get("created") or "",**p})
                validated+=1
                break
            except Exception: pass
        if good:
            item={"id":pkg.get("id"),"title":pkg.get("title",""),"metadata_modified":pkg.get("metadata_modified",""),"resource":good[0]}
            for k in hits:
                if len(families[k])<5: families[k].append(item)
        if all(families[k] for k in families): break
    missing=[k for k,v in families.items() if not v]
    if missing: raise RuntimeError("INPS famiglie mancanti: "+",".join(missing))
    latest=max((x.get("metadata_modified","") for arr in families.values() for x in arr),default="")
    snap={"source":"INPS","source_family":"INPS - Open Data e Osservatori statistici","catalog_count":len(ids),
          "families":families,"validated_resource_count":validated,"latest_metadata_date":latest,
          "checked_at":datetime.now(timezone.utc).isoformat(),"status":"feed"}
    OUT.write_text(json.dumps(snap,ensure_ascii=False,indent=2)+"\n")
    root=json.loads(CAT.read_text()) if CAT.exists() else {"sources":[]};name="INPS - Open Data e Osservatori statistici"
    src=next((x for x in root["sources"] if x.get("name")==name),None)
    if src is None:src={};root["sources"].append(src)
    src.update({"name":name,"category":"SOCIALE_LAVORO_IT","topics":["LAVORO","PENSIONI","WELFARE","ASSEGNO_UNICO"],
      "official":True,"url":"https://www.inps.it/it/it/dati-e-bilanci/open-data.html","access_cost":"free",
      "integration_status":"feed","feed_status":"Attiva · package_list/package_show INPS e risorse ufficiali validate",
      "frequency":"Secondo calendario INPS","latest_period":latest,"checked_at":snap["checked_at"]})
    CAT.write_text(json.dumps(root,ensure_ascii=False,indent=2)+"\n")
    print(json.dumps({"catalog":len(ids),"validated":validated,"latest":latest},ensure_ascii=False))

if __name__=="__main__":main()
