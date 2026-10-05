#!/usr/bin/env python3
from __future__ import annotations
import hashlib,json,re,urllib.parse,urllib.request
from datetime import datetime,timezone
from pathlib import Path
from bs4 import BeautifulSoup

OUT=Path("data/inail_latest.json"); CAT=Path("data/sources_catalog.json")
UA="ISTAT-PULSE/INAIL (+https://github.com/pierfido89/ISTAT-PULSE-DATA)"
PAGES={
 "diseases_monthly":"https://dati.inail.it/portale/it/dataset/malattie-professionali/dati-con-cadenza-mensile/italia.html",
 "diseases_halfyear":"https://dati.inail.it/portale/it/dataset/malattie-professionali/dati-con-cadenza-semestrale/protocollo/italia.html",
 "accidents_monthly":"https://dati.inail.it/portale/it/dataset/infortuni-sul-lavoro/dati-con-cadenza-mensile/lombardia.html",
}

def get(url,range_only=False):
    headers={"User-Agent":UA,"Accept":"*/*"}
    if range_only: headers["Range"]="bytes=0-65535"
    req=urllib.request.Request(url,headers=headers)
    with urllib.request.urlopen(req,timeout=180) as r:
        raw=r.read(65536 if range_only else -1)
        return raw,r.geturl(),r.headers.get("Content-Type","")

def parse_page(key,url):
    raw,final,ct=get(url)
    soup=BeautifulSoup(raw.decode("utf-8","ignore"),"html.parser")
    text=re.sub(r"\s+"," ",soup.get_text(" ",strip=True))
    pub=re.search(r"Data pubblicazione:\s*(\d{2}/\d{2}/20\d{2})",text,re.I)
    rilev=re.search(r"Data rilevazione:\s*(\d{2}/\d{2}/20\d{2})",text,re.I)
    csv_link=None
    for a in soup.find_all("a",href=True):
        label=" ".join(a.stripped_strings).lower()
        if "csv" in label:
            csv_link=urllib.parse.urljoin(final,a["href"]); break
    if not csv_link: raise RuntimeError(key+": CSV link missing")
    probe,purl,pct=get(csv_link,True)
    if len(probe)<50: raise RuntimeError(key+": empty CSV")
    def iso(m):
        if not m:return ""
        d,mo,y=m.group(1).split("/");return f"{y}-{mo}-{d}"
    return {"page":final,"publication_date":iso(pub),"observation_date":iso(rilev),
            "csv_url":purl,"content_type":pct,"probe_bytes":len(probe),"probe_sha256":hashlib.sha256(probe).hexdigest(),"status":"ok"}

def main():
    datasets={};failures={}
    for k,u in PAGES.items():
        try:datasets[k]=parse_page(k,u)
        except Exception as e:failures[k]=str(e)
    if len(datasets)<3: raise RuntimeError("INAIL insufficient datasets: "+json.dumps(failures))
    latest=max((x["publication_date"] for x in datasets.values()),default="")
    snap={"source":"INAIL","source_family":"INAIL - Open Data infortuni e malattie professionali",
      "datasets":datasets,"dataset_count":len(datasets),"failures":failures,"latest_publication_date":latest,
      "checked_at":datetime.now(timezone.utc).isoformat(),"status":"feed"}
    OUT.write_text(json.dumps(snap,ensure_ascii=False,indent=2)+"\n")
    root=json.loads(CAT.read_text()) if CAT.exists() else {"sources":[]};name="INAIL - Open Data infortuni e malattie professionali"
    src=next((x for x in root["sources"] if x.get("name")==name),None)
    if src is None:src={};root["sources"].append(src)
    src.update({"name":name,"category":"LAVORO_SICUREZZA_IT","topics":["INFORTUNI","MALATTIE_PROFESSIONALI","LAVORO"],
      "official":True,"url":"https://dati.inail.it/portale/it.html","access_cost":"free","integration_status":"feed",
      "feed_status":"Attiva · file CSV ufficiali INAIL validati","frequency":"Mensile e semestrale",
      "latest_period":latest,"checked_at":snap["checked_at"]})
    CAT.write_text(json.dumps(root,ensure_ascii=False,indent=2)+"\n")
    print(json.dumps({"datasets":len(datasets),"latest":latest},ensure_ascii=False))

if __name__=="__main__":main()
