#!/usr/bin/env python3
from __future__ import annotations
import hashlib,json,re,urllib.parse,urllib.request\nfrom bs4 import BeautifulSoup
from datetime import datetime,timezone
from pathlib import Path
OUT=Path("data/anac_latest.json");CAT=Path("data/sources_catalog.json")
UA="ISTAT-PULSE/ANAC (+https://github.com/pierfido89/ISTAT-PULSE-DATA)"
API="https://dati.anticorruzione.it/opendata/api/3/action"
def get_json(u):
 req=urllib.request.Request(u,headers={"User-Agent":UA,"Accept":"application/json"})
 with urllib.request.urlopen(req,timeout=120) as r:return json.loads(r.read().decode("utf-8","ignore"))
def get(u):
 req=urllib.request.Request(u,headers={"User-Agent":UA,"Accept":"*/*","Range":"bytes=0-131071"})
 with urllib.request.urlopen(req,timeout=120) as r:return r.read(131072),r.geturl(),r.headers.get("Content-Type","")
def action(name,**params):
 p=get_json(API+"/"+name+"?"+urllib.parse.urlencode(params))
 if not p.get("success"):raise RuntimeError("CKAN action failed")
 return p["result"]
def main():
 search=action("package_search",q="cig OR bdncp OR contratti",rows=20)
 resources=[]
 for pkg in search.get("results",[]):
  for r in pkg.get("resources",[]):
   fmt=str(r.get("format","")).upper();url=r.get("url") or ""
   if fmt not in ("CSV","JSON") and not re.search(r"\.(csv|json)(?:\?|$)",url,re.I):continue
   try:
    b,u,ct=get(url)
    if len(b)>50 and "text/html" not in ct.lower():
     resources.append({"dataset":pkg.get("title",""),"resource":r.get("name",""),"format":fmt or ("CSV" if ".csv" in u.lower() else "JSON"),
      "url":u,"bytes_sampled":len(b),"content_type":ct,"sha256":hashlib.sha256(b).hexdigest(),
      "last_modified":r.get("last_modified") or pkg.get("metadata_modified") or ""})
   except:pass
   if len(resources)>=8:break
  if len(resources)>=8:break
 if not resources:raise RuntimeError("ANAC CKAN: no real CSV/JSON resource validated")
 latest=max((x["last_modified"] for x in resources if x["last_modified"]),default="")
 snap={"source":"ANAC","source_family":"ANAC - BDNCP Open Data","validated_resource_count":len(resources),
 "resources":resources,"latest_metadata_date":latest,"checked_at":datetime.now(timezone.utc).isoformat(),"status":"feed"}
 OUT.write_text(json.dumps(snap,ensure_ascii=False,indent=2)+"\n")
 root=json.loads(CAT.read_text()) if CAT.exists() else {"sources":[]};name="ANAC - BDNCP Open Data"
 src=next((x for x in root["sources"] if x.get("name")==name),None)
 if src is None:src={};root["sources"].append(src)
 src.update({"name":name,"category":"CONTRATTI_PUBBLICI_IT","topics":["APPALTI","CONTRATTI_PUBBLICI","AGGIUDICAZIONI"],
 "official":True,"url":"https://dati.anticorruzione.it/opendata/","access_cost":"free","integration_status":"feed",
 "feed_status":"Attiva · vere risorse BDNCP CSV/JSON validate","frequency":"Mensile","latest_period":latest,"checked_at":snap["checked_at"]})
 CAT.write_text(json.dumps(root,ensure_ascii=False,indent=2)+"\n")
 print(json.dumps({"validated":len(resources),"latest":latest},ensure_ascii=False))
if __name__=="__main__":main()
