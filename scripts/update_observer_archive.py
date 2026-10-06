#!/usr/bin/env python3
from __future__ import annotations
import gzip, hashlib, json, re, urllib.parse, urllib.request
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
            raw,_,_=fetch(sm,timeout=8,max_bytes=3200000)
            if raw[:2] == b"\\x1f\\x8b":
                raw=gzip.decompress(raw)
            root=ET.fromstring(raw.decode("utf-8","ignore"))
            is_index=root.tag.lower().endswith("sitemapindex")
            rows=[]
            for node in list(root):
                loc_el=node.find("{*}loc")
                if loc_el is None or not (loc_el.text or "").strip():
                    continue
                lastmod_el=node.find("{*}lastmod")
                rows.append(((loc_el.text or "").strip(), (lastmod_el.text or "").strip() if lastmod_el is not None else ""))
            return sm,is_index,rows
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

        for _,is_index,rows in docs:
            if is_index:
                for loc,lastmod in rows:
                    low=loc.lower()
                    # Sitemap indexes often use generic filenames. Prefer indexes
                    # explicitly updated in 2026, but also follow a bounded set of
                    # generic children so active institutional sites are not missed.
                    if str(year) in lastmod or str(year) in low or any(k in low for k in (
                        "post","news","notiz","pubblic","article","comunicat",
                        "stat","sitemap","press","rapport"
                    )):
                        if loc not in visited and loc not in queue and len(queue)<64:
                            queue.append(loc)
                    elif len(queue)<28 and loc not in visited and loc not in queue:
                        queue.append(loc)
                continue
            for loc,lastmod in rows:
                if len(out)>=limit: break
                host=canonical_host(loc)
                if not host_allowed(host,[domain]): continue
                low=loc.lower()
                # lastmod is authoritative discovery metadata. Do not require
                # descriptive words inside the URL when the sitemap says 2026.
                if str(year) in lastmod or str(year) in low or any(k in low for k in (
                    "news","notiz","pubblic","rapport","osserv","stat",
                    "comunicat","dati","analisi","press"
                )):
                    out.append((urllib.parse.unquote(loc.rsplit("/",1)[-1]).replace("-"," "),loc))
    return _dedupe_results(out,limit)

def site_crawl_candidates(domain,year=2026,limit=140,extra_roots=None):
    # Generic official-site discovery independent of sitemap/search-engine quality.
    # Start from the institutional home and conventional newsroom/statistics paths,
    # then follow a bounded set of internal listing pages.
    roots=[
        f"https://{domain}/", f"https://www.{domain}/",
        f"https://{domain}/news", f"https://www.{domain}/news",
        f"https://{domain}/notizie", f"https://www.{domain}/notizie",
        f"https://{domain}/comunicati-stampa", f"https://www.{domain}/comunicati-stampa",
        f"https://{domain}/pubblicazioni", f"https://www.{domain}/pubblicazioni",
        f"https://{domain}/statistiche", f"https://www.{domain}/statistiche",
        f"https://{domain}/dati-e-statistiche", f"https://www.{domain}/dati-e-statistiche",
        f"https://{domain}/osservatori", f"https://www.{domain}/osservatori",
        f"https://{domain}/studi-e-ricerche", f"https://www.{domain}/studi-e-ricerche",
    ]
    for root in (extra_roots or []):
        if isinstance(root,str) and root.startswith("http"):
            roots.append(root)
    listing_terms=("news","notiz","comunicat","pubblic","statist","osserv","rapport",
                   "bollett","dati","studi","ricer","analisi","monitor","indagin",
                   "mercato","archiv","press","media")
    out=[]
    listing_pages=[]

    def read_links(url):
        try:
            raw,final,ct=fetch(url,timeout=6,max_bytes=1400000)
            if "html" not in ct.lower(): return []
            soup=BeautifulSoup(raw.decode("utf-8","ignore"),"html.parser")
            rows=[]
            for a in soup.find_all("a",href=True):
                href=urllib.parse.urljoin(final,a.get("href","")).split("#",1)[0]
                title=re.sub(r"\s+"," ",a.get_text(" ",strip=True))
                if not href.startswith("http") or not title: continue
                if host_allowed(canonical_host(href),[domain]):
                    rows.append((title,href))
            return rows
        except Exception:
            return []

    explicit_roots=set(extra_roots or [])
    with ThreadPoolExecutor(max_workers=8) as pool:
        root_rows=list(pool.map(read_links,roots))
        for root_url,rows in zip(roots,root_rows):
            is_explicit=root_url in explicit_roots
            for title,url in rows:
                low=(title+" "+url).lower()
                # A source-specific entrypoint is curated by us: every internal
                # editorial link is a candidate. Generic guessed roots remain filtered.
                if is_explicit or str(year) in low or any(t in low for t in STAT_TERMS) or any(t in low for t in listing_terms):
                    out.append((title,url))
                if (is_explicit or any(t in low for t in listing_terms)) and len(listing_pages)<60:
                    listing_pages.append(url)

    # Follow likely archive/listing pages one additional level.
    listing_pages=list(dict.fromkeys(listing_pages))[:36]
    with ThreadPoolExecutor(max_workers=8) as pool:
        for rows in pool.map(read_links,listing_pages):
            for title,url in rows:
                low=(title+" "+url).lower()
                if str(year) in low or any(t in low for t in STAT_TERMS) or any(t in low for t in listing_terms):
                    out.append((title,url))
                    if len(out)>=limit*3: break

    return _dedupe_results(out,limit)


