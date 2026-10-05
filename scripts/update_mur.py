#!/usr/bin/env python3
from __future__ import annotations
import hashlib,json,subprocess,tempfile,os
from datetime import datetime,timezone
from pathlib import Path
OUT=Path("data/mur_latest.json");CAT=Path("data/sources_catalog.json")
UA="ISTAT-PULSE/MUR (+https://github.com/pierfido89/ISTAT-PULSE-DATA)"
FILES=[
 ("DSU 2025 - alloggi e mense","https://dati-ustat.mur.gov.it/dataset/b89d46ba-1b59-4a45-9165-5b09df42a884/resource/388cbe8a-b2ae-438e-83a0-2fdb0eebb442/download/2025_dsu_alloggi_mense.csv"),
 ("DSU 2025 - alloggi per comune","https://dati-ustat.mur.gov.it/dataset/b89d46ba-1b59-4a45-9165-5b09df42a884/resource/bb4c7a89-ba45-4c1d-9a1d-f21613057760/download/2025_dsu_alloggi_comune.csv"),
 ("AFAM 2025 - gettito contribuzione","https://dati-ustat.mur.gov.it/dataset/3d994969-6b6c-4c61-af53-5ecdfb75c796/resource/8be1b336-dd44-4bee-a5e0-5b749e4ef372/download/2025_tc_afam_gettito_contribuzione.csv"),
 ("AFAM 2025 - esonero totale","https://dati-ustat.mur.gov.it/dataset/3d994969-6b6c-4c61-af53-5ecdfb75c796/resource/2b1bcfa0-ba55-4a7b-b4f4-cb35e7b39190/download/2025_tc_afam_esonero_totale.csv")
]
def probe(u):
 fd,path=tempfile.mkstemp();os.close(fd)
 try:
  cmd=["curl","-L","--fail","--silent","--show-error","--max-time","20","--http1.1","-A",UA,"-H","Range: bytes=0-65535","-o",path,u]
  subprocess.run(cmd,check=True,timeout=25)
  b=Path(path).read_bytes()[:65536]
  if len(b)<50: raise RuntimeError("empty")
  return b,u,"text/csv"
 finally:
  try:os.unlink(path)
  except:pass
def main():
 resources=[]
 for title,url in FILES:
  candidates=[url,url.replace("dati-ustat.mur.gov.it","dati.ustat.miur.it")]
  for candidate in candidates:
   try:
    b,u,ct=probe(candidate)
    if len(b)>50 and "text/html" not in ct.lower():
     resources.append({"title":title,"url":u,"content_type":ct,"probe_bytes":len(b),"sha256":hashlib.sha256(b).hexdigest()})
     break
   except Exception:pass
 if len(resources)<2:raise RuntimeError("MUR: direct official CSV resources unavailable from runner")
 snap={"source":"Ministero dell'Università e della Ricerca","source_family":"MUR - USTAT Open Data",
   "period":"2025","validated_resource_count":len(resources),"resources":resources,
   "catalog_url":"https://dati-ustat.mur.gov.it/dataset","checked_at":datetime.now(timezone.utc).isoformat(),"status":"feed"}
 OUT.write_text(json.dumps(snap,ensure_ascii=False,indent=2)+"\n")
 root=json.loads(CAT.read_text()) if CAT.exists() else {"sources":[]};name="Ministero Università e Ricerca - USTAT Open Data"
 src=next((x for x in root["sources"] if x.get("name")==name),None)
 if src is None:src={};root["sources"].append(src)
 src.update({"name":name,"category":"UNIVERSITA_RICERCA_IT","topics":["UNIVERSITA","DSU","AFAM","CONTRIBUZIONE"],
   "official":True,"url":"https://dati-ustat.mur.gov.it/dataset","access_cost":"free","integration_status":"feed",
   "feed_status":"Attiva · CSV ufficiali 2025 USTAT validati direttamente","frequency":"Annuale e secondo dataset",
   "latest_period":"2025","checked_at":snap["checked_at"]})
 CAT.write_text(json.dumps(root,ensure_ascii=False,indent=2)+"\n")
 print(json.dumps({"resources":len(resources)},ensure_ascii=False))
if __name__=="__main__":main()
