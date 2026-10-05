#!/usr/bin/env python3
from __future__ import annotations
import hashlib,json,re,urllib.parse,urllib.request
from datetime import datetime,timezone
from pathlib import Path
from bs4 import BeautifulSoup

OUT=Path("data/dipfin_latest.json");CAT=Path("data/sources_catalog.json")
UA="ISTAT-PULSE/DipFin (+https://github.com/pierfido89/ISTAT-PULSE-DATA)"
HOME="https://www1.finanze.gov.it/finanze/analisi_stat/public/index.php?opendata=yes"

def get(u,probe=False):
 h={"User-Agent":UA,"Accept":"*/*","Accept-Language":"it-IT,it;q=0.9"}
 if probe:h["Range"]="bytes=0-131071"
 req=urllib.request.Request(u,headers=h)
 with urllib.request.urlopen(req,timeout=180) as r:
  b=r.read(131072 if probe else -1);return b,r.geturl(),r.headers.get("Content-Type","")

def main():
 raw,final,_=get(HOME);soup=BeautifulSoup(raw.decode("utf-8","ignore"),"html.parser")
 resources=[];pages=[];seen=set()
 for a in soup.find_all("a",href=True):
  h=urllib.parse.urljoin(final,a["href"]);t=" ".join(a.stripped_strings);low=(t+" "+h).lower()
  if any(k in low for k in ("csv","zip","xlsx","scarica","download","dichiaraz","irpef","iva","ires","imu")):
   if h not in seen:seen.add(h);pages.append({"title":t[:220],"url":h})
 for p in pages[:120]:
  try:b,u,ct=get(p["url"])
  except Exception:continue
  if "text/html" not in ct.lower():
   if len(b)>50:
    resources.append({"title":p["title"],"url":u,"content_type":ct,"probe_bytes":min(len(b),131072),"probe_sha256":hashlib.sha256(b[:131072]).hexdigest()})
  else:
   ps=BeautifulSoup(b.decode("utf-8","ignore"),"html.parser")
   for a in ps.find_all("a",href=True):
    h=urllib.parse.urljoin(u,a["href"]);lab=" ".join(a.stripped_strings);low=(lab+" "+h).lower()
    if not any(x in low for x in (".csv",".zip",".xlsx",".xls","scarica","download")):continue
    try:
     rb,ru,rct=get(h,True)
     if len(rb)>50 and "text/html" not in rct.lower():
      resources.append({"title":lab[:180] or p["title"],"url":ru,"content_type":rct,
       "probe_bytes":len(rb),"probe_sha256":hashlib.sha256(rb).hexdigest()})
    except Exception:pass
    if len(resources)>=10:break
  if len(resources)>=10:break
 if not resources:raise RuntimeError("Dipartimento Finanze: nessun open data fiscale scaricabile validato")
 snap={"source":"Dipartimento delle Finanze","source_family":"Dipartimento Finanze - Statistiche dichiarazioni",
  "validated_resource_count":len(resources),"resources":resources,
  "checked_at":datetime.now(timezone.utc).isoformat(),"status":"feed"}
 OUT.write_text(json.dumps(snap,ensure_ascii=False,indent=2)+"\n")
 root=json.loads(CAT.read_text()) if CAT.exists() else {"sources":[]};name="Dipartimento delle Finanze - Statistiche fiscali"
 src=next((x for x in root["sources"] if x.get("name")==name),None)
 if src is None:src={};root["sources"].append(src)
 src.update({"name":name,"category":"FISCO_IT","topics":["IRPEF","IVA","IRES","DICHIARAZIONI","REDDITI"],
  "official":True,"url":HOME,"access_cost":"free","integration_status":"feed",
  "feed_status":"Attiva · open data fiscali scaricabili validati","frequency":"Annuale e secondo pubblicazione","checked_at":snap["checked_at"]})
 CAT.write_text(json.dumps(root,ensure_ascii=False,indent=2)+"\n")
 print(json.dumps({"validated":len(resources)},ensure_ascii=False))
if __name__=="__main__":main()
