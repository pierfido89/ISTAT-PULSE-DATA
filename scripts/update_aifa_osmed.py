#!/usr/bin/env python3
import json,hashlib,re,time,urllib.parse,urllib.request
from datetime import datetime,timezone
from pathlib import Path
from bs4 import BeautifulSoup
OUT=Path("data/aifa_osmed_latest.json"); CAT=Path("data/sources_catalog.json")
UA="ISTAT-PULSE/AIFA-OsMed"; PAGE="https://www.aifa.gov.it/it/spesa-e-consumo-relativi-al-flusso-della-farmaceutica-convenzionata-e-degli-acquisti-diretti"
def get(u,probe=False):
 h={"User-Agent":UA,"Accept":"*/*","Accept-Language":"it-IT,it;q=0.9"}
 if probe:h["Range"]="bytes=0-131071"
 err=None
 for attempt in range(4):
  try:
   r=urllib.request.Request(u,headers=h)
   with urllib.request.urlopen(r,timeout=180) as x:
    b=x.read(131072 if probe else -1); return b,x.geturl(),x.headers.get("Content-Type","")
  except Exception as e:
   err=e; time.sleep(2*(attempt+1))
 raise err
def main():
 raw,final,_=get(PAGE); s=BeautifulSoup(raw.decode("utf-8","ignore"),"html.parser"); txt=" ".join(s.stripped_strings)
 upd=""; m=re.search(r"Data ultimo aggiornamento:\s*(\d{2})/(\d{2})/(20\d{2})",txt,re.I)
 if m: upd=f"{m.group(3)}-{m.group(2)}-{m.group(1)}"
 files=[]
 for a in s.find_all("a",href=True):
  h=urllib.parse.urljoin(final,a["href"]); lab=" ".join(a.stripped_strings); low=(lab+" "+h).lower()
  if "download - anno" not in low and ".csv" not in low: continue
  try:
   b,u,ct=get(h,True)
   if len(b)>50 and "text/html" not in ct.lower():
    yr=re.search(r"20\d{2}",lab+" "+u)
    files.append({"year":int(yr.group(1)) if yr else None,"title":lab,"url":u,"content_type":ct,"probe_bytes":len(b),"sha256":hashlib.sha256(b).hexdigest()})
  except: pass
 if len(files)<3 and OUT.exists():
  try:
   old=json.loads(OUT.read_text())
   recovered=[]
   for item in old.get("files",[]):
    u=item.get("url","")
    if not u: continue
    try:
     b,ru,ct=get(u,True)
     if len(b)>50 and "text/html" not in ct.lower():
      yr=re.search(r"dati(20\d{2})",ru,re.I)
      recovered.append({"year":int(yr.group(1)) if yr else None,"title":item.get("title","Download"),"url":ru,
       "content_type":ct,"probe_bytes":len(b),"sha256":hashlib.sha256(b).hexdigest()})
    except Exception: pass
   if len(recovered)>=3: files=recovered
  except Exception: pass
 if len(files)<3: raise RuntimeError("AIFA OsMed: insufficient CSV files")
 snap={"source":"AIFA - OsMed","source_family":"AIFA OsMed - consumi e spesa farmaci","latest_update":upd,"validated_file_count":len(files),"files":files,"checked_at":datetime.now(timezone.utc).isoformat(),"status":"feed"}
 OUT.write_text(json.dumps(snap,ensure_ascii=False,indent=2)+"\n")
 root=json.loads(CAT.read_text()) if CAT.exists() else {"sources":[]}; name="AIFA - OsMed"
 src=next((x for x in root["sources"] if x.get("name")==name),None)
 if src is None: src={};root["sources"].append(src)
 src.update({"name":name,"category":"FARMACI_IT","topics":["FARMACI","SPESA_FARMACEUTICA","CONSUMI","ATC"],"official":True,"url":PAGE,"access_cost":"free","integration_status":"feed","feed_status":"Attiva · CSV OsMed validati","frequency":"Annuale e monitoraggi periodici","latest_period":upd,"checked_at":snap["checked_at"]})
 CAT.write_text(json.dumps(root,ensure_ascii=False,indent=2)+"\n")
if __name__=="__main__":main()
