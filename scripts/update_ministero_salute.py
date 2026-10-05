#!/usr/bin/env python3
from __future__ import annotations
import hashlib,json,urllib.request
from datetime import datetime,timezone,timedelta
from pathlib import Path

OUT=Path("data/ministero_salute_latest.json");CAT=Path("data/sources_catalog.json")
UA="Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 Chrome/154 Safari/537.36"
BASE="https://www.dati.salute.gov.it/sites/default/files/opendata/"

def probe(u):
 req=urllib.request.Request(u,headers={"User-Agent":UA,"Accept":"*/*","Referer":"https://www.dati.salute.gov.it/"})
 with urllib.request.urlopen(req,timeout=120) as r:
  b=r.read(131072);return b,r.geturl(),r.headers.get("Content-Type","")

def discover(pattern):
 today=datetime.now(timezone.utc).date()
 for delta in range(0,21):
  day=today-timedelta(days=delta);stamp=day.strftime("%Y%m%d")
  u=BASE+pattern.format(date=stamp)
  try:
   b,final,ct=probe(u)
   if len(b)>50 and "text/html" not in ct.lower():
    return {"date":day.isoformat(),"url":final,"content_type":ct,"probe_bytes":len(b),"sha256":hashlib.sha256(b).hexdigest()}
  except Exception:pass
 return None

def main():
 defs={
  "apparecchiature":{"pattern":"DISPO_GAP_80_{date}.csv","title":"Apparecchiature sanitarie"},
  "dispositivi_medici":{"pattern":"DISPO_RDM_1_{date}_csv.zip","title":"Dispositivi medici"}
 }
 datasets={}
 for key,cfg in defs.items():
  r=discover(cfg["pattern"])
  if r:datasets[key]={"title":cfg["title"],**r}
 if len(datasets)<2:raise RuntimeError("Ministero Salute: current official open-data files not validated")
 latest=max(x["date"] for x in datasets.values())
 snap={"source":"Ministero della Salute","source_family":"Ministero della Salute - Open Data",
       "dataset_count":len(datasets),"datasets":datasets,"latest_update":latest,
       "checked_at":datetime.now(timezone.utc).isoformat(),"status":"feed"}
 OUT.write_text(json.dumps(snap,ensure_ascii=False,indent=2)+"\n")
 root=json.loads(CAT.read_text()) if CAT.exists() else {"sources":[]};name="Ministero della Salute - Open Data"
 src=next((x for x in root["sources"] if x.get("name")==name),None)
 if src is None:src={};root["sources"].append(src)
 src.update({"name":name,"category":"SALUTE_IT","topics":["SSN","APPARECCHIATURE","DISPOSITIVI_MEDICI"],
   "official":True,"url":"https://www.dati.salute.gov.it/","access_cost":"free","integration_status":"feed",
   "feed_status":"Attiva · file Open Data ufficiali giornalieri validati","frequency":"Secondo dataset",
   "latest_period":latest,"checked_at":snap["checked_at"]})
 CAT.write_text(json.dumps(root,ensure_ascii=False,indent=2)+"\n")
 print(json.dumps({"datasets":len(datasets),"latest":latest},ensure_ascii=False))
if __name__=="__main__":main()
