#!/usr/bin/env python3
import json,hashlib,urllib.parse,urllib.request
from datetime import datetime,timezone
from pathlib import Path
from bs4 import BeautifulSoup
OUT=Path("data/aci_latest.json");CAT=Path("data/sources_catalog.json");UA="ISTAT-PULSE/ACI";HOME="https://opv.aci.it/WEBDMCircolante/noteOPV.html"
def get(u,probe=False):
 h={"User-Agent":UA,"Accept":"*/*"}; 
 if probe:h["Range"]="bytes=0-131071"
 r=urllib.request.Request(u,headers=h)
 with urllib.request.urlopen(r,timeout=180) as x:
  b=x.read(131072 if probe else -1);return b,x.geturl(),x.headers.get("Content-Type","")
def main():
 raw,final,_=get(HOME);s=BeautifulSoup(raw.decode("utf-8","ignore"),"html.parser")
 links=[]
 for a in s.find_all("a",href=True):
  h=urllib.parse.urljoin(final,a["href"]);t=" ".join(a.stripped_strings);low=(t+" "+h).lower()
  if any(x in low for x in ("csv","xlsx","xls","download","scarica","autoritratto","annuario","auto trend")):links.append({"title":t,"url":h})
 files=[]
 for p in links[:80]:
  try:b,u,ct=get(p["url"],True)
  except:continue
  if len(b)>50 and "text/html" not in ct.lower():
   files.append({"title":p["title"],"url":u,"content_type":ct,"probe_bytes":len(b),"sha256":hashlib.sha256(b).hexdigest()})
 if not files:
  # Accept the OPV interactive source as connected only if downloadable assets are not exposed in static markup.
  raise RuntimeError("ACI: downloadable open-data asset not exposed in static page")
 snap={"source":"ACI","source_family":"ACI - Open Parco Veicoli","validated_resource_count":len(files),"resources":files,"checked_at":datetime.now(timezone.utc).isoformat(),"status":"feed"}
 OUT.write_text(json.dumps(snap,ensure_ascii=False,indent=2)+"\n")
 root=json.loads(CAT.read_text()) if CAT.exists() else {"sources":[]};name="ACI - Open Data mobilità"
 src=next((x for x in root["sources"] if x.get("name")==name),None)
 if src is None:src={};root["sources"].append(src)
 src.update({"name":name,"category":"MOBILITA_AUTO_IT","topics":["PARCO_VEICOLARE","PRA","RADIAZIONI","PASSAGGI_PROPRIETA"],"official":True,"url":HOME,"access_cost":"free","integration_status":"feed","feed_status":"Attiva · risorse ACI Open Data validate","frequency":"Annuale e mensile secondo fonte","checked_at":snap["checked_at"]})
 CAT.write_text(json.dumps(root,ensure_ascii=False,indent=2)+"\n")
if __name__=="__main__":main()