def feed_candidates(domain,year=2026,limit=100,extra_seeds=None):
    seeds=list(extra_seeds or [])+[
        f"https://{domain}/feed/",
        f"https://www.{domain}/feed/",
        f"https://{domain}/feed",
        f"https://www.{domain}/feed",
        f"https://{domain}/rss",
        f"https://www.{domain}/rss",
        f"https://{domain}/rss.xml",
        f"https://www.{domain}/rss.xml",
        f"https://{domain}/atom.xml",
        f"https://www.{domain}/atom.xml",
    ]
    out=[]
    def read_feed(url):
        try:
            raw,_,_=fetch(url,timeout=6,max_bytes=1800000)
            root=ET.fromstring(raw.decode("utf-8","ignore"))
            rows=[]
            for item in root.findall(".//item"):
                title=(item.findtext("title") or "").strip()
                link=(item.findtext("link") or "").strip()
                pub=(item.findtext("pubDate") or item.findtext("date") or "").strip()
                rows.append((title,link,pub))
            for entry in root.findall(".//{*}entry"):
                title=(entry.findtext("{*}title") or "").strip()
                link=""
                for a in entry.findall("{*}link"):
                    href=(a.attrib.get("href") or "").strip()
                    if href:
                        link=href; break
                pub=(entry.findtext("{*}published") or entry.findtext("{*}updated") or "").strip()
                rows.append((title,link,pub))
            return rows
        except Exception:
            return []
    with ThreadPoolExecutor(max_workers=5) as pool:
        for rows in pool.map(read_feed,seeds):
            for title,link,pub in rows:
                if not link or not title: continue
                if str(year) in pub or str(year) in link or str(year) in title:
                    out.append((title,link))
                    if len(out)>=limit: return _dedupe_results(out,limit)
    return _dedupe_results(out,limit)




def wordpress_rest_candidates(api_urls,domains,year=2026,limit=240):
    out=[]
    for base in api_urls or []:
        for page in range(1,5):
            try:
                qs=urllib.parse.urlencode({
                    "after":f"{year}-01-01T00:00:00",
                    "before":f"{year}-12-31T23:59:59",
                    "per_page":100,"page":page,
                    "_fields":"link,date,title"
                })
                raw,_,ct=fetch(base+"?"+qs,timeout=8,max_bytes=2200000)
                data=json.loads(raw.decode("utf-8","ignore"))
                if not isinstance(data,list) or not data: break
                for item in data:
                    link=str(item.get("link","")).strip()
                    date_raw=str(item.get("date","")).strip()
                    title_obj=item.get("title") or {}
                    title=title_obj.get("rendered","") if isinstance(title_obj,dict) else str(title_obj)
                    title=BeautifulSoup(title,"html.parser").get_text(" ",strip=True)
                    if not link or not host_allowed(canonical_host(link),domains): continue
                    m=re.match(r"(20\d{2})-(\d{2})-(\d{2})",date_raw)
                    if not m: continue
                    y,mo,d=map(int,m.groups())
                    if y!=year: continue
                    out.append((title,link,datetime(y,mo,d,tzinfo=timezone.utc)))
                    if len(out)>=limit:return out
            except Exception:
                break
    return out

