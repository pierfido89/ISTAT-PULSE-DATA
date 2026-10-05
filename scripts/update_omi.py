#!/usr/bin/env python3
from __future__ import annotations
import hashlib,json,re,urllib.request
from datetime import datetime,timezone
from pathlib import Path
from bs4 import BeautifulSoup
OUT=Path("data/omi_latest.json");CAT=Path("data/sources_catalog.json")
UA="ISTAT-PULSE/OMI (+https://github.com/pierfido89/ISTAT-PULSE-DATA)"
QUOTES="https://www1.agenziaentrate.gov.it/servizi/geopoi_omi/index.htm"
HOME="https://agenziaentrate.gov.it/portale/web/guest/home"
def get(u):
 req=urllib.request.Request(u,headers={"User-Agent":UA,"Accept":"*/*"})
 with urllib.request.urlopen(req,timeout=120) as r:return r.read(),r.geturl(),r.headers.get("Content-Type","")
def clean(s):return re.sub(r"\s+"," ",s or "").strip()
def roman_to_q(s):
 return {"I":1,"II":2,"III":3,"IV":4}.get(s.upper())
def main():
 q,qu,_=get(QUOTES);h,hu,_=get(HOME)
 htxt=clean(BeautifulSoup(h.decode("utf-8","ignore"),"html.parser").get_text(" ",strip=True))
 mentions=[];periods=[]
 for m in re.finditer(r"Statistiche trimestrali Omi.{0,700}",htxt,re.I):
  s=m.group(0);mentions.append(s[:700])
  # support "secondo trimestre del 2026" and roman forms
  y=re.search(r"(20\d{2})",s)
  qn=None
  words={"primo":1,"secondo":2,"terzo":3,"quarto":4}
  wm=re.search(r"\b(primo|secondo|terzo|quarto)\s+trimestre",s,re.I)
  if wm:qn=words[wm.group(1).lower()]
  rm=re.search(r"\b(I|II|III|IV)\s+trimestre",s,re.I)
  if not qn and rm:qn=roman_to_q(rm.group(1))
  if y and qn:periods.append(f"{y.group(1)}-Q{qn}")
 if not periods:raise RuntimeError("OMI: no quarterly statistical publication detected")
 latest=max(periods,key=lambda p:(int(p[:4]),int(p[-1])))
 snap={"source":"Agenzia delle Entrate - OMI","source_family":"Agenzia Entrate - OMI",
 "quote_service":qu,"quotes_mode":"interactive_service","quarterly_latest_period":latest,
 "quarterly_mentions":mentions[:10],"checked_at":datetime.now(timezone.utc).isoformat(),
 "quote_page_sha256":hashlib.sha256(q).hexdigest(),"status":"feed"}
 OUT.write_text(json.dumps(snap,ensure_ascii=False,indent=2)+"\n")
 root=json.loads(CAT.read_text()) if CAT.exists() else {"sources":[]};name="Agenzia delle Entrate - OMI"
 src=next((x for x in root["sources"] if x.get("name")==name),None)
 if src is None:src={};root["sources"].append(src)
 src.update({"name":name,"category":"IMMOBILIARE_IT","topics":["IMMOBILI","PREZZI_CASE","COMPRAVENDITE"],
 "official":True,"url":QUOTES,"access_cost":"free","integration_status":"feed",
 "feed_status":"Attiva · statistiche trimestrali OMI monitorate; quotazioni via servizio interattivo ufficiale",
 "notes":"Feed automatico sulle statistiche trimestrali OMI. Le quotazioni semestrali restano consultate dal servizio Geopoi e non vengono dichiarate machine-feed finché il semestre non è esposto strutturalmente.",
 "level":"Nazionale, territoriale e zone OMI","frequency":"Trimestrale; quotazioni semestrali",
 "latest_period":latest,"checked_at":snap["checked_at"]})
 CAT.write_text(json.dumps(root,ensure_ascii=False,indent=2)+"\n")
 print(json.dumps({"latest_period":latest,"mentions":len(mentions)},ensure_ascii=False))
if __name__=="__main__":main()
