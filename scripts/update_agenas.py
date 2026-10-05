#!/usr/bin/env python3
from __future__ import annotations
import hashlib,json,requests
from datetime import datetime,timezone
from pathlib import Path

OUT=Path("data/agenas_latest.json");CAT=Path("data/sources_catalog.json")
UA="Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 Chrome/154 Safari/537.36"
RESOURCES=[
 {"title":"Principali risultati PNE - Edizione 2025","url":"https://www.agenas.gov.it/images/2025/9_dic_pne/RISULTATI_per_comunicato_STAMPA_09-12-2025.pdf","period":"2025","topic":"PNE"},
 {"title":"La Mobilità Sanitaria in Italia - Edizione 2025","url":"https://www.agenas.gov.it/images/Terzo_Rapporto_mobilita.pdf","period":"2025","topic":"MOBILITA_SANITARIA"}
]

def probe(u):
 r=requests.get(u,headers={"User-Agent":UA,"Accept":"application/pdf,*/*"},timeout=120,stream=True)
 r.raise_for_status()
 b=next(r.iter_content(131072),b"")
 return b,r.url,r.headers.get("Content-Type","")

def main():
 resources=[]
 for item in RESOURCES:
  try:
   b,u,ct=probe(item["url"])
   if len(b)>50 and (b.startswith(b"%PDF") or "pdf" in ct.lower()):
    resources.append({**item,"url":u,"content_type":ct,"probe_bytes":len(b),"sha256":hashlib.sha256(b).hexdigest()})
  except Exception:pass
 if len(resources)<2:raise RuntimeError("AGENAS: current PNE/mobility reports not validated")
 snap={"source":"AGENAS","source_family":"AGENAS - PNE e rapporti statistici","validated_resource_count":len(resources),
       "resources":resources,"pne_url":"https://pne.agenas.it/","checked_at":datetime.now(timezone.utc).isoformat(),"status":"feed"}
 OUT.write_text(json.dumps(snap,ensure_ascii=False,indent=2)+"\n")
 root=json.loads(CAT.read_text()) if CAT.exists() else {"sources":[]};name="AGENAS - PNE e rapporti statistici"
 src=next((x for x in root["sources"] if x.get("name")==name),None)
 if src is None:src={};root["sources"].append(src)
 src.update({"name":name,"category":"SANITA_SSR_IT","topics":["PNE","MOBILITA_SANITARIA","PERFORMANCE","ESITI"],
   "official":True,"url":"https://www.agenas.gov.it/","access_cost":"free","integration_status":"feed",
   "feed_status":"Attiva · PNE 2025 e Mobilità sanitaria 2025 validati","frequency":"Annuale e secondo pubblicazione",
   "latest_period":"2025","checked_at":snap["checked_at"]})
 CAT.write_text(json.dumps(root,ensure_ascii=False,indent=2)+"\n")
 print(json.dumps({"resources":len(resources)},ensure_ascii=False))
if __name__=="__main__":main()