def rss_directory_candidates(directory_url,domains,year=2026,limit=160):
    try:
        raw,final,ct=fetch(directory_url,timeout=7,max_bytes=1600000)
        if "html" not in ct.lower(): return []
        soup=BeautifulSoup(raw.decode("utf-8","ignore"),"html.parser")
        feeds=[]
        for a in soup.find_all("a",href=True):
            label=a.get_text(" ",strip=True).lower()
            href=urllib.parse.urljoin(final,a.get("href",""))
            if any(k in label for k in ("news","comunicati","rss")) or any(k in href.lower() for k in ("rss","feed","xml")):
                feeds.append(href)
        out=[]
        for feed in list(dict.fromkeys(feeds))[:12]:
            try:
                rawf,_,_=fetch(feed,timeout=7,max_bytes=1800000)
                root=ET.fromstring(rawf.decode("utf-8","ignore"))
                for item in root.findall(".//item"):
                    title=(item.findtext("title") or "").strip()
                    link=(item.findtext("link") or "").strip()
                    pub=(item.findtext("pubDate") or item.findtext("date") or "").strip()
                    if title and link and host_allowed(canonical_host(link),domains):
                        out.append((title,link,pub))
                for entry in root.findall(".//{*}entry"):
                    title=(entry.findtext("{*}title") or "").strip()
                    link=""
                    for a in entry.findall("{*}link"):
                        if a.attrib.get("href"): link=a.attrib["href"]; break
                    pub=(entry.findtext("{*}published") or entry.findtext("{*}updated") or "").strip()
                    if title and link and host_allowed(canonical_host(link),domains):
                        out.append((title,link,pub))
            except Exception:
                continue
        return out[:limit]
    except Exception:
        return []



def sequential_listing_candidates(entrypoints,domains,year=2026,limit=360):
    """Parse institutional listings where date and headline are adjacent siblings,
    not wrapped in the same card/container. Follows common ?page=N pagination."""
    out=[]; seen=set(); queue=list(entrypoints or []); visited=set()
    months={"gennaio":1,"febbraio":2,"marzo":3,"aprile":4,"maggio":5,"giugno":6,
            "luglio":7,"agosto":8,"settembre":9,"ottobre":10,"novembre":11,"dicembre":12,
            "gen":1,"feb":2,"mar":3,"apr":4,"mag":5,"giu":6,"lug":7,"ago":8,"set":9,
            "sett":9,"ott":10,"nov":11,"dic":12,
            "january":1,"february":2,"march":3,"april":4,"may":5,"june":6,"july":7,
            "august":8,"september":9,"october":10,"november":11,"december":12,
            "jan":1,"jun":6,"jul":7,"aug":8,"sep":9,"sept":9,"oct":10,"dec":12}
    keys="|".join(sorted(months,key=len,reverse=True))
    date_rx=re.compile(
        r"\b(?:([0-3]?\d)[-/]([01]?\d)[-/](20\d{2}|\d{2})|"
        r"([0-3]?\d)\s+("+keys+r")\.?\s+(20\d{2}))\b",re.I)

    def parse_date(txt):
        m=date_rx.search(txt or "")
        if not m:return None
        try:
            if m.group(1):
                d=int(m.group(1)); mo=int(m.group(2)); y=int(m.group(3)); y=y+2000 if y<100 else y
            else:
                d=int(m.group(4)); mo=months[m.group(5).lower()]; y=int(m.group(6))
            return datetime(y,mo,d,tzinfo=timezone.utc)
        except:return None

    while queue and len(visited)<40 and len(out)<limit:
        url=queue.pop(0)
        if url in visited: continue
        visited.add(url)
        try:
            raw,final,ct=fetch(url,timeout=8,max_bytes=2200000)
            if "html" not in ct.lower(): continue
            soup=BeautifulSoup(raw.decode("utf-8","ignore"),"html.parser")
            current_date=None
            steps_since_date=0
            for el in soup.find_all(["time","span","p","div","h2","h3","a"]):
                txt=re.sub(r"\s+"," ",el.get_text(" ",strip=True)).strip()
                if not txt: continue
                d=parse_date(txt)
                if d and d.year==year:
                    current_date=d; steps_since_date=0
                    continue
                if current_date:
                    steps_since_date+=1
                    a=el if el.name=="a" and el.get("href") else el.find("a",href=True)
                    if a:
                        title=re.sub(r"\s+"," ",a.get_text(" ",strip=True)).strip()
                        href=urllib.parse.urljoin(final,a.get("href","")).split("#",1)[0]
                        if len(title)>=8 and host_allowed(canonical_host(href),domains) and href not in seen:
                            seen.add(href); out.append((title,href,current_date))
                            current_date=None
                            if len(out)>=limit: break
                    if steps_since_date>12: current_date=None

            # common pagination links
            for a in soup.find_all("a",href=True):
                label=(a.get_text(" ",strip=True)+" "+a.get("href","")).lower()
                if any(k in label for k in ("next","successiv","page=","?page=","/page/","_cur=","p_p_id=")):
                    href=urllib.parse.urljoin(final,a["href"]).split("#",1)[0]
                    if host_allowed(canonical_host(href),domains) and href not in visited and href not in queue:
                        queue.append(href)
        except Exception:
            continue
    return out


