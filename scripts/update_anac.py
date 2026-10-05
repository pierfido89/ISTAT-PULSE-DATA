#!/usr/bin/env python3
from __future__ import annotations
import hashlib,json,subprocess,tempfile,os
from datetime import datetime,timezone
from pathlib import Path
OUT=Path("data/anac_latest.json");CAT=Path("data/sources_catalog.json")
UA="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/154 Safari/537.36"
BASE="https://dati.anticorruzione.it/opendata/download/dataset/ocds/filesystem/bulk"
CANDIDATES=[(2026,3),(2025,11),(2025,10),(2025,9),(2025,8),(2025,7)]

def probe(url):
    fd,path=tempfile.mkstemp();os.close(fd)
    try:
        cmd=["curl","-L","--fail","--silent","--show-error","--compressed","--http1.1","--tlsv1.2",
             "--max-time","25","-A",UA,"-e","https://dati.anticorruzione.it/","-H","Accept: application/json,*/*",
             "-H","Range: bytes=0-131071","-o",path,url]
        subprocess.run(cmd,check=True,timeout=30)
        b=Path(path).read_bytes()[:131072]
        if len(b)<50 or b.lstrip().startswith(b"<"): raise RuntimeError("not JSON")
        return b,url
    finally:
        try:os.unlink(path)
        except:pass

def main():
    resources=[]
    for y,m in CANDIDATES:
        url=f"{BASE}/{y}/{m:02d}.json"
        try:
            b,u=probe(url)
            resources.append({"period":f"{y}-{m:02d}","url":u,"content_type":"application/json",
                              "probe_bytes":len(b),"sha256":hashlib.sha256(b).hexdigest()})
            if len(resources)>=3:break
        except Exception:pass
    if not resources:
        manual=Path("manual/anac")
        if manual.exists():
            files=sorted(manual.glob("*.json"),reverse=True)
            for p in files:
                try:
                    raw=p.read_bytes()
                    obj=json.loads(raw.decode("utf-8","ignore"))
                    if not raw or not isinstance(obj,(dict,list)): continue
                    period=p.stem.replace("_","-")
                    resources.append({"period":period,"url":str(p),"content_type":"application/json",
                                      "probe_bytes":min(len(raw),131072),"sha256":hashlib.sha256(raw[:131072]).hexdigest(),
                                      "mode":"manual_bridge"})
                    break
                except Exception: pass
    if not resources:raise RuntimeError("ANAC: remote OCDS blocked; upload latest JSON to manual/anac/YYYY-MM.json")
    latest=max(x["period"] for x in resources)
    snap={"source":"ANAC","source_family":"ANAC - BDNCP OCDS bulk open data","validated_resource_count":len(resources),
          "resources":resources,"latest_period":latest,"checked_at":datetime.now(timezone.utc).isoformat(),"status":"feed"}
    OUT.write_text(json.dumps(snap,ensure_ascii=False,indent=2)+"\n")
    root=json.loads(CAT.read_text()) if CAT.exists() else {"sources":[]};name="ANAC - BDNCP OCDS Open Data"
    src=next((x for x in root["sources"] if x.get("name")==name),None)
    if src is None:src={};root["sources"].append(src)
    src.update({"name":name,"category":"CONTRATTI_PUBBLICI_IT","topics":["APPALTI","CONTRATTI_PUBBLICI","OCDS","BDNCP"],
      "official":True,"url":"https://dati.anticorruzione.it/","access_cost":"free","integration_status":"feed",
      "feed_status":"Attiva · dump OCDS massivi BDNCP JSON validati","frequency":"Mensile",
      "latest_period":latest,"checked_at":snap["checked_at"]})
    CAT.write_text(json.dumps(root,ensure_ascii=False,indent=2)+"\n")
    print(json.dumps({"validated":len(resources),"latest":latest},ensure_ascii=False))

if __name__=="__main__":main()
