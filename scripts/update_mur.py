#!/usr/bin/env python3
from __future__ import annotations
import hashlib,json,re,urllib.parse,urllib.request
from datetime import datetime,timezone
from pathlib import Path
from bs4 import BeautifulSoup

OUT=Path("data/mur_latest.json");CAT=Path("data/sources_catalog.json")
UA="ISTAT-PULSE/MUR (+https://github.com/pierfido89/ISTAT-PULSE-DATA)"
PAGES=[
 "https://dati-ustat.mur.gov.it/dataset/iscritti",
 "https://dati-ustat.mur.gov.it/dataset/2025-2029-personale-universitario",
 "https://dati-ustat.mur.gov.it/dataset/2025-diritto-allo-studio-universitario-dsu-regionale",
 "https://dati-ustat.mur.gov.it/dataset/2025-contribuzione-e-interventi-atenei"
]

def get(u,probe=False):
 h={"User-Agent":UA,"Accept":"*/*","Accept-Language":"it-IT,it;q=0.9"}
 if probe:h["Range"]="bytes=0-131071"
 req=urllib.request.Request(u,headers=h)
 with urllib.request.urlopen(req,timeout=120) as r:
  b=r.read(131072 if probe else -1);return b,r.geturl(),r.headers.get("Content-Type","")

def parse_page(url):
 raw,final,_=get(url);s=BeautifulSoup(raw.decode("utf-8","ignore"),"html.parser")
 title=s.find("h1").get_text(" ",strip=True) if s.find("h1") else final
 text=" ".join(s.stripped_strings)
 upd=""
 m=re.search(r"Ultimo aggiornamento\s*\|\s*([A-Za-zÀ-ÿ]+)\s+(\d{1,2}),\s*(20\d{2})",text,re.I)
 months={"gennaio":1,"febbraio":2,"marzo":3,"aprile":4,"maggio":5,"giugno":6,"luglio":7,"agosto":8,"settembre":9,"ottobre":10,"novembre":11,"dicembre":12}
 if m and m.group(1).lower() in months:upd=f"{m.group(3)}-{months[m.group(1).lower()]:02d}-{int(m.group(2)):02d}"
 files=[]
 for a in s.find_all("a",href=True):
  lab=" ".join(a.stripped_strings);h=urllib.parse.urljoin(final,a["href"]);low=(lab+" "+h).lower()
  if "download" not in lab.lower() and not any(x in low for x in (".csv",".xlsx",".xls")):continue
  try:
   b,u,ct=get(h,True)
   if len(b)>50 and "text/html" not in ct.lower():
    fmt="CSV" if "csv" in ct.lower() or ".csv" in u.lower() else "XLSX"
    files.append({"title":lab[:160],"format":fmt,"url":u,"content_type":ct,"probe_bytes":len(b),"sha256":hashlib.sha256(b).hexdigest()})
  except Exception:pass
 if not files:raise RuntimeError(title+": no resources")
 return {"title":title,"url":final,"latest_update":upd,"files":files[:8]}

def main():
 datasets=[]
 for p in PAGES:
  try:datasets.append(parse_page(p))
  except Exception:pass
 total=sum(len(x["files"]) for x in datasets)
 if len(datasets)<3 or total<5:raise RuntimeError("MUR: insufficient validated datasets")
 latest=max((d["latest_update"] for d in datasets if d["latest_update"]),default="")
 snap={"source":"Ministero dell'Università e della Ricerca","source_family":"MUR - USTAT Open Data",
       "dataset_count":len(datasets),"validated_resource_count":total,"datasets":datasets,
       "latest_metadata_date":latest,"checked_at":datetime.now(timezone.utc).isoformat(),"status":"feed"}
 OUT.write_text(json.dumps(snap,ensure_ascii=False,indent=2)+"\n")
 root=json.loads(CAT.read_text()) if CAT.exists() else {"sources":[]};name="Ministero Università e Ricerca - USTAT Open Data"
 src=next((x for x in root["sources"] if x.get("name")==name),None)
 if src is None:src={};root["sources"].append(src)
 src.update({"name":name,"category":"UNIVERSITA_RICERCA_IT","topics":["UNIVERSITA","STUDENTI","PERSONALE","DSU","CONTRIBUZIONE"],
   "official":True,"url":"https://ustat.mur.gov.it/opendata/","access_cost":"free","integration_status":"feed",
   "feed_status":"Attiva · CSV/XLSX USTAT validati da catalogo pubblico","frequency":"Annuale e secondo dataset",
   "latest_period":latest,"checked_at":snap["checked_at"]})
 CAT.write_text(json.dumps(root,ensure_ascii=False,indent=2)+"\n")
 print(json.dumps({"datasets":len(datasets),"resources":total,"latest":latest},ensure_ascii=False))
if __name__=="__main__":main()