def anchor_nearby_date_candidates(entrypoints,domains,year=2026,limit=360):
    """For each article link, search nearby DOM text for a publication date."""
    out=[]; seen=set()
    months={"gennaio":1,"febbraio":2,"marzo":3,"aprile":4,"maggio":5,"giugno":6,
            "luglio":7,"agosto":8,"settembre":9,"ottobre":10,"novembre":11,"dicembre":12,
            "gen":1,"feb":2,"mar":3,"apr":4,"mag":5,"giu":6,"lug":7,"ago":8,"set":9,"sett":9,"ott":10,"nov":11,"dic":12,
            "january":1,"february":2,"march":3,"april":4,"may":5,"june":6,"july":7,"august":8,
            "september":9,"october":10,"november":11,"december":12,"jan":1,"jun":6,"jul":7,"aug":8,"sep":9,"sept":9,"oct":10,"dec":12}
    keys="|".join(sorted(months,key=len,reverse=True))
    def parse(txt):
        low=(txt or "").lower()
        m=re.search(r"\b([0-3]?\d)[-/]([01]?\d)[-/](20\d{2}|\d{2})\b",low)
        if m:
            try:
                d,mo,y=map(int,m.groups()); y=y+2000 if y<100 else y
                return datetime(y,mo,d,tzinfo=timezone.utc)
            except: pass
        m=re.search(r"\b([0-3]?\d)\s+("+keys+r")\.?\s+(20\d{2})\b",low)
        if m:
            try:return datetime(int(m.group(3)),months[m.group(2)],int(m.group(1)),tzinfo=timezone.utc)
            except: pass
        return None
    for root_url in entrypoints or []:
        try:
            raw,final,ct=fetch(root_url,timeout=8,max_bytes=2200000)
            if "html" not in ct.lower(): continue
            soup=BeautifulSoup(raw.decode("utf-8","ignore"),"html.parser")
            for a in soup.find_all("a",href=True):
                title=re.sub(r"\s+"," ",a.get_text(" ",strip=True)).strip()
                href=urllib.parse.urljoin(final,a["href"]).split("#",1)[0]
                if len(title)<8 or not host_allowed(canonical_host(href),domains) or href in seen: continue
                contexts=[]
                # Parent cards/containers.
                node=a
                for _ in range(8):
                    node=getattr(node,"parent",None)
                    if node is None: break
                    txt=re.sub(r"\s+"," ",node.get_text(" ",strip=True))
                    if txt: contexts.append(txt[:2500])
                # Nearby siblings and preceding text.
                for sib in list(a.previous_siblings)[-8:]:
                    try:
                        txt=re.sub(r"\s+"," ",sib.get_text(" ",strip=True) if hasattr(sib,"get_text") else str(sib))
                        if txt: contexts.append(txt[:1200])
                    except: pass
                date=None
                for txt in contexts:
                    d=parse(txt)
                    if d and d.year==year:
                        date=d; break
                if date:
                    seen.add(href); out.append((title,href,date))
                    if len(out)>=limit:return out
        except Exception:
            continue
    return out

