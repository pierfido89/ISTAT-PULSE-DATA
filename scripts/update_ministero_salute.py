#!/usr/bin/env python3
from __future__ import annotations
import json,re,urllib.parse,urllib.request,hashlib
from datetime import datetime,timezone
from pathlib import Path
from bs4 import BeautifulSoup
OUT=Path("data/ministero_salute_latest.json");CAT=Path("data/sources_catalog.json")
UA="ISTAT-PULSE/MinisteroSalute (+https://github.com/pierfido89/ISTAT-PULSE-DATA)"
PORTAL="https://www.dati.salute.gov.it/"
def get(u):
 r=urllib.request.Request(u,headers={"User-Agent":UA,"Accept":"*/*"})
 with urllib.request.urlopen(r,timeout=120) as x:return x.read(),x.geturl(),x.headers.get("Content-Type","")
def main():
 raw,final,ct=get(PORTAL);soup=BeautifulSoup(raw.decode("utf-8","ignore"),"html.parser")
 pages=[]
 for a in soup.find_all("a",href=True):
  href=urllib.parse.urljoin(final,a["href"]);t=" ".join(a.stripped_strings)
  if "/dataset/" in href:pages.append({"title":t[:180],"url":href})
 datasets=[]
 for p in pages[:40]:
  try:
   b,u,c=get(p["url"]);ps=BeautifulSoup(b.decode("utf-8","ignore"),"html.parser")
   files=[]
   for a in ps.find_all("a",href=True):
    h=urllib.parse.urljoin(u,a["href"]);tx=" ".join(a.stripped_strings)
    if any(ext in h.lower() for ext in (".csv",".json",".xml")):files.append({"title":tx[:100],"url":h})
   if files:datasets.append({**p,"files":files[:5]})
  except:pass
  if len(datasets)>=12:break
 if not datasets:raise RuntimeError("Ministero Salute: nessun dataset scaricabile validato")
 snap={"source":"Ministero della Salute","source_family":"Ministero della Salute - Open Data",
 "dataset_count":len(datasets),"datasets":datasets,"checked_at":datetime.now(timezone.utc).isoformat(),"status":"feed"}
 OUT.write_text(json.dumps(snap,ensure_ascii=False,indent=2)+"\n")
 root=json.loads(CAT.read_text()) if CAT.exists() else {"sources":[]};name="Ministero della Salute - Open Data"
 src=next((x for x in root["sources"] if x.get("name")==name),None)
 if src is None:src={};root["sources"].append(src)
 src.update({"name":name,"category":"SALUTE_IT","topics":["SSN","RICOVERI","POSTI_LETTO","PERSONALE_SANITARIO","FARMACIE"],
 "official":True,"url":PORTAL,"access_cost":"free","access_note":"Italian Open Data Licence v2.0.",
 "integration_status":"feed","feed_status":"Attiva · dataset CSV/JSON/XML del Ministero acquisiti automaticamente",
 "frequency":"Secondo dataset","level":"Nazionale, regionale e struttura secondo dataset","checked_at":snap["checked_at"]})
 CAT.write_text(json.dumps(root,ensure_ascii=False,indent=2)+"\n")
 print(json.dumps({"dataset_count":len(datasets)},ensure_ascii=False))
if __name__=="__main__":main()
