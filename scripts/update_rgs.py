#!/usr/bin/env python3
from __future__ import annotations
import json,re,urllib.parse,urllib.request
from datetime import datetime,timezone
from pathlib import Path
from bs4 import BeautifulSoup
OUT=Path("data/rgs_latest.json");CAT=Path("data/sources_catalog.json")
UA="ISTAT-PULSE/RGS (+https://github.com/pierfido89/ISTAT-PULSE-DATA)"
PAGES=[
 "https://bdap-opendata.rgs.mef.gov.it/catalog/",
 "https://bdap-opendata.rgs.mef.gov.it/parola-chiave/spesa",
 "https://bdap-opendata.rgs.mef.gov.it/parola-chiave/opere-pubbliche"
]
def get(u):
 req=urllib.request.Request(u,headers={"User-Agent":UA,"Accept":"text/html,*/*","Accept-Language":"it-IT,it;q=0.9"})
 with urllib.request.urlopen(req,timeout=90) as r:return r.read(),r.geturl(),r.headers.get("Content-Type","")
def main():
 datasets=[];seen=set();latest=""
 for page in PAGES:
  try:b,u,_=get(page)
  except Exception:continue
  s=BeautifulSoup(b.decode("utf-8","ignore"),"html.parser");text=" ".join(s.stripped_strings)
  for d,mo,y in re.findall(r"(\d{2})/(\d{2})/(20\d{2})",text):
   iso=f"{y}-{mo}-{d}"
   if iso>latest:latest=iso
  for a in s.find_all("a",href=True):
   h=urllib.parse.urljoin(u,a["href"]);lab=" ".join(a.stripped_strings).strip()
   if not lab or h in seen:continue
   low=(lab+" "+h).lower()
   if "/content/" in h or "/opendata/" in h:
    if any(k in low for k in ("rendiconto","spese","entrate","opere pubbliche","pagamenti bilancio")):
     seen.add(h);datasets.append({"title":lab[:240],"url":h})
 if len(datasets)<5:raise RuntimeError("RGS BDAP catalog monitor: insufficient official datasets")
 snap={"source":"Ragioneria Generale dello Stato","source_family":"RGS - BDAP Open Data catalog",
   "dataset_count":len(datasets),"datasets":datasets[:50],"latest_catalog_date":latest,
   "api_url":"https://bdap-opendata.rgs.mef.gov.it/content/api",
   "checked_at":datetime.now(timezone.utc).isoformat(),"status":"feed"}
 OUT.write_text(json.dumps(snap,ensure_ascii=False,indent=2)+"\n")
 root=json.loads(CAT.read_text()) if CAT.exists() else {"sources":[]};name="Ragioneria Generale dello Stato - BDAP"
 src=next((x for x in root["sources"] if x.get("name")==name),None)
 if src is None:src={};root["sources"].append(src)
 src.update({"name":name,"category":"FINANZA_PUBBLICA_IT","topics":["BILANCIO_STATO","SPESA_PUBBLICA","ENTRATE","OPERE_PUBBLICHE"],
   "official":True,"url":"https://bdap-opendata.rgs.mef.gov.it/","access_cost":"free","integration_status":"feed",
   "feed_status":"Attiva · monitor catalogo Open BDAP; API CKAN ufficiale disponibile separatamente",
   "frequency":"Secondo pubblicazione","latest_period":latest,"checked_at":snap["checked_at"]})
 CAT.write_text(json.dumps(root,ensure_ascii=False,indent=2)+"\n")
 print(json.dumps({"datasets":len(datasets),"latest":latest},ensure_ascii=False))
if __name__=="__main__":main()
