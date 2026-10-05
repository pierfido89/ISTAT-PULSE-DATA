#!/usr/bin/env python3
from __future__ import annotations
import hashlib,json,re,urllib.parse,urllib.request
from datetime import datetime,timezone
from pathlib import Path
from bs4 import BeautifulSoup
OUT=Path("data/giustizia_dgstat_latest.json");CAT=Path("data/sources_catalog.json")
UA="ISTAT-PULSE/DGSTAT (+https://github.com/pierfido89/ISTAT-PULSE-DATA)"
PAGES=[
 "https://datiestatistiche.giustizia.it/page/it/monitoraggio-mensile-dei-tribunal",
 "https://datiestatistiche.giustizia.it/page/it/flussi-tribunali-ordinari-e-corti-di-appello",
 "https://datiestatistiche.giustizia.it/page/it/giustizia-flussi-per-ufficio-penale",
 "https://datiestatistiche.giustizia.it/page/it/flussi-dei-giudici-di-pace"
]
def get(u,probe=False):
 h={"User-Agent":UA,"Accept":"*/*","Accept-Language":"it-IT,it;q=0.9"}
 if probe:h["Range"]="bytes=0-131071"
 req=urllib.request.Request(u,headers=h)
 with urllib.request.urlopen(req,timeout=180) as r:
  b=r.read(131072 if probe else -1);return b,r.geturl(),r.headers.get("Content-Type","")
def main():
 datasets=[];resources=[]
 for page in PAGES:
  try:b,u,_=get(page);s=BeautifulSoup(b.decode("utf-8","ignore"),"html.parser")
  except Exception:continue
  title=s.find("h1").get_text(" ",strip=True) if s.find("h1") else u
  text=" ".join(s.stripped_strings)
  period=""
  m=re.search(r"Periodo:\s*([0-9]{4}\s*[-–]\s*[0-9]{4})",text,re.I)
  if m:period=m.group(1).replace(" ","")
  files=[]
  for a in s.find_all("a",href=True):
   h=urllib.parse.urljoin(u,a["href"]);lab=" ".join(a.stripped_strings);low=(lab+" "+h).lower()
   if not any(x in low for x in (".csv",".xlsx",".xls","file dati","scarica")):continue
   try:
    rb,ru,ct=get(h,True)
    if len(rb)>50 and "text/html" not in ct.lower():
     fmt="CSV" if "csv" in ct.lower() or ".csv" in ru.lower() else "XLSX"
     it={"title":lab[:180],"format":fmt,"url":ru,"content_type":ct,"probe_bytes":len(rb),"sha256":hashlib.sha256(rb).hexdigest()}
     files.append(it);resources.append(it)
   except:pass
  if files:datasets.append({"title":title,"url":u,"period":period,"files":files[:4]})
 if len(resources)<2:raise RuntimeError("DGStat: insufficient structured resources")
 snap={"source":"Ministero della Giustizia - DGStat","source_family":"DGStat - Statistiche giudiziarie",
       "dataset_count":len(datasets),"validated_resource_count":len(resources),"datasets":datasets,
       "checked_at":datetime.now(timezone.utc).isoformat(),"status":"feed"}
 OUT.write_text(json.dumps(snap,ensure_ascii=False,indent=2)+"\n")
 root=json.loads(CAT.read_text()) if CAT.exists() else {"sources":[]};name="Ministero della Giustizia - DGStat"
 src=next((x for x in root["sources"] if x.get("name")==name),None)
 if src is None:src={};root["sources"].append(src)
 src.update({"name":name,"category":"GIUSTIZIA_IT","topics":["GIUSTIZIA_CIVILE","GIUSTIZIA_PENALE","UFFICI_GIUDIZIARI"],
   "official":True,"url":"https://datiestatistiche.giustizia.it/","access_cost":"free","integration_status":"feed",
   "feed_status":"Attiva · CSV/XLSX DGStat validati","frequency":"Mensile e annuale","checked_at":snap["checked_at"]})
 CAT.write_text(json.dumps(root,ensure_ascii=False,indent=2)+"\n")
 print(json.dumps({"datasets":len(datasets),"resources":len(resources)},ensure_ascii=False))
if __name__=="__main__":main()
