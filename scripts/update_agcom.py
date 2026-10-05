#!/usr/bin/env python3
from __future__ import annotations
import hashlib,json,re,urllib.parse,urllib.request
from datetime import datetime,timezone
from pathlib import Path
from bs4 import BeautifulSoup

OUT=Path("data/agcom_latest.json"); CAT=Path("data/sources_catalog.json")
UA="ISTAT-PULSE/AGCOM (+https://github.com/pierfido89/ISTAT-PULSE-DATA)"
LIST="https://www.agcom.it/pubblicazioni/osservatori"

def get(url,probe=False):
    h={"User-Agent":UA,"Accept":"*/*","Accept-Language":"it-IT,it;q=0.9"}
    if probe:h["Range"]="bytes=0-131071"
    req=urllib.request.Request(url,headers=h)
    with urllib.request.urlopen(req,timeout=180) as r:
        raw=r.read(131072 if probe else -1)
        return raw,r.geturl(),r.headers.get("Content-Type","")

def iso(text):
    m=re.search(r"(\d{1,2})/(\d{1,2})/(20\d{2})",text)
    if not m:return ""
    return f"{m.group(3)}-{int(m.group(2)):02d}-{int(m.group(1)):02d}"

def main():
    raw,final,_=get(LIST)
    soup=BeautifulSoup(raw.decode("utf-8","ignore"),"html.parser")
    pages=[]
    for a in soup.find_all("a",href=True):
        title=" ".join(a.stripped_strings)
        href=urllib.parse.urljoin(final,a["href"])
        m=re.search(r"Osservatorio sulle comunicazioni n\.\s*(\d+)\s*/\s*(20\d{2})",title,re.I)
        if m:
            pages.append({"title":title,"url":href,"issue":int(m.group(1)),"year":int(m.group(2))})
    if not pages:raise RuntimeError("AGCOM: osservatori non trovati")
    pages.sort(key=lambda x:(x["year"],x["issue"]),reverse=True)
    latest=pages[0]
    b,u,_=get(latest["url"]); ps=BeautifulSoup(b.decode("utf-8","ignore"),"html.parser")
    text=" ".join(ps.stripped_strings)
    pub=iso(text)
    open_data=[]
    for a in ps.find_all("a",href=True):
        title=" ".join(a.stripped_strings)
        href=urllib.parse.urljoin(u,a["href"])
        low=(title+" "+href).lower()
        if "open data" in low or ".xlsx" in low or ".xls" in low:
            try:
                rb,ru,ct=get(href,True)
                if len(rb)>50 and ("sheet" in ct.lower() or "excel" in ct.lower() or ".xls" in ru.lower()):
                    open_data.append({"title":title,"url":ru,"content_type":ct,"probe_bytes":len(rb),
                      "probe_sha256":hashlib.sha256(rb).hexdigest()})
            except Exception:pass
    if not open_data:raise RuntimeError("AGCOM: allegato OPEN DATA non validato")
    snap={"source":"AGCOM","source_family":"AGCOM - Osservatorio sulle comunicazioni",
      "issue":latest["issue"],"year":latest["year"],"publication_date":pub,
      "release_title":latest["title"],"release_url":u,"open_data":open_data,
      "checked_at":datetime.now(timezone.utc).isoformat(),"status":"feed"}
    OUT.write_text(json.dumps(snap,ensure_ascii=False,indent=2)+"\n")
    root=json.loads(CAT.read_text()) if CAT.exists() else {"sources":[]}
    name="AGCOM - Osservatorio sulle comunicazioni"
    src=next((x for x in root["sources"] if x.get("name")==name),None)
    if src is None:src={};root["sources"].append(src)
    src.update({"name":name,"category":"COMUNICAZIONI_MEDIA_IT",
      "topics":["TELECOMUNICAZIONI","INTERNET","MEDIA","POSTE"],
      "official":True,"url":LIST,"access_cost":"free","integration_status":"feed",
      "feed_status":"Attiva · allegati OPEN DATA AGCOM XLSX validati","frequency":"Trimestrale",
      "latest_period":f'{latest["year"]}-Q{latest["issue"]}',"publication_date":pub,"checked_at":snap["checked_at"]})
    CAT.write_text(json.dumps(root,ensure_ascii=False,indent=2)+"\n")
    print(json.dumps({"issue":latest["issue"],"year":latest["year"],"open_data":len(open_data)},ensure_ascii=False))
if __name__=="__main__":main()
