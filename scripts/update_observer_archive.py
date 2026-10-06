#!/usr/bin/env python3
from __future__ import annotations
import hashlib, json, re, urllib.parse, urllib.request
from concurrent.futures import ThreadPoolExecutor, as_completed
import xml.etree.ElementTree as ET
from datetime import datetime, timezone
from pathlib import Path
from bs4 import BeautifulSoup

ROOT=Path("data/news")
REGISTRY=Path("data/observer_sources.json")
OUT=ROOT/"observer_articles.json"
UA="Mozilla/5.0 ISTAT-PULSE-ObserverArchive/1.0"
ARCHIVE_YEARS=(2026,)
MONTHS_IT=("gennaio","febbraio","marzo","aprile","maggio","giugno",
           "luglio","agosto","settembre","ottobre","novembre","dicembre")
MAX_RESULTS_PER_SOURCE_YEAR=120

STAT_TERMS=("dati","statistic","rapporto","osservatorio","indagine","rilevazione","open data",
            "percent","milioni","miliardi","tasso","indice","variazione","occup","pension",
            "prezzi","credito","energia","ambiente","salute","scuola","imprese","turismo",
            "popolazione","reddito","export","import","consumi","mercato")

def fetch(url, timeout=20, max_bytes=1200000):
    req=urllib.request.Request(url,headers={"User-Agent":UA,"Accept":"text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.6"})
    with urllib.request.urlopen(req,timeout=timeout) as r:
        return r.read(max_bytes),r.geturl(),r.headers.get("Content-Type","")

def canonical_host(url):
    try:return urllib.parse.urlparse(url).netloc.lower().split(":")[0].removeprefix("www.")
    except:return ""

def host_allowed(host,domains):
    return any(host==d or host.endswith("."+d) for d in domains)

def bing_search(query,limit=12):
    url="https://www.bing.com/search?"+urllib.parse.urlencode({"q":query,"format":"rss","setlang":"it-IT"})
    try:
        raw,_,_=fetch(url,max_bytes=800000)
        root=ET.fromstring(raw)
        out=[]
        for item in root.findall(".//item"):
            link=(item.findtext("link") or "").strip()
            title=(item.findtext("title") or "").strip()
            if link and title: out.append((title,link))
            if len(out)>=limit: break
        return out
    except Exception:
        return []

def page_info(url,domains):
    try:
        raw,final,ct=fetch(url)
        if "html" not in ct.lower(): return None
        host=canonical_host(final)
        if not host_allowed(host,domains): return None
        soup=BeautifulSoup(raw.decode("utf-8","ignore"),"html.parser")
        title=(soup.title.get_text(" ",strip=True) if soup.title else "").strip()
        h1=soup.find("h1")
        if h1 and h1.get_text(" ",strip=True): title=h1.get_text(" ",strip=True)
        text=" ".join(soup.stripped_strings)
        low=text.lower()
        if not any(t in low for t in STAT_TERMS): return None
        nums=re.findall(r"(?<!\w)(?:20\d{2}|\d{1,3}(?:[\.,]\d{1,3})?)\s*(?:%|milioni|miliardi|mila|euro)?",low)
        if not nums: return None

        date=None
        meta_candidates=[]
        for attrs in (
            {"property":"article:published_time"},{"name":"date"},{"name":"pubdate"},
            {"name":"publish-date"},{"itemprop":"datePublished"}
        ):
            el=soup.find("meta",attrs=attrs)
            if el and el.get("content"): meta_candidates.append(el.get("content"))
        for t in soup.find_all("time"):
            if t.get("datetime"): meta_candidates.append(t.get("datetime"))
        meta_candidates += re.findall(r"\b(20(?:2[5-9]|[3-9]\d)[-/]\d{1,2}[-/]\d{1,2})\b",text[:12000])
        for rawd in meta_candidates:
            m=re.search(r"(20\d{2})[-/]([01]?\d)[-/]([0-3]?\d)",rawd or "")
            if m:
                try:
                    y,mo,d=map(int,m.groups())
                    date=datetime(y,mo,d,tzinfo=timezone.utc)
                    break
                except: pass
        if not date:
            # Italian textual dates, e.g. 26 marzo 2025
            months={"gennaio":1,"febbraio":2,"marzo":3,"aprile":4,"maggio":5,"giugno":6,
                    "luglio":7,"agosto":8,"settembre":9,"ottobre":10,"novembre":11,"dicembre":12}
            m=re.search(r"\b([0-3]?\d)\s+("+"|".join(months)+r")\s+(20\d{2})\b",low[:16000])
            if m:
                try: date=datetime(int(m.group(3)),months[m.group(2)],int(m.group(1)),tzinfo=timezone.utc)
                except: pass
        if not date or date.year<2025: return None
        return {"title":re.sub(r"\s+"," ",title)[:220],"url":final,"domain":host,"date":date,"numbers":nums[:5]}
    except Exception:
        return None

