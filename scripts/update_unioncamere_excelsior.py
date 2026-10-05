#!/usr/bin/env python3
from __future__ import annotations
import hashlib,json,re,urllib.parse,urllib.request
from datetime import datetime,timezone
from pathlib import Path
from bs4 import BeautifulSoup
OUT=Path("data/unioncamere_excelsior_latest.json");CATALOG=Path("data/sources_catalog.json")
UA="ISTAT-PULSE/Excelsior (+https://github.com/pierfido89/ISTAT-PULSE-DATA)"
HOME="https://excelsior.unioncamere.net/"
MONTHS={"gennaio":1,"febbraio":2,"marzo":3,"aprile":4,"maggio":5,"giugno":6,"luglio":7,"agosto":8,"settembre":9,"ottobre":10,"novembre":11,"dicembre":12}
def get(u,timeout=120):
 req=urllib.request.Request(u,headers={"User-Agent":UA,"Accept":"*/*","Accept-Language":"it-IT,it;q=0.9"})
 with urllib.request.urlopen(req,timeout=timeout) as r:return r.read(),r.geturl(),r.headers.get("Content-Type","")
def clean(x):return re.sub(r"\s+"," ",str(x or "")).strip()
def month_from_text(t):
 for m,n in MONTHS.items():
  if re.search(rf"\b{m}\b",t,re.I):return n
 return None
def publication_date_from_context(t):
 m=re.search(r"(\d{1,2})[/-](\d{1,2})[/-](20\d{2})",t)
 if m:return f"{int(m.group(3)):04d}-{int(m.group(2)):02d}-{int(m.group(1)):02d}"
 m=re.search(r"(\d{1,2})\s+([A-Za-zÀ-ÿ]+)\s+(20\d{2})",t,re.I)
 if m and m.group(2).lower() in MONTHS:return f"{int(m.group(3)):04d}-{MONTHS[m.group(2).lower()]:02d}-{int(m.group(1)):02d}"
 return ""
def main():
 raw,final,_=get(HOME);soup=BeautifulSoup(raw.decode("utf-8","ignore"),"html.parser");candidates=[]
 for a in soup.find_all("a",href=True):
  title=clean(a.get_text(" ",strip=True));href=urllib.parse.urljoin(final,a["href"])
  if "/notizie/" not in href:continue
  mo=month_from_text(title)
  if not mo:continue
  ctx=clean(a.parent.get_text(" ",strip=True) if a.parent else title)
  if a.parent and a.parent.parent:ctx+=" "+clean(a.parent.parent.get_text(" ",strip=True))
  pd=publication_date_from_context(ctx)
  year=int(pd[:4]) if pd else None
  if year is None:
   years=[int(y) for y in re.findall(r"20\d{2}",title)]
   year=max(years) if years else None
  if year:candidates.append({"title":title[:300],"url":href,"period":f"{year:04d}-{mo:02d}","publication_date":pd})
 if not candidates:raise RuntimeError("Excelsior: no dated monthly releases")
 candidates.sort(key=lambda x:(x["period"],x["publication_date"]),reverse=True);latest=candidates[0]
 page_raw,page_final,_=get(latest["url"]);psoup=BeautifulSoup(page_raw.decode("utf-8","ignore"),"html.parser");text=clean(psoup.get_text(" ",strip=True))
 links=[];seen=set()
 for a in psoup.find_all("a",href=True):
  href=urllib.parse.urljoin(page_final,a["href"]);title=clean(a.get_text(" ",strip=True));low=(title+" "+href).lower()
  if any(k in low for k in (".pdf",".xlsx",".xls",".csv","bollettino","tavol","comunicato")) and href not in seen:
   seen.add(href);links.append({"title":title[:200],"url":href})
 validated=[]
 for item in links[:30]:
  try:
   b,u,ct=get(item["url"])
   if len(b)>500:validated.append({**item,"url":u,"content_type":ct,"bytes":len(b),"sha256":hashlib.sha256(b).hexdigest()})
  except:pass
 if not validated:raise RuntimeError("Excelsior: no official attachments")
 ent=None;m=re.search(r"(\d{3})\s*mila\s+(?:entrate|contratti)",text,re.I)
 if m:ent=int(m.group(1))*1000
 mm=None;m=re.search(r"(?:difficil[^%]{0,120}|mismatch[^%]{0,120})(\d{1,2}[,.]\d)%",text,re.I)
 if m:mm=float(m.group(1).replace(",","."))
 snap={"source":"Unioncamere - Excelsior","source_family":"Unioncamere - Excelsior","period":latest["period"],
 "publication_date":latest["publication_date"],"release_title":latest["title"],"release_url":page_final,
 "entrate_programmate":ent,"mismatch_percent":mm,"validated_attachment_count":len(validated),"attachments":validated,
 "checked_at":datetime.now(timezone.utc).isoformat(),"status":"feed"}
 OUT.write_text(json.dumps(snap,ensure_ascii=False,indent=2)+"\n")
 root=json.loads(CATALOG.read_text()) if CATALOG.exists() else {"sources":[]};name="Unioncamere - Excelsior"
 src=next((x for x in root["sources"] if x.get("name")==name),None)
 if src is None:src={};root["sources"].append(src)
 src.update({"name":name,"category":"LAVORO_IT","topics":["LAVORO","PROFESSIONI","FABBISOGNI_OCCUPAZIONALI","MISMATCH"],
 "official":True,"url":HOME,"access_cost":"free","integration_status":"feed",
 "feed_status":"Attiva · ultimo bollettino mensile e allegati validati","frequency":"Mensile",
 "latest_period":latest["period"],"publication_date":latest["publication_date"],"checked_at":snap["checked_at"]})
 CATALOG.write_text(json.dumps(root,ensure_ascii=False,indent=2)+"\n")
 print(json.dumps({"period":latest["period"],"attachments":len(validated),"entrate":ent},ensure_ascii=False))
if __name__=="__main__":main()
