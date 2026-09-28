#!/usr/bin/env python3
from __future__ import annotations
import json,re,urllib.request
from urllib.parse import urljoin
from bs4 import BeautifulSoup

HEADERS={
 "User-Agent":"Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 Chrome/153 Safari/537.36",
 "Accept":"text/html,application/xhtml+xml,application/json,*/*",
}

def fetch(url, accept=None):
    h=dict(HEADERS)
    if accept: h["Accept"]=accept
    req=urllib.request.Request(url,headers=h)
    with urllib.request.urlopen(req,timeout=60) as r:
        return r.read(),r.headers.get_content_type(),r.geturl()

def show_json_api():
    print("\n### IDROGEO PATHS")
    raw,_,_=fetch("https://idrogeo.isprambiente.it/api/","application/json")
    obj=json.loads(raw)
    print("VERSION",obj.get("info",{}).get("version"))
    for p,methods in obj.get("paths",{}).items():
        if any(k in p.lower() for k in ["comun","prov","region","alluv","fran","pericol","indic","risch"]):
            print("PATH",p,"METHODS",",".join(methods.keys()))

def inspect_page(name,url):
    print("\n###",name,url)
    try:
        raw,ctype,final=fetch(url)
        print("OK",len(raw),ctype,final)
        text=raw.decode("utf-8","ignore")
        soup=BeautifulSoup(text,"html.parser")
        for tag in soup.find_all(["script","form","a"]):
            if tag.name=="script" and tag.get("src"):
                src=urljoin(final,tag.get("src"))
                if any(x in src.lower() for x in ["js","api","main","bundle"]):
                    print("SCRIPT",src)
            elif tag.name=="form":
                print("FORM",tag.get("method"),urljoin(final,tag.get("action") or final))
            elif tag.name=="a" and tag.get("href"):
                href=urljoin(final,tag["href"])
                label=" ".join(tag.get_text(" ",strip=True).split())
                if re.search(r"\.(csv|xlsx?|xls|ods|zip|json|tsv)(\?|$)",href,re.I) or "download" in href.lower():
                    print("LINK",label[:100],href)
        for m in re.finditer(r"https?://[^\"'<>\\ ]+",text):
            u=m.group(0)
            if any(k in u.lower() for k in ["api","csv","xlsx","download","json"]):
                print("INLINE",u[:300])
    except Exception as exc:
        print("ERROR",repr(exc))

def try_urls(label,urls):
    print("\n###",label)
    for url in urls:
        try:
            raw,ctype,final=fetch(url)
            print("OK",len(raw),ctype,final)
            if len(raw)<5000 and "text" in ctype:
                print(raw[:1000].decode("utf-8","ignore").replace("\n"," "))
        except Exception as exc:
            print("ERR",url,repr(exc))

def main():
    show_json_api()
    inspect_page("TERNA_DOWNLOAD","https://dati.terna.it/download-center")
    inspect_page("TERNA_GENERAZIONE","https://dati.terna.it/generazione/dati-statistici")
    inspect_page("TERNA_DEV","https://developer.terna.it/")
    inspect_page("ISTAT_RISCHI","https://www.istat.it/wp-content/themes/EGPbs5-child/inc/mappa-rischi/?lang=it")
    inspect_page("ISPRA_RIFIUTI","https://www.catasto-rifiuti.isprambiente.it/index.php?advice=si&pg=downloadComune")
    inspect_page("ISPRA_EMISSIONI","https://emissioni.sina.isprambiente.it/inventario-nazionale/")
    inspect_page("GSE_STATS","https://www.gse.it/dati-e-scenari/statistiche")
    inspect_page("BIGBANG_DIR","https://groupware.sinanet.isprambiente.it/bigbang-data/library/bigbang100/excel_tables/")

    try_urls("GSE_GUESSES",[
      "https://www.gse.it/documenti_site/Documenti%20GSE/Rapporti%20statistici/Rapporto%20Statistico%20GSE%20-%20FER%202024.pdf",
      "https://www.gse.it/documenti_site/Documenti%20GSE/Rapporti%20statistici/Rapporto%20Statistico%20GSE%20-%20FER%202023.pdf",
      "https://www.gse.it/documenti_site/Documenti%20GSE/Rapporti%20statistici/Rapporto%20Statistico%20GSE%20-%20FER%202022.pdf",
    ])

if __name__=="__main__":
    main()
