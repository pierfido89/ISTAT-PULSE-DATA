#!/usr/bin/env python3
from __future__ import annotations
import hashlib,json,re,urllib.parse,urllib.request
from datetime import datetime,timezone
from pathlib import Path
from bs4 import BeautifulSoup

OUT=Path("data/invalsi_latest.json"); CAT=Path("data/sources_catalog.json")
UA="ISTAT-PULSE/INVALSI (+https://github.com/pierfido89/ISTAT-PULSE-DATA)"
RESULTS="https://www.invalsiopen.it/risultati/"

def get(url,probe=False):
    h={"User-Agent":UA,"Accept":"*/*","Accept-Language":"it-IT,it;q=0.9"}
    if probe:h["Range"]="bytes=0-131071"
    req=urllib.request.Request(url,headers=h)
    with urllib.request.urlopen(req,timeout=180) as r:
        b=r.read(131072 if probe else -1); return b,r.geturl(),r.headers.get("Content-Type","")

def main():
    raw,final,_=get(RESULTS); soup=BeautifulSoup(raw.decode("utf-8","ignore"),"html.parser")
    releases=[]
    for a in soup.find_all("a",href=True):
        title=" ".join(a.stripped_strings)
        m=re.search(r"Risultati delle Prove INVALSI\s+(20\d{2})",title,re.I)
        if m:
            releases.append({"year":int(m.group(1)),"title":title,"url":urllib.parse.urljoin(final,a["href"])})
    if not releases: raise RuntimeError("INVALSI: pagina risultati non trovata")
    releases.sort(key=lambda x:x["year"],reverse=True)
    latest=releases[0]
    b,u,_=get(latest["url"]); ps=BeautifulSoup(b.decode("utf-8","ignore"),"html.parser")
    text=" ".join(ps.stripped_strings)
    metrics={}
    m=re.search(r"più di\s+([\d\.,]+)\s+milioni di",text,re.I)
    if m: metrics["students_millions"]=float(m.group(1).replace(".","").replace(",","."))
    m=re.search(r"circa\s+([\d\.,]+)\s+istituti scolastici",text,re.I)
    if m: metrics["schools_approx"]=int(m.group(1).replace(".","").replace(",",""))
    attachments=[]
    for a in ps.find_all("a",href=True):
        h=urllib.parse.urljoin(u,a["href"]); lab=" ".join(a.stripped_strings); low=(lab+" "+h).lower()
        if "rapporto invalsi" in low or ".pdf" in low:
            try:
                rb,ru,ct=get(h,True)
                if len(rb)>50 and ("pdf" in ct.lower() or ".pdf" in ru.lower()):
                    attachments.append({"title":lab[:180],"url":ru,"content_type":ct,"probe_bytes":len(rb),"sha256":hashlib.sha256(rb).hexdigest()})
            except Exception: pass
    snap={"source":"INVALSI","source_family":"INVALSI - Risultati rilevazioni nazionali",
          "year":latest["year"],"release_title":latest["title"],"release_url":u,
          "metrics":metrics,"attachments":attachments[:5],
          "checked_at":datetime.now(timezone.utc).isoformat(),
          "status":"feed" if metrics or attachments else "connected"}
    if snap["status"]!="feed": raise RuntimeError("INVALSI: nessun indicatore o allegato validato")
    OUT.write_text(json.dumps(snap,ensure_ascii=False,indent=2)+"\n")
    root=json.loads(CAT.read_text()) if CAT.exists() else {"sources":[]}; name="INVALSI - Risultati rilevazioni nazionali"
    src=next((x for x in root["sources"] if x.get("name")==name),None)
    if src is None: src={}; root["sources"].append(src)
    src.update({"name":name,"category":"ISTRUZIONE_VALUTAZIONE_IT","topics":["INVALSI","APPRENDIMENTI","ITALIANO","MATEMATICA","INGLESE"],
                "official":True,"url":RESULTS,"access_cost":"free","integration_status":"feed",
                "feed_status":"Attiva · risultati pubblici e rapporti INVALSI monitorati","frequency":"Annuale",
                "latest_period":str(latest["year"]),"checked_at":snap["checked_at"]})
    CAT.write_text(json.dumps(root,ensure_ascii=False,indent=2)+"\n")
    print(json.dumps({"year":latest["year"],"metrics":metrics,"attachments":len(attachments)},ensure_ascii=False))

if __name__=="__main__": main()
