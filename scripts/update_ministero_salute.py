#!/usr/bin/env python3
from __future__ import annotations
import hashlib,json,requests
from datetime import datetime,timezone,timedelta
from pathlib import Path

OUT=Path("data/ministero_salute_latest.json");CAT=Path("data/sources_catalog.json")
UA="Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 Chrome/154 Safari/537.36"
BASE="https://www.dati.salute.gov.it/sites/default/files/opendata/"

def curl_probe(url):
    r=requests.get(url,headers={"User-Agent":UA,"Accept":"*/*"},timeout=45,stream=True,allow_redirects=True)
    r.raise_for_status()
    chunk=next(r.iter_content(chunk_size=131072),b"")
    if len(chunk)<50 or chunk.lstrip().startswith(b"<"): raise RuntimeError("invalid file")
    return chunk,r.url

def discover(pattern):
    today=datetime.now(timezone.utc).date()
    for delta in range(15):
        day=today-timedelta(days=delta)
        url=BASE+pattern.format(date=day.strftime("%Y%m%d"))
        try:
            b,u=curl_probe(url)
            return {"date":day.isoformat(),"url":u,"probe_bytes":len(b),"sha256":hashlib.sha256(b).hexdigest()}
        except Exception:
            pass
    return None

def main():
    defs={
      "apparecchiature":{"pattern":"DISPO_GAP_80_{date}.csv","format":"CSV"},
      "dispositivi_medici":{"pattern":"DISPO_RDM_1_{date}_csv.zip","format":"ZIP"}
    }
    datasets={}
    for key,cfg in defs.items():
        r=discover(cfg["pattern"])
        if r: datasets[key]={"format":cfg["format"],**r}
    if len(datasets)<2: raise RuntimeError("Ministero Salute: direct official daily files unavailable")
    latest=max(x["date"] for x in datasets.values())
    snap={"source":"Ministero della Salute","source_family":"Ministero della Salute - Open Data",
          "dataset_count":len(datasets),"datasets":datasets,"latest_update":latest,
          "checked_at":datetime.now(timezone.utc).isoformat(),"status":"feed"}
    OUT.write_text(json.dumps(snap,ensure_ascii=False,indent=2)+"\n")
    root=json.loads(CAT.read_text()) if CAT.exists() else {"sources":[]};name="Ministero della Salute - Open Data"
    src=next((x for x in root["sources"] if x.get("name")==name),None)
    if src is None:src={};root["sources"].append(src)
    src.update({"name":name,"category":"SALUTE_IT","topics":["SSN","APPARECCHIATURE","DISPOSITIVI_MEDICI"],
      "official":True,"url":"https://www.dati.salute.gov.it/","access_cost":"free","integration_status":"feed",
      "feed_status":"Attiva · file ufficiali giornalieri CSV/ZIP validati direttamente","frequency":"Giornaliera/settimanale",
      "latest_period":latest,"checked_at":snap["checked_at"]})
    CAT.write_text(json.dumps(root,ensure_ascii=False,indent=2)+"\n")
    print(json.dumps({"datasets":len(datasets),"latest":latest},ensure_ascii=False))

if __name__=="__main__":main()
