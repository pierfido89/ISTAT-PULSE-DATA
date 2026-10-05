#!/usr/bin/env python3
from __future__ import annotations
import hashlib,json,re,urllib.parse,urllib.request
from datetime import datetime,timezone
from pathlib import Path
from bs4 import BeautifulSoup

OUT=Path("data/ivass_latest.json"); CAT=Path("data/sources_catalog.json")
UA="ISTAT-PULSE/IVASS (+https://github.com/pierfido89/ISTAT-PULSE-DATA)"
LIST="https://www.ivass.it/pubblicazioni-e-statistiche/statistiche/comunicazioni-statistiche/"

def get(url,probe=False):
    h={"User-Agent":UA,"Accept":"*/*","Accept-Language":"it-IT,it;q=0.9"}
    if probe:h["Range"]="bytes=0-131071"
    req=urllib.request.Request(url,headers=h)
    with urllib.request.urlopen(req,timeout=180) as r:
        raw=r.read(131072 if probe else -1)
        return raw,r.geturl(),r.headers.get("Content-Type","")

def date_from_text(t):
    months={"gennaio":1,"febbraio":2,"marzo":3,"aprile":4,"maggio":5,"giugno":6,"luglio":7,"agosto":8,"settembre":9,"ottobre":10,"novembre":11,"dicembre":12}
    m=re.search(r"(\d{1,2})\s+([A-Za-zÀ-ÿ]+)\s+(20\d{2})",t,re.I)
    if m and m.group(2).lower() in months:
        return f"{m.group(3)}-{months[m.group(2).lower()]:02d}-{int(m.group(1)):02d}"
    return ""

def main():
    raw,final,_=get(LIST);soup=BeautifulSoup(raw.decode("utf-8","ignore"),"html.parser")
    releases=[]
    for a in soup.find_all("a",href=True):
        title=" ".join(a.stripped_strings)
        href=urllib.parse.urljoin(final,a["href"])
        if "Comunicazione statistica" not in title:continue
        ctx=title
        if a.parent:ctx+=" "+" ".join(a.parent.stripped_strings)
        pub=date_from_text(ctx)
        releases.append({"title":title[:260],"url":href,"publication_date":pub})
    if not releases:raise RuntimeError("IVASS: comunicazioni statistiche non trovate")
    releases.sort(key=lambda x:x["publication_date"],reverse=True)
    validated=[]
    for rel in releases[:6]:
        try:
            b,u,_=get(rel["url"]);ps=BeautifulSoup(b.decode("utf-8","ignore"),"html.parser")
            docs=[]
            for a in ps.find_all("a",href=True):
                title=" ".join(a.stripped_strings); href=urllib.parse.urljoin(u,a["href"])
                low=(title+" "+href).lower()
                if ".xlsx" in low or ".xls" in low or ".zip" in low:
                    try:
                        rb,ru,ct=get(href,True)
                        if len(rb)>50 and "text/html" not in ct.lower():
                            docs.append({"title":title,"url":ru,"content_type":ct,"probe_bytes":len(rb),
                              "probe_sha256":hashlib.sha256(rb).hexdigest()})
                    except Exception:pass
            if docs:
                validated.append({**rel,"url":u,"attachments":docs})
        except Exception:pass
        if len(validated)>=3:break
    if not validated:raise RuntimeError("IVASS: nessun allegato statistico XLSX/ZIP validato")
    latest=validated[0]
    snap={"source":"IVASS","source_family":"IVASS - Comunicazioni statistiche",
      "latest_release":latest,"release_count":len(validated),"releases":validated,
      "checked_at":datetime.now(timezone.utc).isoformat(),"status":"feed"}
    OUT.write_text(json.dumps(snap,ensure_ascii=False,indent=2)+"\n")
    root=json.loads(CAT.read_text()) if CAT.exists() else {"sources":[]};name="IVASS - Comunicazioni statistiche"
    src=next((x for x in root["sources"] if x.get("name")==name),None)
    if src is None:src={};root["sources"].append(src)
    src.update({"name":name,"category":"ASSICURAZIONI_IT",
      "topics":["ASSICURAZIONI","RC_AUTO","PREMI","MERCATO_ASSICURATIVO"],
      "official":True,"url":LIST,"access_cost":"free","integration_status":"feed",
      "feed_status":"Attiva · comunicazioni statistiche e allegati XLSX/ZIP validati",
      "frequency":"Trimestrale e periodica","latest_period":latest["publication_date"],"checked_at":snap["checked_at"]})
    CAT.write_text(json.dumps(root,ensure_ascii=False,indent=2)+"\n")
    print(json.dumps({"latest":latest["publication_date"],"releases":len(validated)},ensure_ascii=False))
if __name__=="__main__":main()
