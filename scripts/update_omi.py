#!/usr/bin/env python3
from __future__ import annotations
import json,re,urllib.request,hashlib
from datetime import datetime,timezone
from pathlib import Path
from bs4 import BeautifulSoup
OUT=Path("data/omi_latest.json"); CAT=Path("data/sources_catalog.json")
UA="ISTAT-PULSE/OMI (+https://github.com/pierfido89/ISTAT-PULSE-DATA)"
QUOTES="https://www1.agenziaentrate.gov.it/servizi/geopoi_omi/index.htm"
HOME="https://agenziaentrate.gov.it/portale/web/guest/home"
def get(u):
 r=urllib.request.Request(u,headers={"User-Agent":UA,"Accept":"*/*"})
 with urllib.request.urlopen(r,timeout=120) as x:return x.read(),x.geturl(),x.headers.get("Content-Type","")
def clean(s):return re.sub(r"\s+"," ",s or "").strip()
def main():
 q,qu,qc=get(QUOTES); h,hu,hc=get(HOME)
 qtxt=clean(BeautifulSoup(q.decode("utf-8","ignore"),"html.parser").get_text(" ",strip=True))
 htxt=clean(BeautifulSoup(h.decode("utf-8","ignore"),"html.parser").get_text(" ",strip=True))
 semesters=sorted(set(re.findall(r"(20\d{2})\s*[-/]?\s*([12])",qtxt)))
 latest_sem=f"{semesters[-1][0]}-S{semesters[-1][1]}" if semesters else ""
 news=[]
 for m in re.finditer(r"Statistiche trimestrali Omi.{0,500}",htxt,re.I):
  s=m.group(0); y=re.search(r"20\d{2}",s); qtr=re.search(r"([IVX]{1,4})\s+(?:trimestre|semestre)",s,re.I)
  news.append(s[:500])
 snap={"source":"Agenzia delle Entrate - OMI","quote_service":qu,"latest_semester":latest_sem,
 "quarterly_mentions":news[:10],"checked_at":datetime.now(timezone.utc).isoformat(),
 "quote_page_sha256":hashlib.sha256(q).hexdigest(),"status":"feed"}
 OUT.write_text(json.dumps(snap,ensure_ascii=False,indent=2)+"\n")
 root=json.loads(CAT.read_text()) if CAT.exists() else {"sources":[]}
 name="Agenzia delle Entrate - OMI"
 src=next((x for x in root["sources"] if x.get("name")==name),None)
 if src is None:src={};root["sources"].append(src)
 src.update({"name":name,"category":"IMMOBILIARE_IT","topics":["IMMOBILI","PREZZI_CASE","COMPRAVENDITE"],
 "official":True,"url":QUOTES,"access_cost":"free","integration_status":"feed",
 "feed_status":"Attiva · quotazioni OMI e pubblicazioni trimestrali monitorate automaticamente",
 "notes":"Feed pubblico su quotazioni semestrali OMI e statistiche trimestrali del mercato immobiliare.",
 "level":"Nazionale, provinciale, comunale e zona OMI","frequency":"Semestrale e trimestrale",
 "latest_period":latest_sem,"checked_at":snap["checked_at"]})
 CAT.write_text(json.dumps(root,ensure_ascii=False,indent=2)+"\n")
 print(json.dumps(snap,ensure_ascii=False))
if __name__=="__main__":main()