def listing_dated_candidates(entrypoints,domains,year=2026,limit=300):
    out=[]; seen=set()
    for root_url in entrypoints or []:
        try:
            raw,final,ct=fetch(root_url,timeout=7,max_bytes=1800000)
            if "html" not in ct.lower(): continue
            soup=BeautifulSoup(raw.decode("utf-8","ignore"),"html.parser")
            for a in soup.find_all("a",href=True):
                href=urllib.parse.urljoin(final,a.get("href","")).split("#",1)[0]
                title=re.sub(r"\s+"," ",a.get_text(" ",strip=True)).strip()
                if len(title)<8 or not host_allowed(canonical_host(href),domains): continue
                node=a
                block=""
                for _ in range(5):
                    node=getattr(node,"parent",None)
                    if node is None: break
                    block=re.sub(r"\s+"," ",node.get_text(" ",strip=True))
                    if str(year) in block and len(block)<1800: break
                if str(year) not in block: continue
                date=None
                for pat,order in [
                    (r"\b([0-3]?\d)[-/]([01]?\d)[-/](20\d{2}|\d{2})\b","dmy"),
                    (r"\b(20\d{2})[-/]([01]?\d)[-/]([0-3]?\d)\b","ymd")
                ]:
                    m=re.search(pat,block)
                    if not m: continue
                    try:
                        vals=list(map(int,m.groups()))
                        if order=="dmy":
                            d,mo,y=vals
                            if y<100:y+=2000
                        else:y,mo,d=vals
                        date=datetime(y,mo,d,tzinfo=timezone.utc); break
                    except: pass
                if not date:
                    months={"gennaio":1,"gen":1,"febbraio":2,"feb":2,"marzo":3,"mar":3,
                            "aprile":4,"apr":4,"maggio":5,"mag":5,"giugno":6,"giu":6,
                            "luglio":7,"lug":7,"agosto":8,"ago":8,"settembre":9,"set":9,"sett":9,
                            "ottobre":10,"ott":10,"novembre":11,"nov":11,"dicembre":12,"dic":12,
                            "january":1,"jan":1,"february":2,"march":3,"april":4,"may":5,
                            "june":6,"jun":6,"july":7,"jul":7,"august":8,"aug":8,
                            "september":9,"sep":9,"sept":9,"october":10,"oct":10,
                            "november":11,"december":12,"dec":12}
                    keys="|".join(sorted(months,key=len,reverse=True))
                    m=re.search(r"\b([0-3]?\d)\s+("+keys+r")\.?\s+(20\d{2})\b",block.lower())
                    if m:
                        try: date=datetime(int(m.group(3)),months[m.group(2)],int(m.group(1)),tzinfo=timezone.utc)
                        except: pass
                    if not date:
                        m=re.search(r"\b("+keys+r")\.?\s+(20\d{2})\b",block.lower())
                        if m:
                            try: date=datetime(int(m.group(2)),months[m.group(1)],1,tzinfo=timezone.utc)
                            except: pass
                if date and date.year==year and href not in seen:
                    seen.add(href); out.append((title,href,date))
                    if len(out)>=limit:return out
        except Exception:
            continue
    return out



def cgiamestre_candidates(entrypoints,domains,year=2026,limit=420):
    """Dedicated parser for CGIA Mestre WordPress category archives.
    CGIA renders each article title in h2 with an Italian textual date nearby.
    Follow /page/N/ archives until pages stop yielding the requested year.
    """
    out=[]; seen=set()
    months={"gen":1,"feb":2,"mar":3,"apr":4,"mag":5,"giu":6,"lug":7,"ago":8,"set":9,"sett":9,"ott":10,"nov":11,"dic":12}
    rx=re.compile(r"\\b([0-3]?\\d)\\s+(gen|feb|mar|apr|mag|giu|lug|ago|set|sett|ott|nov|dic)\\s+(20\\d{2})\\b",re.I)
    roots=list(entrypoints or [])
    for root in roots:
        root=root.rstrip("/")+"/"
        empty_pages=0
        for page in range(1,45):
            url=root if page==1 else urllib.parse.urljoin(root,f"page/{page}/")
            try:
                raw,final,ct=fetch(url,timeout=8,max_bytes=2200000)
                if "html" not in ct.lower():
                    break
                soup=BeautifulSoup(raw.decode("utf-8","ignore"),"html.parser")
                page_found=0
                page_has_older=False
                for h in soup.find_all(["h2","h3"]):
                    a=h.find("a",href=True)
                    if not a:
                        continue
                    title=re.sub(r"\\s+"," ",a.get_text(" ",strip=True)).strip()
                    href=urllib.parse.urljoin(final,a["href"]).split("#",1)[0]
                    if len(title)<8 or not host_allowed(canonical_host(href),domains):
                        continue
                    block=""
                    node=h
                    for _ in range(4):
                        node=getattr(node,"parent",None)
                        if node is None:
                            break
                        block=re.sub(r"\\s+"," ",node.get_text(" ",strip=True))
                        if rx.search(block):
                            break
                    m=rx.search(block)
                    if not m:
                        continue
                    try:
                        d=int(m.group(1)); mo=months[m.group(2).lower()]; y=int(m.group(3))
                        pub=datetime(y,mo,d,tzinfo=timezone.utc)
                    except Exception:
                        continue
                    if y < year:
                        page_has_older=True
                    if y==year and href not in seen:
                        seen.add(href); out.append((title,href,pub)); page_found+=1
                        if len(out)>=limit:
                            return out
                if page_found==0:
                    empty_pages+=1
                else:
                    empty_pages=0
                if page_has_older or empty_pages>=2:
                    break
            except Exception:
                empty_pages+=1
                if empty_pages>=2:
                    break
    return out


