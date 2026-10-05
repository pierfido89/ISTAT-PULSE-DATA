#!/usr/bin/env python3
from __future__ import annotations
import hashlib,json,re,urllib.parse,urllib.request
from datetime import datetime,timezone
from pathlib import Path
from bs4 import BeautifulSoup

OUT=Path("data/rgs_latest.json");CAT=Path("data/sources_catalog.json")
UA="ISTAT-PULSE/RGS (+https://github.com/pierfido89/ISTAT-PULSE-DATA)"
HOME="https://bdap-opendata.rgs.mef.gov.it/"

def get(u,probe=False):
 h={"User-Agent":UA,"Accept":"*/*","Accept-Language":"it-IT,it;q=0.9"}
 if probe:h["Range"]="bytes=0-131071"
 req=urllib.request.Request(u,headers=h)
 with urllib.request.urlopen(req,timeout=180) as r:
  b=r.read(131072 if probe else -1);return b,r.geturl(),r.headers.get("Content-Type","")

def main():
 raw,final,_=get(HOME);soup=BeautifulSoup(raw.decode("utf-8","ignore"),"html.parser")
 candidates=[]
 for a in soup.find_all("a",href=True):
  h=urllib.parse.urljoin(final,a["href"]);t=" ".join(a.stripped_strings);low=(t+" "+h).lower()
  if any(k in low for k in ("scarica","download","rendiconto","bilancio","spese","entrate","pubblico impiego","opere pubbliche")):
   candidates.append({"title":t[:220],"url":h})
 resources=[];seen=set()
 for c in candidates[:120]:
  if c["url"] in seen:continue
  seen.add(c["url"])
  try:b,u,ct=get(c["url"])
  except Exception:continue
  if "text/html" not in ct.lower():
   if len(b)>50:resources.append({"title":c["title"],"url":u,"content_type":ct,"bytes_sampled":min(len(b),131072),"sha256":hashlib.sha256(b[:131072]).hexdigest()})
   continue
  ps=BeautifulSoup(b.decode("utf-8","ignore"),"html.parser")
  for a in ps.find_all("a",href=True):
   h=urllib.parse.urljoin(u,a["href"]);lab=" ".join(a.stripped_strings);low=(lab+" "+h).lower()
   if not any(k in low for k in ("scarica","download",".csv",".zip",".json",".xlsx")):continue
   try:
    rb,ru,rct=get(h,True)
    if len(rb)>50 and "text/html" not in rct.lower():
     resources.append({"title":lab[:180] or c["title"],"url":ru,"content_type":rct,"bytes_sampled":len(rb),"sha256":hashlib.sha256(rb).hexdigest()})
   except Exception:pass
   if len(resources)>=10:break
  if len(resources)>=10:break
 if not resources:raise RuntimeError("RGS/BDAP: nessuna risorsa open data scaricabile validata")
 snap={"source":"Ragioneria Generale dello Stato","source_family":"RGS - BDAP Open Data","validated_resource_count":len(resources),
  "resources":resources,"checked_at":datetime.now(timezone.utc).isoformat(),"status":"feed"}
 OUT.write_text(json.dumps(snap,ensure_ascii=False,indent=2)+"\n")
 root=json.loads(CAT.read_text()) if CAT.exists() else {"sources":[]};name="Ragioneria Generale dello Stato - BDAP"
 src=next((x for x in root["sources"] if x.get("name")==name),None)
 if src is None:src={};root["sources"].append(src)
 src.update({"name":name,"category":"FINANZA_PUBBLICA_IT","topics":["BILANCIO_STATO","SPESA_PUBBLICA","ENTRATE","PUBBLICO_IMPIEGO","OPERE_PUBBLICHE"],
  "official":True,"url":HOME,"access_cost":"free","integration_status":"feed",
  "feed_status":"Attiva · BDAP Open Data scaricabili validati","frequency":"Secondo dataset","checked_at":snap["checked_at"]})
 CAT.write_text(json.dumps(root,ensure_ascii=False,indent=2)+"\n")
 print(json.dumps({"validated":len(resources)},ensure_ascii=False))
if __name__=="__main__":main()
