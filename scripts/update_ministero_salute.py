#!/usr/bin/env python3
from __future__ import annotations
import hashlib,json,re,urllib.parse,urllib.request
from datetime import datetime,timezone
from pathlib import Path
from bs4 import BeautifulSoup
OUT=Path("data/ministero_salute_latest.json");CAT=Path("data/sources_catalog.json")
UA="ISTAT-PULSE/MinisteroSalute (+https://github.com/pierfido89/ISTAT-PULSE-DATA)"
PAGES={
 "apparecchiature":"https://www.dati.salute.gov.it/it/dataset/apparecchiature-sanitarie/",
 "dispositivi_medici":"https://www.dati.salute.gov.it/it/dataset/dispositivi-medici/"
}
def get(u,probe=False):
 h={"User-Agent":UA,"Accept":"*/*","Accept-Language":"it-IT,it;q=0.9"}
 if probe:h["Range"]="bytes=0-131071"
 req=urllib.request.Request(u,headers=h)
 with urllib.request.urlopen(req,timeout=180) as r:
  b=r.read(131072 if probe else -1);return b,r.geturl(),r.headers.get("Content-Type","")
def iso_date(text):
 m=re.search(r"Data ultimo aggiornamento\s*(\d{2})/(\d{2})/(20\d{2})",text,re.I)
 return f"{m.group(3)}-{m.group(2)}-{m.group(1)}" if m else ""
def main():
 datasets={}
 for key,page in PAGES.items():
  raw,final,_=get(page);s=BeautifulSoup(raw.decode("utf-8","ignore"),"html.parser");text=" ".join(s.stripped_strings)
  files=[]
  for a in s.find_all("a",href=True):
   h=urllib.parse.urljoin(final,a["href"]);low=h.lower()
   if "/sites/default/files/opendata/" not in low:continue
   if not any(x in low for x in (".csv",".json",".xml",".zip")):continue
   try:
    b,u,ct=get(h,True)
    if len(b)>50 and "text/html" not in ct.lower():
     fmt="CSV" if ".csv" in low else "JSON" if ".json" in low else "XML" if ".xml" in low else "ZIP"
     files.append({"format":fmt,"url":u,"content_type":ct,"probe_bytes":len(b),"sha256":hashlib.sha256(b).hexdigest()})
   except Exception:pass
  if files:datasets[key]={"page":final,"latest_update":iso_date(text),"files":files}
 if len(datasets)<2:raise RuntimeError("Ministero Salute: official download links not validated")
 latest=max((d["latest_update"] for d in datasets.values() if d["latest_update"]),default="")
 snap={"source":"Ministero della Salute","source_family":"Ministero della Salute - Open Data",
       "dataset_count":len(datasets),"datasets":datasets,"latest_update":latest,
       "checked_at":datetime.now(timezone.utc).isoformat(),"status":"feed"}
 OUT.write_text(json.dumps(snap,ensure_ascii=False,indent=2)+"\n")
 root=json.loads(CAT.read_text()) if CAT.exists() else {"sources":[]};name="Ministero della Salute - Open Data"
 src=next((x for x in root["sources"] if x.get("name")==name),None)
 if src is None:src={};root["sources"].append(src)
 src.update({"name":name,"category":"SALUTE_IT","topics":["SSN","APPARECCHIATURE","DISPOSITIVI_MEDICI"],
   "official":True,"url":"https://www.dati.salute.gov.it/","access_cost":"free","integration_status":"feed",
   "feed_status":"Attiva · download ufficiali CSV/JSON/XML validati","frequency":"Giornaliera/settimanale secondo dataset",
   "latest_period":latest,"checked_at":snap["checked_at"]})
 CAT.write_text(json.dumps(root,ensure_ascii=False,indent=2)+"\n")
 print(json.dumps({"datasets":len(datasets),"latest":latest},ensure_ascii=False))
if __name__=="__main__":main()