def dataset_updated_candidates(entrypoints,domains,year=2026,limit=220):
    """Discover dataset detail pages and use their declared 'Ultimo aggiornamento' date."""
    links=[]; out=[]; seen=set()
    for root_url in entrypoints or []:
        try:
            raw,final,ct=fetch(root_url,timeout=8,max_bytes=2200000)
            if "html" not in ct.lower(): continue
            soup=BeautifulSoup(raw.decode("utf-8","ignore"),"html.parser")
            for a in soup.find_all("a",href=True):
                href=urllib.parse.urljoin(final,a["href"]).split("#",1)[0]
                if host_allowed(canonical_host(href),domains) and "/dataset/" in href and href not in links:
                    links.append(href)
        except Exception:
            continue
    for url in links[:limit*2]:
        try:
            raw,final,ct=fetch(url,timeout=8,max_bytes=1800000)
            if "html" not in ct.lower(): continue
            soup=BeautifulSoup(raw.decode("utf-8","ignore"),"html.parser")
            text=re.sub(r"\s+"," ",soup.get_text(" ",strip=True))
            m=re.search(r"Ultimo\s+aggiornamento\s*:\s*([0-3]?\d)[-/]([01]?\d)[-/](20\d{2})",text,re.I)
            if not m: continue
            d,mo,y=map(int,m.groups())
            if y!=year: continue
            h1=soup.find("h1")
            title=h1.get_text(" ",strip=True) if h1 else (soup.title.get_text(" ",strip=True) if soup.title else url)
            if final not in seen:
                seen.add(final); out.append((re.sub(r"\s+"," ",title),final,datetime(y,mo,d,tzinfo=timezone.utc)))
                if len(out)>=limit: break
        except Exception:
            continue
    return out

def page_info(url,domains):
    try:
        raw,final,ct=fetch(url,timeout=7)
        if "html" not in ct.lower(): return None
        host=canonical_host(final)
        if not host_allowed(host,domains): return None
        soup=BeautifulSoup(raw.decode("utf-8","ignore"),"html.parser")
        title=(soup.title.get_text(" ",strip=True) if soup.title else "").strip()
        h1=soup.find("h1")
        if h1 and h1.get_text(" ",strip=True): title=h1.get_text(" ",strip=True)
        text=" ".join(soup.stripped_strings)
        low=text.lower()
        nums=re.findall(r"(?<!\w)(?:20\d{2}|\d{1,3}(?:[\.,]\d{1,3})?)\s*(?:%|milioni|miliardi|mila|euro)?",low)

        # OSSERVATORI is an institutional publication archive, not the PULSE
        # statistical-pattern detector. Do not discard valid official news merely
        # because the page lacks percentages/numeric indicators.
        generic_titles={
            "news","notizie","comunicati","comunicati stampa","pubblicazioni",
            "archivio","eventi","navigazione","home","homepage","press area",
            "media","ufficio stampa","ultime news"
        }
        normalized_title=re.sub(r"\s+"," ",title).strip().lower()
        if normalized_title in generic_titles or len(normalized_title)<8:
            return None

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
        # Many institutional CMS expose the canonical publication date only in
        # JSON-LD rather than meta/time tags.
        for script in soup.find_all("script",attrs={"type":"application/ld+json"}):
            raw_json=script.get_text(" ",strip=True)
            for value in re.findall(r'"(?:datePublished|dateCreated|dateModified)"\s*:\s*"([^"]+)"',raw_json):
                meta_candidates.append(value)
        meta_candidates += re.findall(r"\b(20(?:2[5-9]|[3-9]\d)[-/]\d{1,2}[-/]\d{1,2})\b",text[:12000])
        for rawd in meta_candidates:
            rawd=rawd or ""
            # ISO / year-first dates: 2026-10-06, 2026/10/06
            m=re.search(r"(20\d{2})[-/]([01]?\d)[-/]([0-3]?\d)",rawd)
            if m:
                try:
                    y,mo,d=map(int,m.groups())
                    date=datetime(y,mo,d,tzinfo=timezone.utc)
                    break
                except: pass
            # Common Italian / European dates: 06/10/2026 or 06-10-2026.
            m=re.search(r"\b([0-3]?\d)[-/]([01]?\d)[-/](20\d{2})\b",rawd)
            if m:
                try:
                    d,mo,y=map(int,m.groups())
                    date=datetime(y,mo,d,tzinfo=timezone.utc)
                    break
                except: pass
        if not date:
            # Also inspect visible text for numeric Italian dates.
            m=re.search(r"\b([0-3]?\d)[-/]([01]?\d)[-/](20\d{2})\b",text[:16000])
            if m:
                try:
                    d,mo,y=map(int,m.groups())
                    date=datetime(y,mo,d,tzinfo=timezone.utc)
                except: pass
        if not date:
            # Italian/English textual dates, including abbreviated CMS formats:
            # 26 marzo 2026, 01 ott 2026, 14 Sept 2026.
            months={
                "gennaio":1,"gen":1,"january":1,"jan":1,
                "febbraio":2,"feb":2,"february":2,
                "marzo":3,"mar":3,"march":3,
                "aprile":4,"apr":4,"april":4,
                "maggio":5,"mag":5,"may":5,
                "giugno":6,"giu":6,"june":6,"jun":6,
                "luglio":7,"lug":7,"july":7,"jul":7,
                "agosto":8,"ago":8,"august":8,"aug":8,
                "settembre":9,"set":9,"sett":9,"september":9,"sep":9,"sept":9,
                "ottobre":10,"ott":10,"october":10,"oct":10,
                "novembre":11,"nov":11,"november":11,
                "dicembre":12,"dic":12,"december":12,"dec":12
            }
            m=re.search(r"\b([0-3]?\d)\s+("+"|".join(sorted(months,key=len,reverse=True))+r")\.?\s+(20\d{2})\b",low[:20000])
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

