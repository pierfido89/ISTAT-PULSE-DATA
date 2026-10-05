#!/usr/bin/env python3
from __future__ import annotations
import hashlib,json,re,urllib.parse,urllib.request
from datetime import datetime,timezone
from pathlib import Path
from bs4 import BeautifulSoup
OUT=Path("data/unioncamere_infocamere_latest.json");CATALOG=Path("data/sources_catalog.json")
UA="ISTAT-PULSE/Unioncamere-InfoCamere (+https://github.com/pierfido89/ISTAT-PULSE-DATA)"
DATASETS="https://opengovernment.unioncamere.gov.it/dataset";MOVIMPRESE="https://www.infocamere.it/movimprese"
def get(u,timeout=120):
 req=urllib.request.Request(u,headers={"User-Agent":UA,"Accept":"*/*","Accept-Language":"it-IT,it;q=0.9"})
 with urllib.request.urlopen(req,timeout=timeout) as r:return r.read(),r.geturl(),r.headers.get("Content-Type","")
def clean(x):return re.sub(r"\s+"," ",str(x or "")).strip()
def main():
 raw,final,_=get(DATASETS);soup=BeautifulSoup(raw.decode("utf-8","ignore"),"html.parser")
 pages=[];seen=set()
 for a in soup.find_all("a",href=True):
  href=urllib.parse.urljoin(final,a["href"]);title=clean(a.get_text(" ",strip=True))
  if "/dataset/" in href and href.rstrip("/")!=DATASETS.rstrip("/") and href not in seen:
   if any(k in title.lower() for k in ("impres","moviment","consistenza","iscrizioni","cessazioni")):
    seen.add(href);pages.append({"title":title[:220],"url":href})
 datasets=[];csvs=[]
 for p in pages[:25]:
  try:
   b,u,_=get(p["url"]);ps=BeautifulSoup(b.decode("utf-8","ignore"),"html.parser");txt=clean(ps.get_text(" ",strip=True))
   mod="";m=re.search(r"Data ultima modifica dataset:\s*(\d{1,2}/\d{1,2}/20\d{2})",txt,re.I)
   if m:
    d,mo,y=m.group(1).split("/");mod=f"{y}-{int(mo):02d}-{int(d):02d}"
   dist=[]
   for a in ps.find_all("a",href=True):
    href=urllib.parse.urljoin(u,a["href"]);title=clean(a.get_text(" ",strip=True));low=(href+" "+title).lower()
    if any(x in low for x in (".csv","download","scarica")):
     try:
      rb,ru,ct=get(href)
      magic=rb[:300].decode("utf-8","ignore")
      if len(rb)>20 and ("csv" in ct.lower() or ".csv" in ru.lower() or ";" in magic or "," in magic):
       if "text/html" not in ct.lower():
        item={"title":title[:180],"url":ru,"content_type":ct,"bytes":len(rb),"sha256":hashlib.sha256(rb).hexdigest()}
        dist.append(item);csvs.append(item)
     except:pass
   if dist:datasets.append({"title":p["title"],"url":u,"modified":mod,"distributions":dist})
  except:pass
  if len(csvs)>=8:break
 if not csvs:raise RuntimeError("Unioncamere Open Government: no true CSV distributions validated")
 latest=max((d["modified"] for d in datasets if d["modified"]),default="")
 snap={"source":"Unioncamere - InfoCamere","source_family":"Unioncamere - InfoCamere - Open Data imprese",
 "dataset_count":len(datasets),"validated_csv_count":len(csvs),"datasets":datasets,"movimprese_url":MOVIMPRESE,
 "latest_publication_date":latest,"checked_at":datetime.now(timezone.utc).isoformat(),"status":"feed"}
 OUT.write_text(json.dumps(snap,ensure_ascii=False,indent=2)+"\n")
 root=json.loads(CATALOG.read_text()) if CATALOG.exists() else {"sources":[]};name="Unioncamere - InfoCamere - Demografia d'impresa"
 src=next((x for x in root["sources"] if x.get("name")==name),None)
 if src is None:src={};root["sources"].append(src)
 src.update({"name":name,"category":"IMPRESE_IT","topics":["IMPRESE","DEMOGRAFIA_IMPRESE","STARTUP","IMPRENDITORIA"],
 "official":True,"url":DATASETS,"access_cost":"free","integration_status":"feed",
 "feed_status":"Attiva · vere distribuzioni CSV Open Government validate","frequency":"Trimestrale e secondo dataset",
 "latest_period":latest,"checked_at":snap["checked_at"]})
 CATALOG.write_text(json.dumps(root,ensure_ascii=False,indent=2)+"\n")
 print(json.dumps({"datasets":len(datasets),"csv":len(csvs),"latest":latest},ensure_ascii=False))
if __name__=="__main__":main()
