#!/usr/bin/env python3
import json,hashlib,urllib.parse,urllib.request
from datetime import datetime,timezone
from pathlib import Path
from bs4 import BeautifulSoup
OUT=Path("data/agenas_latest.json");CAT=Path("data/sources_catalog.json");UA="ISTAT-PULSE/AGENAS";HOME="https://stat.agenas.it/"
def get(u,probe=False):
 h={"User-Agent":UA,"Accept":"*/*"}; 
 if probe:h["Range"]="bytes=0-131071"
 r=urllib.request.Request(u,headers=h)
 with urllib.request.urlopen(r,timeout=180) as x:
  b=x.read(131072 if probe else -1);return b,x.geturl(),x.headers.get("Content-Type","")
def main():
 raw,final,_=get(HOME);s=BeautifulSoup(raw.decode("utf-8","ignore"),"html.parser")
 reports=[];files=[]
 for a in s.find_all("a",href=True):
  h=urllib.parse.urljoin(final,a["href"]);t=" ".join(a.stripped_strings)
  if "report=" in h: reports.append({"title":t,"url":h})
 for p in reports[:60]:
  try:b,u,_=get(p["url"]);ps=BeautifulSoup(b.decode("utf-8","ignore"),"html.parser")
  except:continue
  for a in ps.find_all("a",href=True):
   h=urllib.parse.urljoin(u,a["href"]);lab=" ".join(a.stripped_strings);low=(lab+" "+h).lower()
   if not any(x in low for x in (".csv",".xlsx",".xls",".zip","download","scarica")):continue
   try:
    rb,ru,ct=get(h,True)
    if len(rb)>50 and "text/html" not in ct.lower():
     files.append({"report":p["title"],"title":lab,"url":ru,"content_type":ct,"probe_bytes":len(rb),"sha256":hashlib.sha256(rb).hexdigest()})
   except:pass
  if len(files)>=6:break
 if not files:raise RuntimeError("AGENAS: no structured downloadable resources")
 snap={"source":"AGENAS","source_family":"AGENAS Portale Statistico","validated_resource_count":len(files),"resources":files,"checked_at":datetime.now(timezone.utc).isoformat(),"status":"feed"}
 OUT.write_text(json.dumps(snap,ensure_ascii=False,indent=2)+"\n")
 root=json.loads(CAT.read_text()) if CAT.exists() else {"sources":[]};name="AGENAS - Portale Statistico"
 src=next((x for x in root["sources"] if x.get("name")==name),None)
 if src is None:src={};root["sources"].append(src)
 src.update({"name":name,"category":"SANITA_SSR_IT","topics":["PNE","MOBILITA_SANITARIA","PERFORMANCE","TEMPI_ATTESA"],"official":True,"url":HOME,"access_cost":"free","integration_status":"feed","feed_status":"Attiva · risorse statistiche scaricabili validate","frequency":"Secondo report","checked_at":snap["checked_at"]})
 CAT.write_text(json.dumps(root,ensure_ascii=False,indent=2)+"\n")
if __name__=="__main__":main()
