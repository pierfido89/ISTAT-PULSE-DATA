#!/usr/bin/env python3
from __future__ import annotations
import hashlib,json,re,urllib.parse,urllib.request
from datetime import datetime,timezone
from pathlib import Path
from bs4 import BeautifulSoup

OUT=Path("data/aci_latest.json");CAT=Path("data/sources_catalog.json")
UA="ISTAT-PULSE/ACI (+https://github.com/pierfido89/ISTAT-PULSE-DATA)"
PAGE="https://aci.gov.it/attivita-e-progetti/studi-e-ricerche/autoritratto/"

def get(u,probe=False):
 h={"User-Agent":UA,"Accept":"*/*","Accept-Language":"it-IT,it;q=0.9"}
 if probe:h["Range"]="bytes=0-131071"
 req=urllib.request.Request(u,headers=h)
 with urllib.request.urlopen(req,timeout=180) as r:
  b=r.read(131072 if probe else -1);return b,r.geturl(),r.headers.get("Content-Type","")

def main():
 raw,final,_=get(PAGE);s=BeautifulSoup(raw.decode("utf-8","ignore"),"html.parser");text=" ".join(s.stripped_strings)
 upd=""
 m=re.search(r"Pagina aggiornata il\s+(\d{1,2})\s+([A-Za-zÀ-ÿ]+)\s+(20\d{2})",text,re.I)
 months={"gennaio":1,"febbraio":2,"marzo":3,"aprile":4,"maggio":5,"giugno":6,"luglio":7,"agosto":8,"settembre":9,"ottobre":10,"novembre":11,"dicembre":12}
 if m and m.group(2).lower() in months:upd=f"{m.group(3)}-{months[m.group(2).lower()]:02d}-{int(m.group(1)):02d}"
 files=[]
 seen=set()
 for a in s.find_all("a",href=True):
  lab=" ".join(a.stripped_strings);row=" ".join(a.parent.parent.stripped_strings) if a.parent and a.parent.parent else lab
  h=urllib.parse.urljoin(final,a["href"]);low=(row+" "+h).lower()
  if not any(k in low for k in ("consistenza parco","prime iscrizioni","passaggi di proprietà","radiazioni")):continue
  if h in seen:continue
  try:
   b,u,ct=get(h,True)
   if len(b)>50 and "text/html" not in ct.lower():
    seen.add(h);files.append({"title":row[:180],"url":u,"content_type":ct,"probe_bytes":len(b),"sha256":hashlib.sha256(b).hexdigest()})
  except Exception:pass
  if len(files)>=8:break
 if len(files)<4:raise RuntimeError("ACI Autoritratto: insufficient downloadable resources")
 snap={"source":"ACI","source_family":"ACI - Autoritratto / Open Data mobilità","latest_update":upd,
       "validated_resource_count":len(files),"resources":files,"opv_url":"https://opv.aci.it/",
       "checked_at":datetime.now(timezone.utc).isoformat(),"status":"feed"}
 OUT.write_text(json.dumps(snap,ensure_ascii=False,indent=2)+"\n")
 root=json.loads(CAT.read_text()) if CAT.exists() else {"sources":[]};name="ACI - Open Data mobilità"
 src=next((x for x in root["sources"] if x.get("name")==name),None)
 if src is None:src={};root["sources"].append(src)
 src.update({"name":name,"category":"MOBILITA_AUTO_IT","topics":["PARCO_VEICOLARE","PRIME_ISCRIZIONI","PASSAGGI_PROPRIETA","RADIAZIONI"],
   "official":True,"url":PAGE,"access_cost":"free","integration_status":"feed",
   "feed_status":"Attiva · allegati Autoritratto ZIP/XLS validati; OPV disponibile come consultazione",
   "frequency":"Annuale","latest_period":upd,"checked_at":snap["checked_at"]})
 CAT.write_text(json.dumps(root,ensure_ascii=False,indent=2)+"\n")
 print(json.dumps({"resources":len(files),"latest":upd},ensure_ascii=False))
if __name__=="__main__":main()
