#!/usr/bin/env python3
from __future__ import annotations
import hashlib,json,re,urllib.parse,urllib.request
from datetime import datetime,timezone
from pathlib import Path
from bs4 import BeautifulSoup

OUT=Path("data/mim_latest.json");CAT=Path("data/sources_catalog.json")
UA="ISTAT-PULSE/MIM (+https://github.com/pierfido89/ISTAT-PULSE-DATA)"
PAGES=[
 "https://dati.istruzione.it/opendata/opendata/catalogo/elements1/?area=Scuole",
 "https://dati.istruzione.it/opendata/opendata/catalogo/elements1/leaf/?datasetId=DS0755BISCONSUNTIVO",
 "https://dati.istruzione.it/opendata/opendata/catalogo/elements1/leaf/?datasetId=DS0750BISPROGANNO"
]

def get(url,probe=False):
    h={"User-Agent":UA,"Accept":"*/*","Accept-Language":"it-IT,it;q=0.9"}
    if probe:h["Range"]="bytes=0-131071"
    req=urllib.request.Request(url,headers=h)
    with urllib.request.urlopen(req,timeout=180) as r:
        b=r.read(131072 if probe else -1);return b,r.geturl(),r.headers.get("Content-Type","")

def parse_page(url):
    raw,final,_=get(url);soup=BeautifulSoup(raw.decode("utf-8","ignore"),"html.parser")
    title=soup.find("h1").get_text(" ",strip=True) if soup.find("h1") else soup.find("h3").get_text(" ",strip=True) if soup.find("h3") else final
    files=[];latest_period=""
    text=" ".join(soup.stripped_strings)
    periods=re.findall(r"(?:ANNOSCOLASTICO|ANNOFINANZIARIO)\s+(20\d{4}|20\d{2})",text,re.I)
    if periods:latest_period=max(periods)
    for a in soup.find_all("a",href=True):
        h=urllib.parse.urljoin(final,a["href"]);lab=" ".join(a.stripped_strings);low=(lab+" "+h).lower()
        if ".csv" not in low and "scarica" not in low:continue
        try:
            rb,ru,ct=get(h,True)
            if len(rb)>50 and ("csv" in ct.lower() or ".csv" in ru.lower()) and "text/html" not in ct.lower():
                files.append({"title":lab[:180],"url":ru,"content_type":ct,"probe_bytes":len(rb),"sha256":hashlib.sha256(rb).hexdigest()})
        except Exception:pass
    if not files:raise RuntimeError(title+": no CSV")
    return {"title":title,"url":final,"latest_period":latest_period,"files":files[:4]}

def main():
    datasets=[]
    for p in PAGES:
        try:datasets.append(parse_page(p))
        except Exception:pass
    if len(datasets)<2:raise RuntimeError("MIM: fewer than 2 validated datasets")
    latest=max((d["latest_period"] for d in datasets if d["latest_period"]),default="")
    snap={"source":"Ministero dell'Istruzione e del Merito","source_family":"MIM - Open Data scuola",
          "dataset_count":len(datasets),"datasets":datasets,"latest_period":latest,
          "checked_at":datetime.now(timezone.utc).isoformat(),"status":"feed"}
    OUT.write_text(json.dumps(snap,ensure_ascii=False,indent=2)+"\n")
    root=json.loads(CAT.read_text()) if CAT.exists() else {"sources":[]};name="Ministero dell'Istruzione e del Merito - Open Data"
    src=next((x for x in root["sources"] if x.get("name")==name),None)
    if src is None:src={};root["sources"].append(src)
    src.update({"name":name,"category":"ISTRUZIONE_IT","topics":["SCUOLE","BILANCI_SCUOLE","EDILIZIA_SCOLASTICA"],
      "official":True,"url":"https://dati.istruzione.it/opendata/","access_cost":"free","integration_status":"feed",
      "feed_status":"Attiva · CSV MIM validati","frequency":"Annuale e secondo dataset","latest_period":latest,"checked_at":snap["checked_at"]})
    CAT.write_text(json.dumps(root,ensure_ascii=False,indent=2)+"\n")
    print(json.dumps({"datasets":len(datasets),"latest":latest},ensure_ascii=False))
if __name__=="__main__":main()
