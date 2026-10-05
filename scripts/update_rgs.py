#!/usr/bin/env python3
from __future__ import annotations
import hashlib,json,re,urllib.parse,urllib.request
from datetime import datetime,timezone
from pathlib import Path

OUT=Path("data/rgs_latest.json")
CAT=Path("data/sources_catalog.json")
UA="ISTAT-PULSE/RGS (+https://github.com/pierfido89/ISTAT-PULSE-DATA)"
API="https://bdap-opendata.rgs.mef.gov.it/SpodCkanApi/api/3/action"

def jget(url):
    req=urllib.request.Request(url,headers={"User-Agent":UA,"Accept":"application/json"})
    with urllib.request.urlopen(req,timeout=120) as r:
        return json.loads(r.read().decode("utf-8","ignore"))

def action(name,**params):
    d=jget(API+"/"+name+"?"+urllib.parse.urlencode(params))
    if not d.get("success"): raise RuntimeError(name+" failed")
    return d["result"]

def probe(url):
    req=urllib.request.Request(url,headers={"User-Agent":UA,"Accept":"*/*","Range":"bytes=0-131071"})
    with urllib.request.urlopen(req,timeout=120) as r:
        b=r.read(131072)
        return b,r.geturl(),r.headers.get("Content-Type","")

def main():
    ids=action("package_list")
    if not isinstance(ids,list) or len(ids)<10: raise RuntimeError("RGS package_list too small")
    wanted=("bilancio","spesa","entrate","opere","sanita","pubblico impiego","amministrazioni pubbliche")
    packages=[]; resources=[]
    for did in ids[:500]:
        try: pkg=action("package_show",id=did)
        except Exception: continue
        text=(" ".join([str(pkg.get("title","")),str(pkg.get("notes","")),str(pkg.get("name",""))])).lower()
        if not any(k in text for k in wanted): continue
        good=[]
        for r in pkg.get("resources",[]):
            url=r.get("url") or ""; fmt=str(r.get("format") or "").upper()
            if not url: continue
            if fmt not in ("CSV","JSON","XLSX","XLS","ZIP") and not re.search(r"\.(csv|json|xlsx?|zip)(?:\?|$)",url,re.I): continue
            try:
                b,u,ct=probe(url)
                if len(b)<50 or "text/html" in ct.lower(): continue
                good.append({"name":r.get("name",""),"format":fmt,"url":u,"content_type":ct,
                    "probe_bytes":len(b),"sha256":hashlib.sha256(b).hexdigest(),
                    "last_modified":r.get("last_modified") or r.get("created") or ""})
            except Exception: pass
        if good:
            packages.append({"title":pkg.get("title",""),"name":pkg.get("name",""),"metadata_modified":pkg.get("metadata_modified",""),"resources":good[:2]})
            resources.extend(good[:2])
        if len(resources)>=8: break
    if len(resources)<3: raise RuntimeError("RGS: insufficient structured resources")
    latest=max((p["metadata_modified"] for p in packages if p["metadata_modified"]),default="")
    snap={"source":"Ragioneria Generale dello Stato","source_family":"RGS - BDAP Open Data",
          "catalog_count":len(ids),"package_count":len(packages),"validated_resource_count":len(resources),
          "packages":packages,"latest_metadata_date":latest,
          "checked_at":datetime.now(timezone.utc).isoformat(),"status":"feed"}
    OUT.write_text(json.dumps(snap,ensure_ascii=False,indent=2)+"\n")
    root=json.loads(CAT.read_text()) if CAT.exists() else {"sources":[]};name="Ragioneria Generale dello Stato - BDAP"
    src=next((x for x in root["sources"] if x.get("name")==name),None)
    if src is None:src={};root["sources"].append(src)
    src.update({"name":name,"category":"FINANZA_PUBBLICA_IT","topics":["BILANCIO_STATO","SPESA_PUBBLICA","ENTRATE","OPERE_PUBBLICHE"],
        "official":True,"url":"https://bdap-opendata.rgs.mef.gov.it/","access_cost":"free","integration_status":"feed",
        "feed_status":"Attiva · API CKAN BDAP validate","frequency":"Secondo dataset","latest_period":latest,"checked_at":snap["checked_at"]})
    CAT.write_text(json.dumps(root,ensure_ascii=False,indent=2)+"\n")
    print(json.dumps({"catalog":len(ids),"packages":len(packages),"resources":len(resources),"latest":latest},ensure_ascii=False))

if __name__=="__main__":main()