def process_source(src, now):
    name=src["name"]
    domains=src.get("domains",[])
    local_articles={}
    stats={"2026":0}

    for year in ARCHIVE_YEARS:
        candidates={}
        listing_dates={}
        entrypoints=src.get("entrypoints",[])

        for title,url,pub_date in listing_dated_candidates(entrypoints,domains,year,300):
            candidates.setdefault(url,title)
            listing_dates[url]=(title,pub_date)
        for title,url,pub_date in sequential_listing_candidates(entrypoints,domains,year,360):
            candidates.setdefault(url,title)
            listing_dates.setdefault(url,(title,pub_date))
        for title,url,pub_date in anchor_nearby_date_candidates(entrypoints,domains,year,360):
            candidates.setdefault(url,title)
            listing_dates.setdefault(url,(title,pub_date))

        for title,url,pub_date in wordpress_rest_candidates(src.get("api_urls",[]),domains,year,300):
            candidates.setdefault(url,title)
            listing_dates[url]=(title,pub_date)

        if src.get("adapter")=="cgiamestre":
            for title,url,pub_date in cgiamestre_candidates(entrypoints,domains,year,420):
                candidates.setdefault(url,title)
                listing_dates[url]=(title,pub_date)

        if src.get("adapter")=="dataset_updated_at":
            dataset_roots=list(entrypoints)
            for domain in domains[:2]:
                for _,u in sitemap_candidates(domain,year,320):
                    if "/dataset/" in u:
                        dataset_roots.append(u.rsplit("/dataset/",1)[0]+"/dataset/")
            for title,url,pub_date in dataset_updated_candidates(dataset_roots,domains,year,260):
                candidates.setdefault(url,title)
                listing_dates[url]=(title,pub_date)

        for title,url,pub_raw in rss_directory_candidates(src.get("rss_directory",""),domains,year,200) if src.get("rss_directory") else []:
            candidates.setdefault(url,title)

        # 1) Official source discovery first.
        with ThreadPoolExecutor(max_workers=min(2,max(1,len(domains[:2])))) as pool:
            jobs={pool.submit(sitemap_candidates,domain,year,140):domain for domain in domains[:2]}
            for fut in as_completed(jobs):
                try: results=fut.result()
                except Exception: results=[]
                for title,url in results:
                    if url and url not in candidates:
                        candidates[url]=title

        # 2) Crawl official newsroom/statistics sections directly. This is
        # crucial for institutions whose sitemap does not expose article URLs.
        with ThreadPoolExecutor(max_workers=min(2,max(1,len(domains[:2])))) as pool:
            jobs={pool.submit(site_crawl_candidates,domain,year,140,entrypoints):domain for domain in domains[:2]}
            for fut in as_completed(jobs):
                try: results=fut.result()
                except Exception: results=[]
                for title,url in results:
                    if url and url not in candidates:
                        candidates[url]=title

        # 3) Official RSS/Atom feeds catch newsrooms that expose weak sitemaps.
        with ThreadPoolExecutor(max_workers=min(2,max(1,len(domains[:2])))) as pool:
            jobs={pool.submit(feed_candidates,domain,year,120,src.get("feed_urls",[])):domain for domain in domains[:2]}
            for fut in as_completed(jobs):
                try: results=fut.result()
                except Exception: results=[]
                for title,url in results:
                    if url and url not in candidates:
                        candidates[url]=title

        # 4) Search engines are fallback only.
        if len(candidates) < 24 or src.get("adapter"):
            queries=[]
            for domain in domains[:2]:
                queries.extend([
                    f'site:{domain} {year} (dati OR statistiche OR rapporto OR osservatorio OR indagine)',
                    f'site:{domain} {year} (mercato OR monitoraggio OR rilevazione OR "open data")',
                    f'site:{domain} {year} (comunicato OR pubblicazione OR bollettino OR analisi)'
                ])
            with ThreadPoolExecutor(max_workers=min(6,max(1,len(queries)))) as pool:
                jobs=[pool.submit(web_search,q,12) for q in queries]
                for fut in as_completed(jobs):
                    try: results=fut.result()
                    except Exception: results=[]
                    for title,url in results:
                        if url and url not in candidates:
                            candidates[url]=title

        year_found=0

        # Curated listing pages are authoritative for publication date.
        for url,(listing_title,listing_date) in listing_dates.items():
            if listing_date>now or listing_date.year!=year: continue
            info=page_info(url,domains)
            title=(info or {}).get("title") or listing_title
            numbers=(info or {}).get("numbers") or []
            final_url=(info or {}).get("url") or url
            host=(info or {}).get("domain") or canonical_host(url)
            aid=stable_id(name,final_url)
            local_articles[aid]={
                "id":aid,
                "published_at":listing_date.isoformat().replace("+00:00","Z"),
                "observer":name,
                "topic":topic_of(title),
                "pulse_score":0,
                "patterns":[],
                "public_source":{
                    "url":final_url,"domain":host,
                    "role":"primary_institutional_source",
                    "verification_method":"official_listing_date"
                },
                "headline":title,
                "summary":safe_summary(name,title,listing_date,numbers),
                "territories":["italia"],
                "editorial_status":"source_publication_verified",
                "publication_status":"published"
            }
            year_found+=1
            if year_found>=MAX_RESULTS_PER_SOURCE_YEAR: break

        # Additional sitemap/feed/search candidates require detail-page verification.
        items=[(u,t) for u,t in candidates.items() if u not in listing_dates][:220]
        with ThreadPoolExecutor(max_workers=6) as pool:
            future_pages={
                pool.submit(page_info,url,domains):(title,url)
                for url,title in items
            }
            for fut in as_completed(future_pages):
                title,url=future_pages[fut]
                try: info=fut.result()
                except Exception: info=None
                if not info or info["date"].year!=year: continue
                if info["date"]>now: continue

                aid=stable_id(name,info["url"])
                local_articles[aid]={
                    "id":aid,
                    "published_at":info["date"].isoformat().replace("+00:00","Z"),
                    "observer":name,
                    "topic":topic_of(info["title"]),
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
                    break

        stats[str(year)]=year_found

    return name,stats,local_articles

def main():
    cfg=json.loads(REGISTRY.read_text())
    current=json.loads(OUT.read_text()) if OUT.exists() else {"articles":[]}
    by_id={
        a["id"]:a for a in current.get("articles",[])
        if a.get("id") and str(a.get("published_at","")).startswith("2026-")
    }
    now=datetime.now(timezone.utc)
    sources=cfg.get("sources",[])
    source_stats={}

    # Process independent institutions in parallel. A slow sitemap can no longer
    # hold up the other 62 sources.
    with ThreadPoolExecutor(max_workers=12) as pool:
        futures={pool.submit(process_source,src,now):src.get("name","") for src in sources}
        for fut in as_completed(futures):
            name=futures[fut]
            try:
                name,stats,articles=fut.result()
            except Exception as exc:
                print(f"{name}: ERROR {exc}", flush=True)
                source_stats[name]={"2026":0}
                continue
            source_stats[name]=stats
            by_id.update(articles)
            print(f"{name}: 2026={stats.get('2026',0)}", flush=True)

    arts=sorted(by_id.values(),key=lambda a:a.get("published_at",""),reverse=True)

    # Final coverage must describe the persistent archive, not only what one
    # network scan managed to rediscover today. A temporary source failure must
    # never turn a previously populated observer back to zero.
    archived_counts={src.get("name",""):0 for src in sources}
    for article in arts:
        observer=article.get("observer","")
        if observer in archived_counts and str(article.get("published_at","")).startswith("2026-"):
            archived_counts[observer]+=1

    scan_stats=source_stats
    source_stats={
        name:{
            "2026":archived_counts.get(name,0),
            "scan_2026":scan_stats.get(name,{}).get("2026",0),
            "connector_status":"ok" if scan_stats.get(name,{}).get("2026",0)>0
                               else ("degraded_preserved" if archived_counts.get(name,0)>0 else "empty_error")
        }
        for name in archived_counts
    }

    OUT.write_text(json.dumps({
        "generated_at":now.isoformat(),
        "min_year":2026,
        "max_year":2026,
        "source_count":len(sources),
        "source_stats":source_stats,
        "articles":arts
    },ensure_ascii=False,indent=2)+"\n")

if __name__=="__main__":
    main()