def topic_of(text):
    low=text.lower()
    rules=[
      ("LAVORO",("lavor","occup","pension","cassa integrazione","retrib")),
      ("ECONOMIA",("econom","credito","banche","prezzi","inflaz","reddito","imprese","fisc","mercato")),
      ("SALUTE",("salute","sanit","farmac","osped")),
      ("ISTRUZIONE",("scuola","student","universit","istruzione","invalsi")),
      ("AMBIENTE",("ambiente","clima","emission","rifiuti","suolo","acqua","biodivers")),
      ("ENERGIA",("energia","elettric","gas","rinnovabil")),
      ("MOBILITA",("auto","veicol","trasport","mobilit")),
      ("TURISMO",("turismo","viaggi","presenze","pernott")),
      ("DEMOGRAFIA",("popolazione","nascit","mortal","resident"))
    ]
    for topic,words in rules:
        if any(w in low for w in words): return topic
    return "ALTRO"

def stable_id(entity,url):
    return "OBS-"+hashlib.sha256((entity+"|"+url).encode()).hexdigest()[:18].upper()

def safe_summary(entity,title,date,numbers):
    values=", ".join(dict.fromkeys(n.strip() for n in numbers if n.strip()))[:120]
    base=f"{entity} ha pubblicato questo aggiornamento quantitativo il {date.strftime('%d/%m/%Y')}. "
    if values:
        base+=f"La pagina contiene valori e indicatori numerici (tra cui {values}); "
    return base+"ISTAT PULSE lo archivia nell’Osservatorio della fonte primaria senza attribuire un punteggio PULSE quando non emerge un pattern statistico verificato."

def main():
    cfg=json.loads(REGISTRY.read_text())
    current=json.loads(OUT.read_text()) if OUT.exists() else {"articles":[]}
    # From now on OSSERVATORI is a live archive starting on 1 January 2026.
    # Purge legacy 2025 material so every entity follows the same rule.
    by_id={
        a["id"]:a for a in current.get("articles",[])
        if a.get("id") and str(a.get("published_at","")).startswith("2026-")
    }
    now=datetime.now(timezone.utc)
    source_stats={}
    for src in cfg.get("sources",[]):
        name=src["name"]; domains=src.get("domains",[])
        source_stats[name]={"2026":0}

        for year in ARCHIVE_YEARS:
            queries=[]
            for domain in domains[:2]:
                queries.extend([
                    f'site:{domain} {year} (dati OR statistiche OR rapporto OR osservatorio)',
                    f'site:{domain} {year} (indagine OR "open data" OR rilevazione OR monitoraggio)'
                ])
                queries.extend(
                    f'site:{domain} "{month} {year}" (dati OR statistiche OR rapporto OR osservatorio OR indagine)'
                    for month in MONTHS_IT
                )

            # Network I/O is the bottleneck. Search queries are independent, so run a
            # small bounded pool instead of waiting for every request sequentially.
            candidates={}
            with ThreadPoolExecutor(max_workers=8) as pool:
                future_searches=[pool.submit(bing_search,q,12) for q in queries]
                for fut in as_completed(future_searches):
                    try:
                        results=fut.result()
                    except Exception:
                        results=[]
                    for title,url in results:
                        if url and url not in candidates:
                            candidates[url]=title

            year_found=0
            # Page verification is independent too; keep the same conservative pool.
            with ThreadPoolExecutor(max_workers=8) as pool:
                future_pages={
                    pool.submit(page_info,url,domains):(title,url)
                    for url,title in candidates.items()
                }
                for fut in as_completed(future_pages):
                    title,url=future_pages[fut]
                    try:
                        info=fut.result()
                    except Exception:
                        info=None
                    if not info or info["date"].year!=year: continue
                    if info["date"]>now: continue
                    low=(info["title"]+" "+title).lower()
                    if not any(t in low for t in ("dati","stat","rapport","osserv","indagin","rilev","mercato","bilancio","monitor","analisi","pubblic")):
                        continue

                    aid=stable_id(name,info["url"])
                    if aid not in by_id:
                        topic=topic_of(info["title"])
                        by_id[aid]={
                            "id":aid,
                            "published_at":info["date"].isoformat().replace("+00:00","Z"),
                            "topic":topic,
                            "pulse_score":0,
                            "patterns":[],
                            "public_source":{
                                "url":info["url"],"domain":info["domain"],
                                "role":"primary_statistical_source",
                                "verification_method":"official_domain_backfill"
                            },
                            "headline":info["title"],
                            "summary":safe_summary(name,info["title"],info["date"],info["numbers"]),
                            "territories":["italia"],
                            "editorial_status":"source_publication_verified",
                            "publication_status":"published"
                        }
                    year_found+=1
                    if year_found>=MAX_RESULTS_PER_SOURCE_YEAR:
                        for pending in future_pages:
                            pending.cancel()
                        break

            source_stats[name][str(year)]=year_found
        print(f"{name}: 2026={source_stats[name]['2026']}")

    arts=sorted(by_id.values(),key=lambda a:a.get("published_at",""),reverse=True)
    OUT.write_text(json.dumps({
        "generated_at":now.isoformat(),
        "min_year":2026,
        "max_year":2026,
        "source_count":len(cfg.get("sources",[])),
        "source_stats":source_stats,
        "articles":arts
    },ensure_ascii=False,indent=2)+"\n")

if __name__=="__main__":
    main()
