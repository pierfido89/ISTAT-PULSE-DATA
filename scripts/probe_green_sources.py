#!/usr/bin/env python3
from __future__ import annotations
import json, re, ssl, urllib.request
from urllib.parse import urljoin
from bs4 import BeautifulSoup

PAGES = {
    "ACI": "https://aci.gov.it/attivita-e-progetti/studi-e-ricerche/open-data/",
    "ARERA": "https://www.arera.it/dati-e-statistiche/dettaglio/rqsii",
    "GSE": "https://www.gse.it/dati-e-scenari/statistiche",
    "ENEA": "https://www.efficienzaenergetica.enea.it/vi-segnaliamo/rapporto-annuale-sullefficienza-energetica-2026-schede-regionali.html",
    "ISPRA_RIFIUTI": "https://www.catasto-rifiuti.isprambiente.it/index.php?advice=si&pg=downloadComune",
    "ISPRA_SUOLO": "https://www.isprambiente.gov.it/it/attivita/suolo-e-territorio/suolo/il-consumo-di-suolo/i-dati-sul-consumo-di-suolo",
    "ISPRA_BIODIV": "https://indicatoriambientali.isprambiente.it/it/biodiversita-stato-e-minacce/stato-di-conservazione-delle-specie-di-direttiva-habitat-9243cee",
    "ISPRA_ACQUA": "https://www.isprambiente.gov.it/pre_meteo/idro/BIGBANG_ISPRA.html",
    "ISTAT_SDG": "https://www.istat.it/statistiche-per-temi/focus/benessere-e-sostenibilita/obiettivi-di-sviluppo-sostenibile/gli-indicatori-istat/",
    "ISTAT_AMB_URB": "https://www.istat.it/comunicato-stampa/ambiente-urbano-anno-2024/",
    "ISTAT_ACQUA": "https://www.istat.it/comunicato-stampa/le-statistiche-sullacqua-anni-2023-2025/",
    "ISTAT_RISCHI": "https://www.istat.it/wp-content/themes/EGPbs5-child/inc/mappa-rischi/?lang=it",
    "EEA": "https://www.eea.europa.eu/en/europe-environment-2025/countries/data-download",
    "TERNA": "https://dati.terna.it/",
}

UA={"User-Agent":"ISTAT-PULSE-GREEN/0.1 (+https://github.com/pierfido89/ISTAT-PULSE-DATA)"}

def get(url):
    req=urllib.request.Request(url,headers=UA)
    with urllib.request.urlopen(req,timeout=60) as r:
        return r.read(), r.headers.get_content_type(), r.geturl()

def main():
    for name,url in PAGES.items():
        print("\n###",name,url)
        try:
            raw,ctype,final=get(url)
            print("HTTP OK",len(raw),"bytes",ctype,final)
            text=raw.decode("utf-8","ignore")
            soup=BeautifulSoup(text,"html.parser")
            links=[]
            for a in soup.find_all("a",href=True):
                href=urljoin(final,a["href"])
                label=" ".join(a.get_text(" ",strip=True).split())
                if re.search(r"\.(?:csv|xlsx?|ods|zip|json|geojson|tsv)(?:\?|$)",href,re.I) or any(k in label.lower() for k in ["csv","xlsx","xls","ods","zip","download","scarica","dati"]):
                    links.append((label[:120],href))
            # unique, limited
            seen=set()
            for label,href in links:
                if href in seen: continue
                seen.add(href)
                print("LINK",json.dumps({"label":label,"url":href},ensure_ascii=False))
            if not links:
                print("NO DOWNLOAD LINKS DETECTED")
        except Exception as exc:
            print("ERROR",repr(exc))

    print("\n### IDROGEO API")
    for url in [
        "https://idrogeo.isprambiente.it/api/",
        "https://idrogeo.isprambiente.it/openapi/",
        "https://idrogeo.isprambiente.it/api/openapi.json",
        "https://idrogeo.isprambiente.it/openapi/openapi.json",
    ]:
        try:
            raw,ctype,final=get(url)
            print("IDRO",url,len(raw),ctype,final,raw[:300].decode("utf-8","ignore").replace("\n"," "))
        except Exception as exc:
            print("IDRO ERROR",url,repr(exc))

    print("\n### TERNA developer")
    for url in ["https://developer.terna.it/","https://developer.terna.it/api/","https://developer.terna.it/swagger/index.html"]:
        try:
            raw,ctype,final=get(url)
            print("TERNADEV",url,len(raw),ctype,final,raw[:250].decode("utf-8","ignore").replace("\n"," "))
        except Exception as exc:
            print("TERNADEV ERROR",url,repr(exc))

if __name__=="__main__":
    main()
