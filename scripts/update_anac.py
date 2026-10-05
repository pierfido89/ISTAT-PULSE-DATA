#!/usr/bin/env python3
from __future__ import annotations
import json,re,urllib.parse,urllib.request,hashlib
from datetime import datetime,timezone
from pathlib import Path
from bs4 import BeautifulSoup
OUT=Path("data/anac_latest.json");CAT=Path("data/sources_catalog.json")
UA="ISTAT-PULSE/ANAC (+https://github.com/pierfido89/ISTAT-PULSE-DATA)"
PORTAL="https://www.anticorruzione.it/-/portale-dei-dati-aperti-dell-autorit%C3%A0-nazionale-anticorruzione"
def get(u):
 r=urllib.request.Request(u,headers={"User-Agent":UA,"Accept":"*/*"})
 with urllib.request.urlopen(r,timeout=120) as x:return x.read(),x.geturl(),x.headers.get("Content-Type","")
def main():
 raw,final,ct=get(PORTAL); soup=BeautifulSoup(raw.decode("utf-8","ignore"),"html.parser")
 cand=[]
 for a in soup.find_all("a",href=True):
  href=urllib.parse.urljoin(final,a["href"]); t=" ".join(a.stripped_strings)
  if any(k in (t+" "+href).lower() for k in (".csv",".json","dataset","open data")):cand.append({"title":t[:180],"url":href})
 val=[]
 for x in cand[:30]:
  try:
   b,u,c=get(x["url"])
   if len(b)>100:val.append({**x,"url":u,"bytes":len(b),"content_type":c,"sha256":hashlib.sha256(b[:131072]).hexdigest()})
  except:pass
  if len(val)>=8:break
 if not val:raise RuntimeError("ANAC: nessuna risorsa open data validata")
 snap={"source":"ANAC","source_family":"ANAC - BDNCP Open Data","validated_resource_count":len(val),
 "resources":val,"checked_at":datetime.now(timezone.utc).isoformat(),"status":"feed"}
 OUT.write_text(json.dumps(snap,ensure_ascii=False,indent=2)+"\n")
 root=json.loads(CAT.read_text()) if CAT.exists() else {"sources":[]};name="ANAC - BDNCP Open Data"
 src=next((x for x in root["sources"] if x.get("name")==name),None)
 if src is None:src={};root["sources"].append(src)
 src.update({"name":name,"category":"CONTRATTI_PUBBLICI_IT","topics":["APPALTI","CONTRATTI_PUBBLICI","AGGIUDICAZIONI"],
 "official":True,"url":PORTAL,"access_cost":"free","integration_status":"feed",
 "feed_status":"Attiva · dataset BDNCP CSV/JSON monitorati automaticamente","frequency":"Mensile",
 "level":"Nazionale, stazione appaltante e procedura","checked_at":snap["checked_at"]})
 CAT.write_text(json.dumps(root,ensure_ascii=False,indent=2)+"\n")
 print(json.dumps({"validated":len(val)},ensure_ascii=False))
if __name__=="__main__":main()
