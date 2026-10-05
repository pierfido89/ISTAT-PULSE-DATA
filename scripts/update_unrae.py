#!/usr/bin/env python3
"""UNRAE public statistics connector for ISTAT PULSE.

Discovers the latest monthly passenger-car statistics from UNRAE and stores a
normalized snapshot using only public official pages and attachments.
"""
from __future__ import annotations

import hashlib
import json
import re
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

from bs4 import BeautifulSoup

LANDING="https://www.unrae.it/dati-statistici/immatricolazioni"
PRESS="https://www.unrae.it/sala-stampa/autovetture"
OUT=Path("data/unrae_latest.json")
CATALOG=Path("data/sources_catalog.json")
UA="ISTAT-PULSE/UNRAE-connector (+https://github.com/pierfido89/ISTAT-PULSE-DATA)"

MONTHS={"gennaio":1,"febbraio":2,"marzo":3,"aprile":4,"maggio":5,"giugno":6,
"luglio":7,"agosto":8,"settembre":9,"ottobre":10,"novembre":11,"dicembre":12}

def get(url,timeout=120):
    req=urllib.request.Request(url,headers={"User-Agent":UA,"Accept":"*/*","Accept-Language":"it-IT,it;q=0.9,en;q=0.7"})
    with urllib.request.urlopen(req,timeout=timeout) as r:
        return r.read(),r.geturl(),r.headers.get("Content-Type","")

def clean(s): return re.sub(r"\s+"," ",s or "").strip()

def iso_date(text):
    m=re.search(r"(\d{1,2})\s+([A-Za-zÀ-ÿ]+)\s+(20\d{2})",text,re.I)
    if not m:return ""
    mo=MONTHS.get(m.group(2).lower())
    return f"{int(m.group(3)):04d}-{mo:02d}-{int(m.group(1)):02d}" if mo else ""

def period_from_text(text):
    m=re.search(r"(gennaio|febbraio|marzo|aprile|maggio|giugno|luglio|agosto|settembre|ottobre|novembre|dicembre)\s+(20\d{2})",text,re.I)
    if not m:return ""
    return f"{int(m.group(2)):04d}-{MONTHS[m.group(1).lower()]:02d}"

def parse_cards(html):
    soup=BeautifulSoup(html,"html.parser")
    items=[]
    seen=set()
    for a in soup.find_all("a",href=True):
        href=urllib.parse.urljoin(LANDING,a["href"])
        if "/dati-statistici/immatricolazioni/" not in href: continue
        title=clean(a.get_text(" ",strip=True))
        if not title:
            parent=a.parent
            title=clean(parent.get_text(" ",strip=True) if parent else "")
        if not title or href in seen: continue
        seen.add(href)
        ctx=clean((a.parent.parent.get_text(" ",strip=True) if a.parent and a.parent.parent else title))
        period=period_from_text(ctx+" "+title)
        pub=iso_date(ctx)
        items.append({"title":title[:220],"url":href,"period":period,"publication_date":pub})
    return items

def extract_press(html):
    text=clean(BeautifulSoup(html,"html.parser").get_text(" ",strip=True))
    result={}
    m=re.search(r"(\d{1,3}(?:\.\d{3})+)\s+nuove immatricolazioni.*?(\d{1,3}(?:\.\d{3})+)\s+unità.*?([+\-]\d+,\d+)%",text,re.I)
    if m:
        result["passenger_cars_registered"]=int(m.group(1).replace(".",""))
        result["passenger_cars_registered_previous_year"]=int(m.group(2).replace(".",""))
        result["yoy_percent"]=float(m.group(3).replace(",","."))
    bev=re.search(r"BEV[^%]{0,80}(\d+,\d+)%",text,re.I)
    phev=re.search(r"PHEV[^%]{0,80}(\d+,\d+)%",text,re.I)
    if bev: result["bev_share_percent"]=float(bev.group(1).replace(",","."))
    if phev: result["phev_share_percent"]=float(phev.group(1).replace(",","."))
    return result

