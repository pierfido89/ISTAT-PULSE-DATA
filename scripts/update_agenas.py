#!/usr/bin/env python3
from __future__ import annotations
import hashlib,json,re,urllib.parse,urllib.request
from datetime import datetime,timezone
from pathlib import Path
from bs4 import BeautifulSoup

OUT=Path("data/agenas_latest.json");CAT=Path("data/sources_catalog.json")
UA="ISTAT-PULSE/AGENAS (+https://github.com/pierfido89/ISTAT-PULSE-DATA)"
PAGES=[
 "https://www.agenas.gov.it/?id=96&view=category",
 "https://www.agenas.gov.it/i-quaderni-di-monitor-%E2%80%93-supplementi-alla-rivista/2743-la-mobilit%C3%A0-sanitaria-in-italia-edizione-2025"
]

def get(u,probe=False):
 h={"User-Agent":UA,"Accept":"*/*","Accept-Language":"it-IT,it;q=0.9"}
 if probe:h["Range"]="bytes=0-131071"
 req=urllib.request.Request(u,headers=h)
 with urllib.request.urlopen(req,timeout=180) as r:
  b=r.read(131072 if probe else -1);return b,r.geturl(),r.headers.get("Content-Type","")

def main():
 resources=[];seen=set()
 for page in PAGES:
  try:b,u,_=get(page);s=BeautifulSoup(b.decode("utf-8","ignore"),"html.parser")
  except Exception:continue
  for a in s.find_all("a",href=True):
   h=urllib.parse.urljoin(u,a["href"]);lab=" ".join(a.stripped_strings)
   parent=" ".join(a.parent.stripped_strings) if a.parent else lab
   ctx=(parent+" "+lab+" "+h).lower()
   if h in seen:continue
   if not any(k in ctx for k in ("pne 2025","programma nazionale esiti","mobilità sanitaria","edizione 2025","report 2025")):continue
   if not any(x in ctx for x in (".pdf","download","scarica","document")):continue
   try:
    rb,ru,ct=get(h,True)
    if len(rb)>50 and ("pdf" in ct.lower() or ".pdf" in ru.lower()):
     seen.add(h);resources.append({"title":lab[:220],"url":ru,"content_type":ct,"probe_bytes":len(rb),"sha256":hashlib.sha256(rb).hexdigest()})
   except Exception:pass
   if len(resources)>=6:break
  if len(resources)>=6:break
 if not resources:raise RuntimeError("AGENAS: no official statistical report validated")
 snap={"source":"AGENAS","source_family":"AGENAS - PNE e rapporti statistici",
       "validated_resource_count":len(resources),"resources":resources,
       "pne_url":"https://pne.agenas.it/","checked_at":datetime.now(timezone.utc).isoformat(),"status":"feed"}
 OUT.write_text(json.dumps(snap,ensure_ascii=False,indent=2)+"\n")
 root=json.loads(CAT.read_text()) if CAT.exists() else {"sources":[]};name="AGENAS - PNE e rapporti statistici"
 src=next((x for x in root["sources"] if x.get("name")==name),None)
 if src is None:src={};root["sources"].append(src)
 src.update({"name":name,"category":"SANITA_SSR_IT","topics":["PNE","MOBILITA_SANITARIA","PERFORMANCE","ESITI"],
   "official":True,"url":"https://www.agenas.gov.it/","access_cost":"free","integration_status":"feed",
   "feed_status":"Attiva · rapporti statistici ufficiali AGENAS/PNE validati; dashboard PNE consultabile separatamente",
   "frequency":"Annuale e secondo pubblicazione","checked_at":snap["checked_at"]})
 CAT.write_text(json.dumps(root,ensure_ascii=False,indent=2)+"\n")
 print(json.dumps({"resources":len(resources)},ensure_ascii=False))
if __name__=="__main__":main()
