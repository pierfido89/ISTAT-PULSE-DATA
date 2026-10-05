#!/usr/bin/env python3
from __future__ import annotations
import hashlib,json,re,urllib.parse,urllib.request
from datetime import datetime,timezone
from pathlib import Path
from bs4 import BeautifulSoup

OUT=Path("data/mur_latest.json");CAT=Path("data/sources_catalog.json")
UA="ISTAT-PULSE/MUR (+https://github.com/pierfido89/ISTAT-PULSE-DATA)"
ORG="https://dati-ustat.mur.gov.it/organization/ace58834-5a0b-40f6-9b0e-ed6c34ea8de0"

def get(u,probe=False):
 h={"User-Agent":UA,"Accept":"*/*","Accept-Language":"it-IT,it;q=0.9"}
 req=urllib.request.Request(u,headers=h)
 with urllib.request.urlopen(req,timeout=120) as r:
  b=r.read(131072 if probe else -1);return b,r.geturl(),r.headers.get("Content-Type","")

def main():
 raw,final,_=get(ORG);s=BeautifulSoup(raw.decode("utf-8","ignore"),"html.parser")
 pages=[];seen=set()
 for a in s.find_all("a",href=True):
  h=urllib.parse.urljoin(final,a["href"]);lab=" ".join(a.stripped_strings)
  if "/dataset/" not in h or h in seen:continue
  ctx=(lab+" "+h).lower()
  if not any(k in ctx for k in ("2025","iscritt","personale","diritto","contribuzione","afam")):continue
  seen.add(h);pages.append({"title":lab[:200],"url":h})
 datasets=[];resources=[]
 for p in pages[:25]:
  try:b,u,_=get(p["url"]);ps=BeautifulSoup(b.decode("utf-8","ignore"),"html.parser")
  except Exception:continue
  title=ps.find("h1").get_text(" ",strip=True) if ps.find("h1") else p["title"]
  files=[];rseen=set()
  for a in ps.find_all("a",href=True):
   h=urllib.parse.urljoin(u,a["href"]);lab=" ".join(a.stripped_strings);low=(lab+" "+h).lower()
   if h in rseen:continue
   if "/resource/" not in h and "download" not in low and not any(x in low for x in (".csv",".xlsx",".xls")):continue
   # Resource pages often contain the actual Download link.
   targets=[h]
   if "/resource/" in h and "/download/" not in h:
    try:
     rb,ru,_=get(h);rs=BeautifulSoup(rb.decode("utf-8","ignore"),"html.parser")
     targets=[urllib.parse.urljoin(ru,x["href"]) for x in rs.find_all("a",href=True)
              if "download" in (" ".join(x.stripped_strings)+" "+x["href"]).lower()]
    except Exception:targets=[]
   for target in targets[:4]:
    try:
     db,du,ct=get(target,True)
     if len(db)<50 or "text/html" in ct.lower():continue
     fmt="CSV" if "csv" in ct.lower() or ".csv" in du.lower() else "XLSX" if "sheet" in ct.lower() or ".xls" in du.lower() else ""
     if not fmt:continue
     rseen.add(h)
     item={"title":lab[:160],"format":fmt,"url":du,"content_type":ct,"probe_bytes":len(db),"sha256":hashlib.sha256(db).hexdigest()}
     files.append(item);resources.append(item);break
    except Exception:pass
  if files:datasets.append({"title":title,"url":u,"files":files[:6]})
  if len(resources)>=8:break
 if len(datasets)<2 or len(resources)<4:raise RuntimeError("MUR: insufficient validated datasets")
 snap={"source":"Ministero dell'Università e della Ricerca","source_family":"MUR - USTAT Open Data",
       "dataset_count":len(datasets),"validated_resource_count":len(resources),"datasets":datasets,
       "checked_at":datetime.now(timezone.utc).isoformat(),"status":"feed"}
 OUT.write_text(json.dumps(snap,ensure_ascii=False,indent=2)+"\n")
 root=json.loads(CAT.read_text()) if CAT.exists() else {"sources":[]};name="Ministero Università e Ricerca - USTAT Open Data"
 src=next((x for x in root["sources"] if x.get("name")==name),None)
 if src is None:src={};root["sources"].append(src)
 src.update({"name":name,"category":"UNIVERSITA_RICERCA_IT","topics":["UNIVERSITA","STUDENTI","PERSONALE","AFAM","DSU"],
   "official":True,"url":ORG,"access_cost":"free","integration_status":"feed",
   "feed_status":"Attiva · CSV/XLSX USTAT validati","frequency":"Annuale e secondo dataset","checked_at":snap["checked_at"]})
 CAT.write_text(json.dumps(root,ensure_ascii=False,indent=2)+"\n")
 print(json.dumps({"datasets":len(datasets),"resources":len(resources)},ensure_ascii=False))
if __name__=="__main__":main()
