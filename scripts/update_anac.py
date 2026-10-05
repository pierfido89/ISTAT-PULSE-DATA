#!/usr/bin/env python3
from __future__ import annotations
import hashlib,json,re,urllib.parse,urllib.request
from datetime import datetime,timezone
from pathlib import Path
from bs4 import BeautifulSoup
OUT=Path("data/anac_latest.json");CAT=Path("data/sources_catalog.json")
UA="ISTAT-PULSE/ANAC (+https://github.com/pierfido89/ISTAT-PULSE-DATA)"
HOME="https://pubblicitalegale.anticorruzione.it/"
SECTIONS=["https://pubblicitalegale.anticorruzione.it/bandi","https://pubblicitalegale.anticorruzione.it/esiti"]
def get(u):
 req=urllib.request.Request(u,headers={"User-Agent":UA,"Accept":"text/html,*/*","Accept-Language":"it-IT,it;q=0.9"})
 with urllib.request.urlopen(req,timeout=120) as r:return r.read(),r.geturl(),r.headers.get("Content-Type","")
def main():
 publications=[];latest=""
 for page in [HOME]+SECTIONS:
  try:b,u,ct=get(page)
  except Exception:continue
  s=BeautifulSoup(b.decode("utf-8","ignore"),"html.parser");text=" ".join(s.stripped_strings)
  for d,m,y in re.findall(r"(\d{2})/(\d{2})/(20\d{2})",text):
   iso=f"{y}-{m}-{d}"
   if iso>latest:latest=iso
  for a in s.find_all("a",href=True):
   h=urllib.parse.urljoin(u,a["href"]);lab=" ".join(a.stripped_strings)
   if "/bandi/" in h or "/esiti/" in h or "/avvisi/" in h:
    if h.rstrip("/") not in [x["url"].rstrip("/") for x in publications]:
     publications.append({"title":lab[:220],"url":h})
 if not latest and not publications:raise RuntimeError("ANAC Pubblicita Legale unavailable")
 snap={"source":"ANAC","source_family":"ANAC - Pubblicità legale BDNCP",
   "latest_publication_date":latest,"publication_count":len(publications),"publications":publications[:40],
   "portal_url":HOME,"checked_at":datetime.now(timezone.utc).isoformat(),"status":"feed"}
 OUT.write_text(json.dumps(snap,ensure_ascii=False,indent=2)+"\n")
 root=json.loads(CAT.read_text()) if CAT.exists() else {"sources":[]};name="ANAC - Pubblicità legale BDNCP"
 src=next((x for x in root["sources"] if x.get("name")==name),None)
 if src is None:src={};root["sources"].append(src)
 src.update({"name":name,"category":"CONTRATTI_PUBBLICI_IT","topics":["APPALTI","BANDI","ESITI","BDNCP"],
   "official":True,"url":HOME,"access_cost":"free","integration_status":"feed",
   "feed_status":"Attiva · Piattaforma di Pubblicità a Valore Legale ANAC/BDNCP",
   "frequency":"Giornaliera","latest_period":latest,"checked_at":snap["checked_at"]})
 CAT.write_text(json.dumps(root,ensure_ascii=False,indent=2)+"\n")
 print(json.dumps({"latest":latest,"publications":len(publications)},ensure_ascii=False))
if __name__=="__main__":main()
