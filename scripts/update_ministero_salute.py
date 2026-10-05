#!/usr/bin/env python3
from __future__ import annotations
import json,re,urllib.parse,urllib.request,hashlib
from datetime import datetime,timezone
from pathlib import Path
from bs4 import BeautifulSoup
OUT=Path("data/ministero_salute_latest.json");CAT=Path("data/sources_catalog.json")
UA="ISTAT-PULSE/MinisteroSalute (+https://github.com/pierfido89/ISTAT-PULSE-DATA)"
PORTAL="https://www.dati.salute.gov.it/"
KNOWN_PAGES=[
 "https://www.dati.salute.gov.it/it/dataset/apparecchiature-sanitarie/",
 "https://www.dati.salute.gov.it/it/dataset/dispositivi-medici/",
 "https://www.dati.salute.gov.it/it/dataset/utenti-carico-secondo-la-sostanza-dabuso-primaria-anno-2025/",
 "https://www.dati.salute.gov.it/it/dataset/personale-dei-serd-anno-2024/",
]
def get(u,probe=False):
 headers={"User-Agent":UA,"Accept":"*/*"}
 if probe: headers["Range"]="bytes=0-131071"
 r=urllib.request.Request(u,headers=headers)
 with urllib.request.urlopen(r,timeout=180) as x:
  return x.read(131072 if probe else -1),x.geturl(),x.headers.get("Content-Type","")
def main():
 pages=[{"title":"","url":u} for u in KNOWN_PAGES]
 datasets=[]
 for p in pages[:40]:
  try:
   b,u,c=get(p["url"]);ps=BeautifulSoup(b.decode("utf-8","ignore"),"html.parser")
   files=[]
   for a in ps.find_all("a",href=True):
    h=urllib.parse.urljoin(u,a["href"]);tx=" ".join(a.stripped_strings)
    low=(tx+" "+h).lower()
    if any(k in low for k in ("scarica","csv","json","xml")):
     try:
      rb,ru,rct=get(h,True)
      if len(rb)>30 and "text/html" not in rct.lower():
       files.append({"title":tx[:100],"url":ru,"content_type":rct,"bytes":len(rb),"sha256":hashlib.sha256(rb[:131072]).hexdigest()})
     except:pass
   if files:
    title=ps.find("h1").get_text(" ",strip=True) if ps.find("h1") else p["url"]
    txt=" ".join(ps.stripped_strings)
    m=re.search(r"Data ultimo aggiornamento\s*(\d{2}/\d{2}/20\d{2})",txt,re.I)
    upd=""
    if m:
     d,mo,y=m.group(1).split("/");upd=f"{y}-{mo}-{d}"
    datasets.append({"title":title,"url":u,"latest_update":upd,"files":files[:5]})
  except:pass
  if len(datasets)>=12:break
 if not datasets:raise RuntimeError("Ministero Salute: nessun dataset scaricabile validato")
 latest=max((d.get("latest_update","") for d in datasets if d.get("latest_update")),default="")
 snap={"source":"Ministero della Salute","source_family":"Ministero della Salute - Open Data",
 "dataset_count":len(datasets),"datasets":datasets,"latest_update":latest,"checked_at":datetime.now(timezone.utc).isoformat(),"status":"feed"}
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
