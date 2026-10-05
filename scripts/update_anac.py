#!/usr/bin/env python3
from __future__ import annotations
import hashlib, json, re, urllib.parse, urllib.request
from datetime import datetime, timezone
from pathlib import Path

OUT=Path("data/anac_latest.json")
CAT=Path("data/sources_catalog.json")
UA="ISTAT-PULSE/ANAC (+https://github.com/pierfido89/ISTAT-PULSE-DATA)"
API="https://dati.anticorruzione.it/opendata/api/3/action"

def get_json(url):
    req=urllib.request.Request(url,headers={"User-Agent":UA,"Accept":"application/json"})
    with urllib.request.urlopen(req,timeout=120) as r:
        return json.loads(r.read().decode("utf-8","ignore"))

def probe(url):
    req=urllib.request.Request(url,headers={"User-Agent":UA,"Accept":"*/*","Range":"bytes=0-131071"})
    with urllib.request.urlopen(req,timeout=120) as r:
        raw=r.read(131072)
        return raw,r.geturl(),r.headers.get("Content-Type","")

def action(name,**params):
    data=get_json(API+"/"+name+"?"+urllib.parse.urlencode(params))
    if not data.get("success"):
        raise RuntimeError(f"ANAC {name} failed")
    return data["result"]

def main():
    resources=[]
    searches=["CIG","contratti pubblici","BDNCP","aggiudicazioni"]
    seen=set()
    for q in searches:
        try:
            result=action("package_search",q=q,rows=50)
        except Exception:
            continue
        for pkg in result.get("results",[]):
            for r in pkg.get("resources",[]):
                url=r.get("url") or ""
                fmt=str(r.get("format") or "").upper()
                if not url or url in seen: continue
                if fmt not in ("CSV","JSON") and not re.search(r"\.(csv|json)(?:\?|$)",url,re.I):
                    continue
                try:
                    raw,final,ctype=probe(url)
                    if len(raw)<50 or "text/html" in ctype.lower(): continue
                    seen.add(url)
                    resources.append({
                        "dataset":pkg.get("title",""),
                        "resource":r.get("name",""),
                        "format":fmt or ("CSV" if ".csv" in final.lower() else "JSON"),
                        "url":final,
                        "bytes_sampled":len(raw),
                        "content_type":ctype,
                        "sha256":hashlib.sha256(raw).hexdigest(),
                        "last_modified":r.get("last_modified") or pkg.get("metadata_modified") or ""
                    })
                except Exception:
                    pass
                if len(resources)>=8: break
            if len(resources)>=8: break
        if len(resources)>=8: break
    if not resources:
        raise RuntimeError("ANAC: nessuna vera risorsa CSV/JSON BDNCP validata")
    latest=max((x["last_modified"] for x in resources if x["last_modified"]),default="")
    snap={
        "source":"ANAC",
        "source_family":"ANAC - BDNCP Open Data",
        "validated_resource_count":len(resources),
        "resources":resources,
        "latest_metadata_date":latest,
        "checked_at":datetime.now(timezone.utc).isoformat(),
        "status":"feed"
    }
    OUT.write_text(json.dumps(snap,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
    root=json.loads(CAT.read_text()) if CAT.exists() else {"sources":[]}
    name="ANAC - BDNCP Open Data"
    src=next((x for x in root["sources"] if x.get("name")==name),None)
    if src is None: src={}; root["sources"].append(src)
    src.update({
        "name":name,"category":"CONTRATTI_PUBBLICI_IT",
        "topics":["APPALTI","CONTRATTI_PUBBLICI","AGGIUDICAZIONI"],
        "official":True,"url":"https://dati.anticorruzione.it/opendata/",
        "access_cost":"free","integration_status":"feed",
        "feed_status":"Attiva · risorse BDNCP CSV/JSON validate realmente",
        "frequency":"Mensile","latest_period":latest,"checked_at":snap["checked_at"]
    })
    CAT.write_text(json.dumps(root,ensure_ascii=False,indent=2)+"\n")
    print(json.dumps({"validated":len(resources),"latest":latest},ensure_ascii=False))

if __name__=="__main__":
    main()
