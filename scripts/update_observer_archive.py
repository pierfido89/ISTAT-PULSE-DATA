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
UA="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/154.0.0.0 Safari/537.36"
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

def _dedupe_results(items,limit):
    out=[]; seen=set()
    for title,link in items:
        link=(link or "").strip()
        title=re.sub(r"\\s+"," ",title or "").strip()
        if not link or not title or link in seen: continue
        seen.add(link); out.append((title,link))
        if len(out)>=limit: break
    return out

def bing_search(query,limit=12):
    # Bing RSS silently started returning empty/non-useful payloads for many
    # site: queries. Prefer the normal HTML results and retain RSS as fallback.
    out=[]
    try:
        url="https://www.bing.com/search?"+urllib.parse.urlencode({
            "q":query,"setlang":"it-IT","count":max(10,min(limit,50))
        })
        raw,_,_=fetch(url,timeout=6,max_bytes=1400000)
        soup=BeautifulSoup(raw.decode("utf-8","ignore"),"html.parser")
        for li in soup.select("li.b_algo"):
            a=li.find("a",href=True)
            if a and a.get_text(" ",strip=True):
                out.append((a.get_text(" ",strip=True),a["href"]))
        if out:
            return _dedupe_results(out,limit)
    except Exception:
        pass

    try:
        url="https://www.bing.com/search?"+urllib.parse.urlencode({
            "q":query,"format":"rss","setlang":"it-IT"
        })
        raw,_,_=fetch(url,timeout=6,max_bytes=800000)
        root=ET.fromstring(raw)
        for item in root.findall(".//item"):
            link=(item.findtext("link") or "").strip()
            title=(item.findtext("title") or "").strip()
            if link and title: out.append((title,link))
    except Exception:
        pass
    return _dedupe_results(out,limit)

def google_search(query,limit=12):
    # Secondary discovery provider. Google is used only to discover candidate
    # URLs; every candidate must still pass official-domain and publication-date
    # verification in page_info().
    out=[]
    try:
        url="https://www.google.com/search?"+urllib.parse.urlencode({
            "q":query,"num":max(10,min(limit,50)),"filter":"0","hl":"it"
        })
        raw,_,_=fetch(url,max_bytes=1400000)
        soup=BeautifulSoup(raw.decode("utf-8","ignore"),"html.parser")
        for h3 in soup.find_all("h3"):
            a=h3.find_parent("a",href=True)
            if not a: continue
            href=a.get("href","")
            if href.startswith("/url?"):
                qs=urllib.parse.parse_qs(urllib.parse.urlparse(href).query)
                href=(qs.get("q") or qs.get("url") or [""])[0]
            if href.startswith("http"):
                out.append((h3.get_text(" ",strip=True),href))
    except Exception:
        pass
    return _dedupe_results(out,limit)

def web_search(query,limit=12):
    # Merge independent providers so one blocked/empty engine cannot zero the
    # whole archive. Official-domain validation happens later.
    merged=[]
    with ThreadPoolExecutor(max_workers=2) as pool:
        futures=[pool.submit(bing_search,query,limit),pool.submit(google_search,query,limit)]
        for fut in as_completed(futures):
            try: merged.extend(fut.result())
            except Exception: pass
    return _dedupe_results(merged,limit*2)