def main():
    raw,final,ctype=get(LANDING)
    html=raw.decode("utf-8","ignore")
    cards=parse_cards(html)
    cards=[x for x in cards if x["period"]]
    if not cards: raise RuntimeError("UNRAE: nessuna tavola mensile individuata")
    latest_period=max(x["period"] for x in cards)
    latest=[x for x in cards if x["period"]==latest_period]

    # classify the latest-period statistical products
    wanted={}
    keys=[
      ("marca","brands"),("grupp","groups"),("struttura","market_structure"),
      ("co2","co2_bands"),("top 50","top50_models"),("alimentazione","fuel_top10"),
      ("bev","bev"),("phev","phev"),("provincia","province")
    ]
    for item in latest:
        t=item["title"].lower()
        for needle,key in keys:
            if needle in t and key not in wanted:
                wanted[key]=item

    # find matching press release
    praw,pfinal,pctype=get(PRESS)
    psoup=BeautifulSoup(praw.decode("utf-8","ignore"),"html.parser")
    press_url=""
    for a in psoup.find_all("a",href=True):
        title=clean(a.get_text(" ",strip=True))
        href=urllib.parse.urljoin(PRESS,a["href"])
        if latest_period in period_from_text(title) and "/sala-stampa/autovetture/" in href:
            press_url=href; break
    press_data={}
    press_title=""
    publication_date=max((x["publication_date"] for x in latest if x["publication_date"]),default="")
    if press_url:
        br,press_url,pc=get(press_url)
        press_html=br.decode("utf-8","ignore")
        press_title=clean(BeautifulSoup(press_html,"html.parser").find("h1").get_text(" ",strip=True)) if BeautifulSoup(press_html,"html.parser").find("h1") else ""
        press_data=extract_press(press_html)
        if not publication_date: publication_date=iso_date(clean(BeautifulSoup(press_html,"html.parser").get_text(" ",strip=True)))

    snapshot={
      "source":"UNRAE",
      "source_family":"UNRAE - Mercato auto e immatricolazioni",
      "landing_url":final,
      "period":latest_period,
      "publication_date":publication_date,
      "press_release_url":press_url,
      "press_release_title":press_title,
      "datasets":wanted,
      "dataset_count":len(wanted),
      "checked_at":datetime.now(timezone.utc).isoformat(),
      "landing_sha256":hashlib.sha256(raw).hexdigest(),
    }
    snapshot.update(press_data)
    OUT.write_text(json.dumps(snapshot,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")

    root=json.loads(CATALOG.read_text(encoding="utf-8")) if CATALOG.exists() else {"sources":[]}
    name="UNRAE - Mercato auto e immatricolazioni"
    src=next((x for x in root["sources"] if x.get("name")==name),None)
    if src is None:
        src={}; root["sources"].append(src)
    src.update({
      "name":name,
      "category":"MOBILITA_IT",
      "topics":["MOBILITA","AUTO","IMMATRICOLAZIONI"],
      "official":True,
      "url":LANDING,
      "access_cost":"free",
      "access_note":"Tavole statistiche pubbliche UNRAE accessibili senza abbonamento.",
      "integration_status":"feed",
      "feed_status":"Attiva · acquisizione automatica delle tavole pubbliche UNRAE",
      "notes":f"Connettore pubblico UNRAE: {len(wanted)} famiglie statistiche individuate per l'ultimo periodo disponibile.",
      "level":"Nazionale e territoriale secondo tavola",
      "frequency":"Mensile",
      "latest_period":latest_period,
      "publication_date":publication_date,
      "checked_at":snapshot["checked_at"],
      "provides":[
        {"area":"Mobilità e trasporti","series":"Immatricolazioni autovetture","description":"Totale mercato mensile autovetture Italia.","latest_period":latest_period,"status":"latest_public"},
        {"area":"Mobilità e trasporti","series":"Struttura del mercato per alimentazione/utilizzatore/segmento/area","description":"Tavola statistica pubblica UNRAE.","latest_period":latest_period,"status":"latest_public"},
        {"area":"Mobilità e trasporti","series":"Marche, gruppi e modelli","description":"Classifiche mensili pubbliche UNRAE.","latest_period":latest_period,"status":"latest_public"}
      ]
    })
    CATALOG.write_text(json.dumps(root,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
    print(json.dumps(snapshot,ensure_ascii=False,indent=2))

if __name__=="__main__": main()
