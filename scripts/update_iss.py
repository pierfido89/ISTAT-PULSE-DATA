#!/usr/bin/env python3
import json,hashlib,urllib.parse,urllib.request
from datetime import datetime,timezone
from pathlib import Path
from bs4 import BeautifulSoup
OUT=Path("data/iss_latest.json");CAT=Path("data/sources_catalog.json");UA="ISTAT-PULSE/ISS";HOME="https://www.iss.it/dati"
def get(u,probe=False):
 h={"User-Agent":UA,"Accept":"*/*"}; 
 if probe:h["Range"]="bytes=0-131071"
 r=urllib.request.Request(u,headers=h)
 with urllib.request.urlopen(r,timeout=180) as x:
  b=x.read(131072 if probe else -1);return b,x.geturl(),x.headers.get("Content-Type","")
def main():
 raw,final,_=get(HOME);s=BeautifulSoup(raw.decode("utf-8","ignore"),"html.parser")
 pages=[]
 for a in s.find_all("a",href=True):
  h=urllib.parse.urljoin(final,a["href"]); t=" ".join(a.stripped_strings)
  if ("open data" in t.lower() or "/dati/" in h.lower()) and h!=final: pages.append({"title":t,"url":h})
 data=[]
 for p in pages[:40]:
  try:b,u,_=get(p["url"]);ps=BeautifulSoup(b.decode("utf-8","ignore"),"html.parser")
  except:continue
  files=[]
  for a in ps.find_all("a",href=True):
   h=urllib.parse.urljoin(u,a["href"]);lab=" ".join(a.stripped_strings);low=(lab+" "+h).lower()
   if not any(x in low for x in (".csv",".xlsx",".zip","download","scarica")):continue
   try:
    rb,ru,ct=get(h,True)
    if len(rb)>50 and "text/html" not in ct.lower():
     files.append({"title":lab,"url":ru,"content_type":ct,"probe_bytes":len(rb),"sha256":hashlib.sha256(rb).hexdigest()})
   except:pass
  if files:data.append({"title":p["title"],"url":u,"files":files[:3]})
  if len(data)>=8:break
 if not data:raise RuntimeError("ISS: no downloadable open datasets")
 snap={"source":"Istituto Superiore di Sanità","source_family":"ISS Open Data","dataset_count":len(data),"datasets":data,"checked_at":datetime.now(timezone.utc).isoformat(),"status":"feed"}
 OUT.write_text(json.dumps(snap,ensure_ascii=False,indent=2)+"\n")
 root=json.loads(CAT.read_text()) if CAT.exists() else {"sources":[]};name="Istituto Superiore di Sanità - Open Data"
 src=next((x for x in root["sources"] if x.get("name")==name),None)
 if src is None:src={};root["sources"].append(src)
 src.update({"name":name,"category":"SALUTE_RICERCA_IT","topics":["SORVEGLIANZA","REGISTRI","EPIDEMIOLOGIA"],"official":True,"url":HOME,"access_cost":"free","integration_status":"feed","feed_status":"Attiva · dataset ISS scaricabili validati","frequency":"Secondo dataset","checked_at":snap["checked_at"]})
 CAT.write_text(json.dumps(root,ensure_ascii=False,indent=2)+"\n")
if __name__=="__main__":main()
