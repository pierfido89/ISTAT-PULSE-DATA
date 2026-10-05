#!/usr/bin/env python3
from __future__ import annotations
import hashlib,json,requests
from datetime import datetime,timezone
from pathlib import Path
OUT=Path("data/anac_latest.json");CAT=Path("data/sources_catalog.json")
UA="Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 Chrome/154 Safari/537.36"
BASE="https://dati.anticorruzione.it/opendata/download/dataset/ocds/filesystem/bulk"
def probe(url):
 r=requests.get(url,headers={"User-Agent":UA,"Accept":"application/json,*/*","Referer":"https://dati.anticorruzione.it/"},timeout=45,stream=True,allow_redirects=True)
 if r.status_code!=200: raise RuntimeError(f"HTTP {r.status_code}")
 b=next(r.iter_content(131072),b"")
 ct=r.headers.get("Content-Type","")
 if len(b)<50 or "text/html" in ct.lower(): raise RuntimeError("not JSON payload")
 return b,r.url,ct
def main():
 resources=[]
 now=datetime.now(timezone.utc)
 candidates=[]
 for y in (now.year,now.year-1):
  for m in range(12,0,-1):
   if y==now.year and m>now.month:continue
   candidates.append((y,m))
 for y,m in candidates[:18]:
  url=f"{BASE}/{y}/{m:02d}.json"
  try:
   b,u,ct=probe(url)
   resources.append({"period":f"{y}-{m:02d}","url":u,"content_type":ct,"probe_bytes":len(b),"sha256":hashlib.sha256(b).hexdigest()})
   if len(resources)>=3:break
  except Exception:pass
 if not resources:raise RuntimeError("ANAC: no OCDS bulk JSON reachable")
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
