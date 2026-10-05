#!/usr/bin/env python3
from __future__ import annotations
import hashlib,json,re,urllib.parse,urllib.request
from datetime import datetime,timezone
from pathlib import Path
from bs4 import BeautifulSoup

OUT=Path("data/giustizia_dgstat_latest.json");CAT=Path("data/sources_catalog.json")
UA="ISTAT-PULSE/DGSTAT (+https://github.com/pierfido89/ISTAT-PULSE-DATA)"
START=[
 "https://www.giustizia.it/giustizia/it/mg_1_14.page",
 "https://www.giustizia.it/giustizia/it/pubblicazioni_studi_ricerche.page"
]
KEYS=("statistic","civile","penale","procedimenti","uffici giudiziari","pendenze","iscritti","definiti")

def get(u,probe=False):
 h={"User-Agent":UA,"Accept":"*/*","Accept-Language":"it-IT,it;q=0.9"}
 if probe:h["Range"]="bytes=0-131071"
 req=urllib.request.Request(u,headers=h)
 with urllib.request.urlopen(req,timeout=180) as r:
  b=r.read(131072 if probe else -1);return b,r.geturl(),r.headers.get("Content-Type","")

def main():
 pages=[];seen=set();resources=[]
 for seed in START:
  try:b,u,_=get(seed)
  except Exception:continue
  soup=BeautifulSoup(b.decode("utf-8","ignore"),"html.parser")
  for a in soup.find_all("a",href=True):
   h=urllib.parse.urljoin(u,a["href"]);t=" ".join(a.stripped_strings)
   low=(t+" "+h).lower()
   if any(k in low for k in KEYS) and h not in seen:
    seen.add(h);pages.append({"title":t[:220],"url":h})
 for p in pages[:80]:
  try:b,u,_=get(p["url"]);ps=BeautifulSoup(b.decode("utf-8","ignore"),"html.parser")
  except Exception:continue
  title=(ps.find("h1").get_text(" ",strip=True) if ps.find("h1") else p["title"])
  for a in ps.find_all("a",href=True):
   h=urllib.parse.urljoin(u,a["href"]);lab=" ".join(a.stripped_strings);low=(lab+" "+h).lower()
   if not any(x in low for x in (".csv",".xlsx",".xls",".ods",".zip","scarica","download")):continue
   try:
    rb,ru,ct=get(h,True)
    if len(rb)<50 or "text/html" in ct.lower():continue
    fmt="XLSX" if "spreadsheet" in ct.lower() or ".xls" in ru.lower() else "CSV" if "csv" in ct.lower() or ".csv" in ru.lower() else "ZIP"
    resources.append({"page_title":title,"resource_title":lab[:180],"format":fmt,"url":ru,"content_type":ct,
      "probe_bytes":len(rb),"probe_sha256":hashlib.sha256(rb).hexdigest()})
   except Exception:pass
   if len(resources)>=8:break
  if len(resources)>=8:break
 if not resources:raise RuntimeError("DGStat: nessuna risorsa statistica strutturata validata")
 snap={"source":"Ministero della Giustizia - DGStat","source_family":"DGStat - Statistiche giudiziarie",
  "validated_resource_count":len(resources),"resources":resources,
  "checked_at":datetime.now(timezone.utc).isoformat(),"status":"feed"}
 OUT.write_text(json.dumps(snap,ensure_ascii=False,indent=2)+"\n")
 root=json.loads(CAT.read_text()) if CAT.exists() else {"sources":[]};name="Ministero della Giustizia - DGStat"
 src=next((x for x in root["sources"] if x.get("name")==name),None)
 if src is None:src={};root["sources"].append(src)
 src.update({"name":name,"category":"GIUSTIZIA_IT","topics":["GIUSTIZIA_CIVILE","GIUSTIZIA_PENALE","UFFICI_GIUDIZIARI"],
  "official":True,"url":"https://www.giustizia.it/","access_cost":"free","integration_status":"feed",
  "feed_status":"Attiva · risorse statistiche DGStat strutturate validate","frequency":"Secondo pubblicazione",
  "checked_at":snap["checked_at"]})
 CAT.write_text(json.dumps(root,ensure_ascii=False,indent=2)+"\n")
 print(json.dumps({"validated":len(resources)},ensure_ascii=False))
if __name__=="__main__":main()