def sitemap_candidates(domain,year=2026,limit=180):
    # Direct discovery from the official site. Search engines are optional:
    # sitemap documents are fetched in small parallel batches to avoid turning
    # 63 sources into a long serial crawl.
    seeds=[
        f"https://{domain}/sitemap.xml",
        f"https://www.{domain}/sitemap.xml",
        f"https://{domain}/sitemap_index.xml",
        f"https://www.{domain}/sitemap_index.xml",
        f"https://{domain}/wp-sitemap.xml",
        f"https://www.{domain}/wp-sitemap.xml",
    ]

    def robots_sitemaps(url):
        try:
            raw,_,_=fetch(url,timeout=6,max_bytes=250000)
            found=[]
            for line in raw.decode("utf-8","ignore").splitlines():
                if line.lower().startswith("sitemap:"):
                    sm=line.split(":",1)[1].strip()
                    if sm.startswith("http"): found.append(sm)
            return found
        except Exception:
            return []

    with ThreadPoolExecutor(max_workers=2) as pool:
        for found in pool.map(robots_sitemaps,(
            f"https://{domain}/robots.txt",
            f"https://www.{domain}/robots.txt"
        )):
            seeds.extend(found)

    def read_sitemap(sm):
        try:
            raw,_,_=fetch(sm,timeout=8,max_bytes=2400000)
            root=ET.fromstring(raw.decode("utf-8","ignore"))
            locs=[(el.text or "").strip() for el in root.findall(".//{*}loc") if (el.text or "").strip()]
            return sm,root.tag.lower().endswith("sitemapindex"),locs
        except Exception:
            return sm,False,[]

    queue=list(dict.fromkeys(seeds))
    visited=set()
    out=[]
    while queue and len(visited)<28 and len(out)<limit:
        batch=[]
        while queue and len(batch)<8:
            sm=queue.pop(0)
            if sm not in visited:
                visited.add(sm); batch.append(sm)
        if not batch: continue

        with ThreadPoolExecutor(max_workers=min(8,len(batch))) as pool:
            docs=list(pool.map(read_sitemap,batch))

        for _,is_index,locs in docs:
            if is_index:
                for loc in locs:
                    low=loc.lower()
                    if str(year) in low or any(k in low for k in (
                        "post","news","notiz","pubblic","article","comunicat",
                        "stat","sitemap","press","rapport"
                    )):
                        if loc not in visited and loc not in queue and len(queue)<48:
                            queue.append(loc)
                continue
            for loc in locs:
                if len(out)>=limit: break
                host=canonical_host(loc)
                if not host_allowed(host,[domain]): continue
                low=loc.lower()
                if str(year) in low or any(k in low for k in (
                    "news","notiz","pubblic","rapport","osserv","stat",
                    "comunicat","dati","analisi","press"
                )):
                    out.append((urllib.parse.unquote(loc.rsplit("/",1)[-1]).replace("-"," "),loc))
    return _dedupe_results(out,limit)

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
            # PRIMARY discovery: crawl the source's own sitemap/robots archive.
            # This is more authoritative and much less fragile than depending on
            # search-engine HTML from a CI runner.
            candidates={}
            with ThreadPoolExecutor(max_workers=min(2,max(1,len(domains[:2])))) as pool:
                sitemap_jobs={
                    pool.submit(sitemap_candidates,domain,year,220):domain
                    for domain in domains[:2]
                }
                for fut in as_completed(sitemap_jobs):
                    try:
                        results=fut.result()
                    except Exception:
                        results=[]
                    for title,url in results:
                        if url and url not in candidates:
                            candidates[url]=title

            # FALLBACK discovery: retain Google + Bing, as requested, but only
            # when the official archive produced too few candidates. This avoids
            # dozens of slow/blocked engine requests for sources whose own site
            # already exposes the publications.
            if len(candidates) < 24:
                queries=[]
                for domain in domains[:2]:
                    queries.extend([
                        f'site:{domain} {year} (dati OR statistiche OR rapporto OR osservatorio OR indagine)',
                        f'site:{domain} {year} (mercato OR monitoraggio OR rilevazione OR "open data")'
                    ])
                    # Monthly queries improve recall for sites without useful
                    # sitemaps, while the six-second provider timeout bounds cost.
                    queries.extend(
                        f'site:{domain} "{month} {year}" (dati OR statistiche OR rapporto OR osservatorio OR indagine)'
                        for month in MONTHS_IT
                    )

                with ThreadPoolExecutor(max_workers=8) as pool:
                    future_searches=[pool.submit(web_search,q,12) for q in queries]
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
                    # page_info() already requires statistical language and numeric
                    # content on the official page. Do not reject valid publications
                    # merely because the headline itself lacks words such as "dati"
                    # or "rapporto" (e.g. "Banche e moneta").
                    aid=stable_id(name,info["url"])
                    if aid not in by_id:
                        topic=topic_of(info["title"])
                        by_id[aid]={
                            "id":aid,
                            "published_at":info["date"].isoformat().replace("+00:00","Z"),
                            "observer":name,
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
