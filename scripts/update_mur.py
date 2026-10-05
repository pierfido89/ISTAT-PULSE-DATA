#!/usr/bin/env python3
from __future__ import annotations
import hashlib,json,urllib.parse,urllib.request
from datetime import datetime,timezone
from pathlib import Path

OUT=Path("data/mur_latest.json"); CAT=Path("data/sources_catalog.json")
UA="ISTAT-PULSE/MUR (+https://github.com/pierfido89/ISTAT-PULSE-DATA)"
API="https://dati-ustat.mur.gov.it/api/3/action"

def jget(url):
    req=urllib.request.Request(url,headers={"User-Agent":UA,"Accept":"application/json"})
    with urllib.request.urlopen(req,timeout=180) as r:
        return json.loads(r.read().decode("utf-8","ignore"))
def action(name,**params):
    d=jget(API+"/"+name+"?"+urllib.parse.urlencode(params))
    if not d.get("success"): raise RuntimeError(name+" failed")
    return d["result"]
def probe(url):
    req=urllib.request.Request(url,headers={"User-Agent":UA,"Accept":"*/*","Range":"bytes=0-131071"})
    with urllib.request.urlopen(req,timeout=180) as r:
        b=r.read(131072); return b,r.geturl(),r.headers.get("Content-Type","")

def main():
    result=action("package_search",q="studenti OR personale OR contribuzione OR AFAM OR diritto allo studio",rows=50)
    resources=[]
    packages=[]
    for pkg in result.get("results",[]):
        good=[]
        for r in pkg.get("resources",[]):
            fmt=str(r.get("format","")).upper(); url=r.get("url") or ""
            if fmt not in ("CSV","XLSX","XLS","JSON") and not any(x in url.lower() for x in (".csv",".xlsx",".xls",".json")): continue
            try:
                b,u,ct=probe(url)
                if len(b)<50 or "text/html" in ct.lower(): continue
                good.append({"name":r.get("name",""),"format":fmt,"url":u,"content_type":ct,
                             "probe_bytes":len(b),"sha256":hashlib.sha256(b).hexdigest(),
                             "last_modified":r.get("last_modified") or r.get("created") or ""})
            except Exception: pass
        if good:
            packages.append({"title":pkg.get("title",""),"name":pkg.get("name",""),"metadata_modified":pkg.get("metadata_modified",""),"resources":good[:3]})
            resources.extend(good[:3])
        if len(packages)>=10: break
    if len(resources)<5: raise RuntimeError("MUR: meno di 5 risorse strutturate validate")
    latest=max((p.get("metadata_modified","") for p in packages),default="")
    snap={"source":"Ministero dell'Università e della Ricerca","source_family":"MUR - USTAT Open Data",
          "package_count":len(packages),"validated_resource_count":len(resources),"packages":packages,
          "latest_metadata_date":latest,"checked_at":datetime.now(timezone.utc).isoformat(),"status":"feed"}
    OUT.write_text(json.dumps(snap,ensure_ascii=False,indent=2)+"\n")
    root=json.loads(CAT.read_text()) if CAT.exists() else {"sources":[]}; name="Ministero Università e Ricerca - USTAT Open Data"
    src=next((x for x in root["sources"] if x.get("name")==name),None)
    if src is None: src={}; root["sources"].append(src)
    src.update({"name":name,"category":"UNIVERSITA_RICERCA_IT","topics":["UNIVERSITA","STUDENTI","PERSONALE","AFAM","DSU"],
                "official":True,"url":"https://ustat.mur.gov.it/opendata/","access_cost":"free","integration_status":"feed",
                "feed_status":"Attiva · CSV/XLSX USTAT validati","frequency":"Annuale e secondo dataset",
                "latest_period":latest,"checked_at":snap["checked_at"]})
    CAT.write_text(json.dumps(root,ensure_ascii=False,indent=2)+"\n")
    print(json.dumps({"packages":len(packages),"resources":len(resources),"latest":latest},ensure_ascii=False))

if __name__=="__main__": main()
