#!/usr/bin/env python3
from __future__ import annotations
import hashlib,json,re,urllib.parse,urllib.request
from datetime import datetime,timezone
from pathlib import Path
from bs4 import BeautifulSoup

OUT=Path("data/invalsi_latest.json");CAT=Path("data/sources_catalog.json")
UA="ISTAT-PULSE/INVALSI (+https://github.com/pierfido89/ISTAT-PULSE-DATA)"

def get(url,probe=False):
 h={"User-Agent":UA,"Accept":"*/*","Accept-Language":"it-IT,it;q=0.9"}
 if probe:h["Range"]="bytes=0-131071"
 req=urllib.request.Request(url,headers=h)
 with urllib.request.urlopen(req,timeout=120) as r:
  b=r.read(131072 if probe else -1);return b,r.geturl(),r.headers.get("Content-Type","")

def main():
 current=datetime.now(timezone.utc).year
 # 2026 results are not published yet; explicit fallback to latest official edition.
 years=[current] if current<=2025 else [2025,2024]
 chosen=None
 for year in years:
  urls=[
   f"https://www.invalsiopen.it/risultati/risultati-prove-invalsi-{year}/",
   f"https://invalsiopen.it/risultati/risultati-prove-invalsi-{year}/",
   f"https://ftp.invalsiopen.it/risultati/risultati-prove-invalsi-{year}/"
  ]
  for url in urls:
   try:
    b,u,_=get(url);s=BeautifulSoup(b.decode("utf-8","ignore"),"html.parser");txt=" ".join(s.stripped_strings)
    if len(txt)>500:
     chosen=(year,u,s,txt);break
   except Exception:pass
  if chosen:break
 if not chosen:raise RuntimeError("INVALSI: no annual results page")
 year,u,s,text=chosen
 metrics={}
 m=re.search(r"(?:più di|oltre)\s+([\d\.,]+)\s+milioni di",text,re.I)
 if m:metrics["students_millions"]=float(m.group(1).replace(".","").replace(",","."))
 m=re.search(r"circa\s+([\d\.]+)\s+istituti scolastici",text,re.I)
 if m:metrics["schools_approx"]=int(m.group(1).replace(".",""))
 docs=[]
 for a in s.find_all("a",href=True):
  h=urllib.request.urljoin(u,a["href"]) if False else a["href"]
  if not h.startswith("http"): h=urllib.parse.urljoin(u,h)
  lab=" ".join(a.stripped_strings);low=(lab+" "+h).lower()
  if "rapporto" not in low and ".pdf" not in low:continue
  try:
   rb,ru,ct=get(h,True)
   if len(rb)>50 and ("pdf" in ct.lower() or ".pdf" in ru.lower()):
    docs.append({"title":lab[:180],"url":ru,"content_type":ct,"probe_bytes":len(rb),"sha256":hashlib.sha256(rb).hexdigest()})
  except Exception:pass
 if not metrics and not docs:raise RuntimeError("INVALSI: no metrics or official report")
 snap={"source":"INVALSI","source_family":"INVALSI - Risultati rilevazioni nazionali","year":year,"release_url":u,
       "metrics":metrics,"attachments":docs[:5],"checked_at":datetime.now(timezone.utc).isoformat(),"status":"feed"}
 OUT.write_text(json.dumps(snap,ensure_ascii=False,indent=2)+"\n")
 root=json.loads(CAT.read_text()) if CAT.exists() else {"sources":[]};name="INVALSI - Risultati rilevazioni nazionali"
 src=next((x for x in root["sources"] if x.get("name")==name),None)
 if src is None:src={};root["sources"].append(src)
 src.update({"name":name,"category":"ISTRUZIONE_VALUTAZIONE_IT","topics":["INVALSI","APPRENDIMENTI","ITALIANO","MATEMATICA","INGLESE"],
   "official":True,"url":u,"access_cost":"free","integration_status":"feed","feed_status":"Attiva · risultati annuali INVALSI monitorati",
   "frequency":"Annuale","latest_period":str(year),"checked_at":snap["checked_at"]})
 CAT.write_text(json.dumps(root,ensure_ascii=False,indent=2)+"\n")
 print(json.dumps({"year":year,"metrics":metrics,"attachments":len(docs)},ensure_ascii=False))
if __name__=="__main__":main()
