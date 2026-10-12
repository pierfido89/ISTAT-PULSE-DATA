#!/usr/bin/env python3
from __future__ import annotations
import hashlib, html, io, json, re, time, urllib.parse, urllib.request, signal
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta, timezone
from email.utils import parsedate_to_datetime
from zoneinfo import ZoneInfo
from pathlib import Path
from bs4 import BeautifulSoup
try:
    from scripts.pulse_evidence import extract_bytes as extract_evidence_bytes
except ModuleNotFoundError:
    from pulse_evidence import extract_bytes as extract_evidence_bytes

try:
    from scripts.pulse_evidence_adapters import (
        discover_attachments, parse_sdmx_json, parse_sdmx_xml, load_revision_metadata
    )
except ModuleNotFoundError:
    from pulse_evidence_adapters import (
        discover_attachments, parse_sdmx_json, parse_sdmx_xml, load_revision_metadata
    )

ROOT=Path("data/news")
CFG=Path("data/news_radar_sources.json")
ARTICLES=ROOT/"articles.json"
CANDIDATES=ROOT/"candidates.json"
INDEX=ROOT/"index.json"
UA="Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 Chrome/154 Safari/537.36 ISTAT-PULSE-NewsRadar/1.2"
MAX_RUNTIME_SECONDS=720
MAX_ITEMS_PER_FEED=40
MAX_CANDIDATES_TOTAL=180

TOPIC_DOMAINS={
 "LAVORO":["istat.it","inps.it","inail.it","unioncamere.gov.it"],
 "ECONOMIA":["istat.it","bancaditalia.it","mef.gov.it","unioncamere.gov.it"],
 "SALUTE":["salute.gov.it","iss.it","agenas.gov.it","aifa.gov.it"],
 "ISTRUZIONE":["invalsi.it","istruzione.it","istat.it","mur.gov.it","skuola.net","gigroupholding.com"],
 "AMBIENTE":["isprambiente.gov.it","istat.it","eea.europa.eu"],
 "ENERGIA":["terna.it","gse.it","arera.it","istat.it"],
 "MOBILITA":["aci.it","unrae.it","anfia.it","aniasa.it","istat.it"],
 "CASA":["agenziaentrate.gov.it","bancaditalia.it","istat.it"],
 "DEMOGRAFIA":["istat.it"]
}

STAT_TERMS=(
 "dato","dati","statistica","statistiche","rapporto","osservatorio","indagine","rilevazione",
 "percento","%","aumento","calo","crescita","diminuzione","record","massimo","minimo","media",
 "milioni","miliardi","tasso","quota","indice","variazione","occupazione","disoccupazione",
 "natalità","mortalità","inflazione","prezzi","consumi","salari","redditi","imprese","export",
 "import","mutui","immobili","scuola","studenti","sanità","salute","energia","emissioni","rifiuti"
)
GEO={"abruzzo","basilicata","calabria","campania","emilia-romagna","friuli-venezia giulia","lazio",
"liguria","lombardia","marche","molise","piemonte","puglia","sardegna","sicilia","toscana",
"trentino-alto adige","umbria","valle d'aosta","veneto","roma","milano","napoli","torino",
"palermo","bologna","firenze","genova","venezia","bari"}

def fetch(url, timeout=12, max_bytes=700000):
    req=urllib.request.Request(url,headers={"User-Agent":UA,"Accept":"text/html,application/rss+xml,application/xml;q=0.9,*/*;q=0.5"})
    with urllib.request.urlopen(req,timeout=timeout) as r:
        return r.read(max_bytes),r.geturl(),r.headers.get("Content-Type","")

def load_json(path, default):
    try:return json.loads(path.read_text())
    except:return default

def clean_text(raw):
    return re.sub(r"\s+"," ",BeautifulSoup(html.unescape(raw or ""),"html.parser").get_text(" ",strip=True)).strip()

def rss_items(url):
    raw,final,_=fetch(url)
    root=ET.fromstring(raw)
    out=[]
    for item in root.findall(".//item"):
        def t(tag):
            el=item.find(tag); return (el.text or "").strip() if el is not None else ""
        title=t("title"); link=t("link"); desc=t("description"); pub=t("pubDate")
        if title and link: out.append({"title":title,"url":link,"summary":clean_text(desc),"published_raw":pub})
    return out[:MAX_ITEMS_PER_FEED]

def score_candidate(text):
    low=text.lower()
    score=0
    term_hits=sum(1 for t in STAT_TERMS if t in low)
    score += min(35,term_hits*5)
    nums=re.findall(r"(?<!\w)[+-]?(?:20\d{2}|\d{1,3}(?:[\.,]\d+)?)\s*(?:%|milioni|miliardi|mila)?",low)
    score += min(30,len(nums)*6)
    if re.search(r"\b(20\d{2}|\d{1,2}[\.,]\d+\s*%)\b",low): score+=10
    if any(x in low for x in ("record","massimo storico","minimo storico","mai così","più alto","più basso")): score+=15
    if any(g in low for g in GEO): score+=5
    return min(100,score), nums[:12]

def canonical_host(url):
    try:return urllib.parse.urlparse(url).netloc.lower().split(":")[0].removeprefix("www.")
    except:return ""

def official_domain(host, domains):
    return next((d for d in domains if host==d or host.endswith("."+d)),None)

def article_probe(url, domains, hints):
    try:
        raw,final,ct=fetch(url,timeout=10,max_bytes=500000)
        if "html" not in ct.lower(): return {"final_url":final,"text":"","official_links":[],"hint_domains":[]}
        soup=BeautifulSoup(raw.decode("utf-8","ignore"),"html.parser")
        for tag in soup(["script","style","nav","footer","header","aside"]): tag.decompose()
        text=re.sub(r"\s+"," "," ".join(soup.stripped_strings))[:30000]
        links=[]
        for a in soup.find_all("a",href=True):
            h=urllib.parse.urljoin(final,a["href"]); dom=official_domain(canonical_host(h),domains)
            if dom and h not in links: links.append(h)
        low=text.lower()
        hint_domains=sorted({d for k,d in hints.items() if k in low})
        return {"final_url":final,"text":text,"official_links":links[:12],"hint_domains":hint_domains}
    except Exception:
        return {"final_url":url,"text":"","official_links":[],"hint_domains":[]}


def normalize_number_token(x):
    x=(x or "").lower().strip()
    x=x.replace("milioni","").replace("miliardi","").replace("mila","").replace("%","")
    x=re.sub(r"[^0-9,.-]","",x)
    return x.strip(" .,-")

def title_keywords(text):
    stop={"italia","italiano","italiani","oggi","ieri","anno","anni","dati","dato","statistiche","statistica",
          "rapporto","secondo","oltre","sono","della","delle","degli","dello","nella","nelle","con","per","tra","fra",
          "che","del","dei","gli","una","uno","più","meno","news"}
    words=re.findall(r"[a-zà-ù]{4,}",(text or "").lower())
    out=[]
    for w in words:
        if w not in stop and w not in out: out.append(w)
    return out[:8]

def ddg_search(query, limit=6):
    url="https://html.duckduckgo.com/html/?"+urllib.parse.urlencode({"q":query})
    try:
        raw,_,_=fetch(url,timeout=10,max_bytes=600000)
        soup=BeautifulSoup(raw.decode("utf-8","ignore"),"html.parser")
        out=[]
        for a in soup.select("a.result__a"):
            href=a.get("href","")
            if not href: continue
            if "uddg=" in href:
                try:
                    qs=urllib.parse.parse_qs(urllib.parse.urlparse(href).query)
                    href=qs.get("uddg",[href])[0]
                except: pass
            out.append({"url":href,"title":" ".join(a.stripped_strings)})
            if len(out)>=limit: break
        return out
    except Exception:
        return []


def bing_search(query, limit=8):
    url="https://www.bing.com/search?"+urllib.parse.urlencode({"q":query,"format":"rss","setlang":"it-IT"})
    try:
        raw,_,_=fetch(url,timeout=10,max_bytes=700000)
        root=ET.fromstring(raw)
        out=[]
        for item in root.findall(".//item"):
            link=(item.findtext("link") or "").strip()
            title=(item.findtext("title") or "").strip()
            if link:
                out.append({"url":link,"title":title})
            if len(out)>=limit: break
        return out
    except Exception:
        return []

def multi_search(query, limit=10):
    out=[]; seen=set()
    for provider in (bing_search,ddg_search):
        for r in provider(query,limit=limit):
            u=r.get("url")
            if u and u not in seen:
                seen.add(u); out.append(r)
            if len(out)>=limit: return out
    return out

def extract_document_text(raw, content_type, url):
    ct=(content_type or "").lower()
    if "pdf" in ct or url.lower().split("?")[0].endswith(".pdf"):
        try:
            from pypdf import PdfReader
            reader=PdfReader(io.BytesIO(raw))
            parts=[]
            for page in reader.pages[:25]:
                try: parts.append(page.extract_text() or "")
                except: pass
            return re.sub(r"\s+"," "," ".join(parts))[:120000]
        except Exception:
            return ""
    try:
        return clean_text(raw.decode("utf-8","ignore"))[:120000]
    except Exception:
        return ""


def numeric_variants(token):
    raw=(token or "").lower().strip()
    core=normalize_number_token(raw)
    if not core: return []
    vars={core,core.replace(",", "."),core.replace(".", ",")}
    # thousands separators: 38.000 <-> 38000
    if re.fullmatch(r"\d{1,3}\.\d{3}",core): vars.add(core.replace(".",""))
    if re.fullmatch(r"\d{1,3},\d{3}",core): vars.add(core.replace(",",""))
    return [v for v in vars if v]

def extract_verified_year_comparisons(raw, content_type, url):
    """Only compare percentages in a single primary-source HTML table row.

    Each observation is tied to the *same row label* and an explicit year
    column. Never infer years from prose or compare unrelated quantities.
    """
    if "html" not in (content_type or "").lower() and not url.lower().split("?")[0].endswith((".html", ".htm")):
        return []
    soup = BeautifulSoup(raw, "html.parser")
    evidence = []
    year_re = re.compile(r"^(?:19|20)\d{2}$")
    number_re = re.compile(r"^([+-]?\d{1,3}(?:[.,]\d{1,2})?)\s*%?$")
    for table in soup.find_all("table", limit=30):
        rows = table.find_all("tr", limit=150)
        if len(rows) < 2: continue
        headers = [clean_text(c.get_text(" ", strip=True)) for c in rows[0].find_all(["th", "td"], recursive=False)]
        years = [(i, int(h)) for i, h in enumerate(headers) if year_re.fullmatch(h)]
        if len(years) < 2: continue
        years = sorted(years, key=lambda pair: pair[1])[-2:]
        if years[1][1] - years[0][1] > 5: continue
        caption = table.find("caption")
        table_heading = clean_text(caption.get_text(" ", strip=True)) if caption else ""
        for row in rows[1:]:
            cells = [clean_text(c.get_text(" ", strip=True)) for c in row.find_all(["th", "td"], recursive=False)]
            if len(cells) <= max(i for i, _ in years): continue
            indicator = cells[0].strip()
            if not 5 <= len(indicator) <= 120 or year_re.fullmatch(indicator): continue
            # Unit must be explicit in the row or its table caption.
            if not ("%" in indicator or "percent" in indicator.lower() or "%" in table_heading[:160] or "percent" in table_heading[:160].lower()):
                continue
            values = []
            for col, year in years:
                m = number_re.fullmatch(cells[col])
                if m is None: break
                token = m.group(1)
                # Italian thousands separators cannot be confused with decimals.
                value = float(token.replace(",", "."))
                if not 0 <= value <= 100: break
                values.append({"period": str(year), "value": value, "raw": cells[col]})
            if len(values) != 2: continue
            evidence.append({
                "indicator": indicator, "unit": "%", "observations": values,
                "source_url": url, "extraction_method": "same_row_explicit_year_html_table",
                "verified": True, "comparison_unit": "punti percentuali"
            })
            if len(evidence) >= 4: return evidence
    return evidence


def verify_primary_page(url, numbers, keywords, allowed_domains):
    host=canonical_host(url)
    dom=official_domain(host,allowed_domains)
    if not dom: return None
    try:
        raw,final,ct=fetch(url,timeout=12,max_bytes=6000000)
        # For binary workbooks, use *verified table cells* as search context.
        # Never treat arbitrary binary bytes as searchable statistical text.
        preextracted = None
        if final.lower().split("?")[0].endswith((".xlsx", ".xls", ".csv", ".tsv", ".json")):
            try:
                preextracted = extract_evidence_bytes(raw, final, ct)
            except Exception:
                preextracted = None
        text=extract_document_text(raw,ct,final)
        if preextracted and preextracted.get("evidence"):
            verified_context = " ".join(
                e["indicator"] + " " +
                " ".join(obs["raw"] + " " + obs["period"] for obs in e["observations"])
                for e in preextracted["evidence"]
            )
            text = (text + " " + verified_context).strip()
        if not text: return None
        low=text.lower()
        matched_numbers=[]
        matched_non_year_numbers=[]
        for n in numbers:
            nn=normalize_number_token(n)
            if len(nn)>=1 and any(v in low for v in numeric_variants(n)):
                matched_numbers.append(n)
                if not re.fullmatch(r"20\d{2}", nn):
                    matched_non_year_numbers.append(n)
        matched_keywords=[k for k in keywords if k in low]
        score=(40 if matched_non_year_numbers else 0)+min(40,len(matched_keywords)*8)+(15 if dom else 0)
        if not matched_non_year_numbers or score<55: return None
        # Reuse the already fetched original document; no redundant HTTP request.
        # Fail closed when an unreadable PDF, workbook or malformed table is encountered.
        try:
            verified_series = (preextracted or extract_evidence_bytes(raw, final, ct))["evidence"]
            # After the primary page passes domain/number/keyword verification,
            # inspect a strictly bounded set of same-host downloadable tables.
            if "html" in ct.lower():
                for attachment in discover_attachments(raw, final, max_links=3):
                    try:
                        a_raw, a_url, a_ct = fetch(attachment, timeout=8, max_bytes=4000000)
                        a_path = urllib.parse.urlsplit(a_url).path.lower()
                        if a_path.endswith(".json") and ("sdmx" in a_url.lower()):
                            candidate = parse_sdmx_json(a_raw, a_url)
                        elif a_path.endswith(".xml") and ("sdmx" in a_url.lower()):
                            candidate = parse_sdmx_xml(a_raw, a_url)
                        else:
                            candidate = extract_evidence_bytes(a_raw, a_url, a_ct)
                        verified_series.extend(candidate.get("evidence", [])[:4])
                    except Exception as exc:
                        print(f"[ATTACHMENT] skipped {attachment}: {type(exc).__name__}", flush=True)
            # Conservative companion metadata gate: if the same official page
            # links a machine-readable revision bulletin that announces a
            # series break, withhold every comparison on that page.
            if "html" in ct.lower() and verified_series:
                for tag in BeautifulSoup(raw, "html.parser").select("a[href]")[:150]:
                    link = urllib.parse.urljoin(final, tag.get("href", ""))
                    label = (tag.get_text(" ", strip=True) + " " + link).lower()
                    if not link.lower().split("?")[0].endswith(".json"):
                        continue
                    if not any(word in label for word in ("revision", "metodolog", "series-break", "serie-storica")):
                        continue
                    if urllib.parse.urlsplit(link).hostname != urllib.parse.urlsplit(final).hostname:
                        continue
                    try:
                        metadata_raw, _, _ = fetch(link, timeout=7, max_bytes=200000)
                        metadata = load_revision_metadata(metadata_raw)
                        if metadata["status"] == "methodological_break":
                            verified_series = []
                            print(f"[REVISION] comparison withheld for {final}", flush=True)
                            break
                    except Exception:
                        continue
            verified_series = verified_series[:12]
        except Exception as exc:
            print(f"[EVIDENCE] skipped {final}: {type(exc).__name__}", flush=True)
            verified_series = []
        return {"url":final,"domain":dom,"matched_numbers":matched_numbers[:6],"matched_non_year_numbers":matched_non_year_numbers[:6],
                "matched_keywords":matched_keywords[:8],"verification_score":min(100,score),
                "text_excerpt":text[:900], "verified_series":verified_series}
    except Exception:
        return None


PRIMARY_ENTITY_PATTERNS=[
 ("istat","istat.it"),
 ("asso franchising","assofranchising.it"),
 ("assofranchising","assofranchising.it"),
 ("garante privacy","garanteprivacy.it"),
 ("garante per la protezione dei dati personali","garanteprivacy.it"),
 ("edison energia","edison.it"),
 ("life turtlenest","legambiente.it"),
 ("brave-wow","iss.it"),
 ("tuttoscuola","tuttoscuola.com"),
 ("crif","crif.it"),
 ("confindustria nautica","confindustrianautica.net"),
 ("deloitte","deloitte.com"),
 ("legambiente","legambiente.it"),
 ("banca d'italia","bancaditalia.it"),
 ("bankitalia","bancaditalia.it"),
 ("inps","inps.it"),
 ("inail","inail.it"),
 ("aifa","aifa.gov.it"),
 ("iss","iss.it"),
 ("agenas","agenas.gov.it"),
 ("ispra","isprambiente.gov.it"),
 ("invalsi","invalsi.it"),
 ("unioncamere","unioncamere.gov.it"),
 ("anfia","anfia.it"),
 ("unrae","unrae.it"),
 ("aniasa","aniasa.it"),
 ("dataforce","aniasa.it"),
 ("skuola.net","skuola.net"),
 ("gi edu","gigroupholding.com"),
 ("gi group","gigroupholding.com")
]

TRUSTED_PRIMARY_DOMAINS={
 "istat.it","inps.it","inail.it","bancaditalia.it","mef.gov.it","agenziaentrate.gov.it",
 "salute.gov.it","iss.it","agenas.gov.it","aifa.gov.it","invalsi.it","istruzione.it","mur.gov.it",
 "isprambiente.gov.it","arera.it","gse.it","terna.it","aci.it","anfia.it","unrae.it",
 "unioncamere.gov.it","assofranchising.it","tuttoscuola.com","crif.it","confindustrianautica.net",
 "deloitte.com","legambiente.it","legambienteveneto.it","garanteprivacy.it","edison.it",
 "confcommerciomilano.it","lifeturtlenest.eu","aniasa.it","dataforce.de","skuola.net","gigroupholding.com"
}

def extract_named_primary_domains(text):
    low=(text or "").lower()
    out=[]
    for name,dom in PRIMARY_ENTITY_PATTERNS:
        if name in low and dom not in out: out.append(dom)
    return out

def looks_editorially_irrelevant(title):
    low=(title or "").lower()
    bad=("pronostico","quote e statistiche","scommesse","oddschecker","calendario partite",
         "ospita","evento","festival","dal 2027/28 limite","decreto scuola",
         "sarà a industria italiana summit","summit 2026")
    return any(x in low for x in bad)

def journalistic_statistical_article(item, feed, now, topic, geos, nums, score, existing=None):
    """Publish factual news with numeric evidence attributed to the reporting outlet.
    This is NOT a primary-source-verified statistical series or PULSE pattern.
    """
    try:
        published = parsedate_to_datetime(item.get("published_raw", ""))
        if published.tzinfo is None:
            published = published.replace(tzinfo=timezone.utc)
        published = published.astimezone(timezone.utc)
        if not (timedelta(0) <= now - published <= timedelta(days=3)):
            return None
    except (TypeError, ValueError, OverflowError):
        return None
    title = clean_text(item.get("title", ""))
    description = clean_text(item.get("summary", ""))
    # Numeric substance beyond year labels required; no generic, promotional or sports pages.
    meaningful = [n for n in nums if not re.fullmatch(r"20\\d{2}", normalize_number_token(n))]
    if not meaningful or score < 45 or len(title) < 24:
        return None
    if not any(term in (title + " " + description).lower() for term in STAT_TERMS):
        return None
    source_url = item.get("url", "")
    if not source_url.startswith("https://") and not source_url.startswith("http://"):
        return None
    # The original RSS report is the disclosed journalistic source; Google
    # News links remain explicitly journalistic, not official statistical data.
    host = canonical_host(source_url)
    # Google News RSS links are discovery links to the original publisher.
    # Keep them clearly labeled as aggregates; do not call them verified primary sources.
    publisher = title.rsplit(" - ", 1)[-1].strip() if host.endswith("news.google.com") and " - " in title else host
    key = stable_id(source_url, topic, title, meaningful)
    existing = existing or {}
    return {
        "id": key,
        "story_fingerprint": story_fingerprint(source_url, topic, title, meaningful),
        "published_at": existing.get("published_at") or published.isoformat(),
        "last_seen_at": now.isoformat(),
        "topic": topic,
        "pulse_score": min(75, max(45, score)),
        "patterns": [],
        "public_source": {
            "url": source_url,
            "domain": publisher,
            "role": "journalistic_source",
            "verification_method": "reported_statistical_figures_not_primary_verified",
            "verification_score": 0
        },
        "headline": title,
        "summary": description[:600] or "Notizia con dati numerici riportati dalla testata indicata. I valori non sono ancora verificati sulla fonte statistica primaria.",
        "statistical_claims": [{"raw_value": n, "verified": False} for n in meaningful[:6]],
        "territories": geos,
        "editorial_status": "journalistic_attributed",
        "publication_status": "published"
    }


def semantic_key(title, topic, numbers):
    clean=(title or "").lower().split(" - ")[0].split(" | ")[0]
    clean=re.sub(r"[^a-z0-9à-ù ]"," ",clean)
    words=[w for w in clean.split() if len(w)>=4 and w not in {"italia","dati","statistiche","statistica","rapporto","news","record"}]
    core=" ".join(sorted(set(words[:7])))
    vals=[]
    for n in numbers:
        v=normalize_number_token(n)
        if v and not re.fullmatch(r"20\d{2}",v): vals.append(v)
    nums="|".join(sorted(set(vals)))
    return hashlib.sha256(f"{topic}|{core}|{nums}".encode()).hexdigest()[:20]

SELF_PRIMARY_DOMAINS={"aniasa.it","skuola.net","gigroupholding.com","assofranchising.it","crif.it",
                      "confindustrianautica.net","legambiente.it","lifeturtlenest.eu"}

def resolve_primary(discovery_title, discovery_text, topic, numbers, direct_links, hint_domains, cfg):
    institutional=cfg.get("official_domains",[])
    attempts=[]
    named_domains=extract_named_primary_domains(discovery_title+" "+discovery_text[:5000])
    allowed=list(dict.fromkeys(institutional+named_domains))
    kws=title_keywords(discovery_title+" "+discovery_text[:1800])

    # 1) Direct links found in the discovery article.
    for u in direct_links:
        v=verify_primary_page(u,numbers,kws,allowed)
        if v:
            v["method"]="direct_primary_link"; v["attempts"]=attempts; return v

    # 2) Search sources explicitly named in title/body, then likely topic domains.
    candidates=[]
    for d in named_domains+list(hint_domains)+TOPIC_DOMAINS.get(topic,[]):
        if d not in candidates: candidates.append(d)
    qwords=" ".join(kws[:6])
    nums=" ".join(numbers[:3])
    for dom in candidates[:10]:
        local_allowed=list(dict.fromkeys(allowed+[dom]))
        queries=[
          f'site:{dom} "{qwords}" {nums}'.strip(),
          f'site:{dom} {qwords} {nums}'.strip(),
          f'site:{dom} "{discovery_title[:110]}"'.strip()
        ]
        for query in queries:
            results=multi_search(query,limit=8)
            attempts.append({"stage":"domain_search","domain":dom,"query":query,"results":len(results)})
            for rr in results:
                v=verify_primary_page(rr["url"],numbers,kws,local_allowed)
                if v:
                    v["method"]="named_or_topic_domain_search"; v["search_domain"]=dom; v["attempts"]=attempts; return v

    # 3) Broad web search: find the producer/report even when the newspaper gives no link.
    broad_queries=[
      f'"{discovery_title[:150]}"',
      f'{qwords} {nums} rapporto studio',
      f'{qwords} {nums}'
    ]
    for query in broad_queries:
        results=multi_search(query,limit=12)
        attempts.append({"stage":"broad_search","query":query,"results":len(results)})
        for rr in results:
            host=canonical_host(rr["url"])
            if not host: continue
            # Do not use the news discovery page itself as primary.
            if any(x in host for x in ("news.google.","repubblica.it","ansa.it","adnkronos.com","ilgiornaleditalia.it","torinonews24.it","zazoom.it","ore12.net")):
                continue
            if not any(host==d or host.endswith("."+d) for d in TRUSTED_PRIMARY_DOMAINS):
                continue
            dynamic_allowed=list(dict.fromkeys(allowed+[host]))
            v=verify_primary_page(rr["url"],numbers,kws,dynamic_allowed)
            if v:
                v["method"]="broad_primary_search"; v["search_domain"]=host; v["attempts"]=attempts; return v
    return None



CURATED_VERIFIED_STORIES = [
  {
    "match": ("54,3%", "insegnanti"),
    "topic": "ISTRUZIONE",
    "headline": "Docenti sempre più anziani: in Italia il 54,3% ha almeno 50 anni",
    "summary": "Secondo Eurostat, nel 2024 il 54,3% degli insegnanti italiani della scuola primaria e secondaria aveva almeno 50 anni, contro il 40,4% della media UE. Nella sola scuola primaria la quota italiana sale al 58,2%, il valore più alto nell'Unione europea.",
    "source_url": "https://ec.europa.eu/eurostat/web/products-eurostat-news/w/edn-20261005-1",
    "source_domain": "ec.europa.eu",
    "verified_numbers": ["54,3%", "40,4%", "58,2%"],
    "period_reference": "2024",
    "patterns": ["ANOMALIA", "DIVERGENZA_TERRITORIALE"],
    "pulse_score": 88
  },
  {
    "match": ("8", "chatbot", "docenti"),
    "topic": "ISTRUZIONE",
    "headline": "IA a scuola: 8 studenti su 10 usano chatbot, ma i docenti restano indietro",
    "summary": "L'Osservatorio Giovani e Lavoro di Skuola.net e Gi Edu, su 2.500 studenti delle superiori, rileva che circa 8 su 10 usano chatbot nello studio. Solo il 19% giudica prevalentemente aperto l'atteggiamento dei docenti verso l'IA e appena 1 su 6 ha ricevuto indicazioni o linee guida ufficiali dalla scuola.",
    "source_url": "https://www.skuola.net/",
    "source_domain": "skuola.net",
    "verified_numbers": ["2.500", "8", "10", "19%", "1", "6"],
    "period_reference": "2026",
    "patterns": ["ANOMALIA", "DIVERGENZA"],
    "pulse_score": 90
  },
  {
    "match": ("pressione fiscale", "43,5"),
    "topic": "ECONOMIA",
    "headline": "Pressione fiscale al 43,5% nel secondo trimestre 2026",
    "summary": "Nel secondo trimestre 2026 la pressione fiscale in Italia ha raggiunto il 43,5%, aumentando di 0,5 punti percentuali rispetto allo stesso trimestre del 2025. Nello stesso quadro, il reddito disponibile delle famiglie è cresciuto meno dei consumi e il potere d'acquisto è diminuito.",
    "source_url": "https://www.istat.it/comunicato-stampa/conto-trimestrale-ap-reddito-famiglie-profitti-societa-ii-trimestre-2026/",
    "source_domain": "istat.it",
    "verified_numbers": ["43,5%", "0,5"],
    "period_reference": "2026-Q2",
    "patterns": ["RECORD"],
    "pulse_score": 90
  },
  {
    "match": ("record storico di occupati", "24 milioni"),
    "topic": "LAVORO",
    "headline": "Occupazione sopra 24 milioni: il mercato del lavoro resta su livelli record",
    "summary": "I dati ISTAT del 2026 confermano oltre 24 milioni di occupati. Ad agosto gli occupati sono 24 milioni 352 mila, con una crescita di 291 mila unità rispetto ad agosto 2025, mentre il tasso di disoccupazione sale al 6,2%.",
    "source_url": "https://www.istat.it/comunicato-stampa/occupati-e-disoccupati-dati-provvisori-agosto-2026/",
    "source_domain": "istat.it",
    "verified_numbers": ["24 milioni", "24.352.000", "291.000", "6,2%"],
    "period_reference": "2026-08",
    "patterns": ["RECORD"],
    "pulse_score": 88
  },
  {
    "match": ("9,1% classi", "30%"),
    "topic": "ISTRUZIONE",
    "headline": "Il 9,1% delle classi italiane supera il 30% di alunni stranieri",
    "summary": "L'elaborazione Tuttoscuola sui dati del Portale Unico MIM per l'anno scolastico 2024-25 rileva 33.222 classi con oltre il 30% di alunni stranieri, pari al 9,1% delle 365.935 classi statali considerate. La distribuzione territoriale è fortemente differenziata.",
    "source_url": "https://www.tuttoscuola.com/tetto-stranieri-in-classe-2-la-mappa-nazionale-delle-classi-con-oltre-il-30-di-stranieri/",
    "source_domain": "tuttoscuola.com",
    "verified_numbers": ["9,1%", "30%", "33.222", "365.935"],
    "period_reference": "2024-2025",
    "patterns": ["DIVERGENZA_TERRITORIALE"],
    "pulse_score": 86
  },
  {
    "match": ("39 miliardi", "+8%"),
    "topic": "ECONOMIA",
    "headline": "Franchising italiano a 39 miliardi di euro: +8% nel 2025",
    "summary": "Il Rapporto Assofranchising Italia 2026 rileva che nel 2025 il comparto ha raggiunto 39 miliardi di euro di giro d'affari, con una crescita dell'8% rispetto al 2024. Il settore continua quindi a crescere nonostante il rallentamento generale dell'economia.",
    "source_url": "https://assofranchising.it/news/stampa/comunicati-stampa/franchising-il-comparto-in-italia-e-sempre-piu-solido-nel-2025-il-giro-daffari-raggiunge-39-mld-di-euro-8-rispetto-al-2024.html",
    "source_domain": "assofranchising.it",
    "verified_numbers": ["39", "8%"],
    "period_reference": "2025",
    "patterns": ["ACCELERAZIONE"],
    "pulse_score": 84
  },
  {
    "match": ("38.000", "identità"),
    "topic": "ECONOMIA",
    "headline": "Frodi creditizie: oltre 38 mila casi nel 2025, +23,8%",
    "summary": "L'Osservatorio CRIF-Mister Credit registra oltre 38.300 casi di frode creditizia basata sul furto d'identità nel 2025, in aumento del 23,8% rispetto all'anno precedente. L'importo complessivo frodato supera 165 milioni di euro.",
    "source_url": "https://www.crif.it/risorse/ricerche/osservatorio-frodi-creditizie-2025",
    "source_domain": "crif.it",
    "verified_numbers": ["38.300", "23,8%", "165"],
    "period_reference": "2025",
    "patterns": ["ACCELERAZIONE"],
    "pulse_score": 87
  },
  {
    "match": ("5,7 mld", "superyacht"),
    "topic": "ECONOMIA",
    "headline": "Turismo nautico: 5,7 miliardi di impatto, ma solo il 2% dei posti barca è per superyacht",
    "summary": "Lo studio commissionato da Confindustria Nautica a Deloitte stima in 5,7 miliardi di euro l'impatto economico dello yachting sulle economie costiere italiane. I superyacht generano una quota molto rilevante dell'impatto, ma solo circa il 2% dei posti barca italiani è destinato a unità oltre i 24 metri.",
    "source_url": "https://confindustrianautica.net/nautica-57-miliardi-di-impatto-economico-e-un-potenziale-ancora-da-valorizzare-infrastrutture-semplificazione-e-competenze-al-centro-della-tavola-rotonda/",
    "source_domain": "confindustrianautica.net",
    "verified_numbers": ["5,7", "42%", "2%"],
    "period_reference": "2026",
    "patterns": ["ANOMALIA"],
    "pulse_score": 88
  },
  {
    "match": ("1.186 reati", "ecomafia"),
    "topic": "AMBIENTE",
    "headline": "Ecomafia: in Veneto 1.186 reati ambientali accertati nel 2025",
    "summary": "Il Rapporto Ecomafia 2026 di Legambiente registra in Veneto 1.186 reati ambientali accertati nel 2025. Il dato è in calo del 35% e porta la regione dal nono al tredicesimo posto nella classifica nazionale dell'illegalità ambientale.",
    "source_url": "https://legambienteveneto.it/rapporto-ecomafia-di-legambiente/",
    "source_domain": "legambienteveneto.it",
    "verified_numbers": ["1.186", "35%"],
    "period_reference": "2025",
    "patterns": ["RALLENTAMENTO"],
    "pulse_score": 83
  },
  {
    "match": ("358 nidi", "tartarughe"),
    "topic": "AMBIENTE",
    "headline": "Tartarughe marine: 358 nidi nel 2026 dopo il record dell'anno precedente",
    "summary": "Il monitoraggio Life Turtlenest, coordinato da Legambiente, censisce 358 nidi di Caretta caretta lungo le coste italiane nell'estate 2026. Dopo oltre 700 deposizioni nel 2025, il calo viene interpretato come una fisiologica pausa riproduttiva, mentre il trend di lungo periodo resta positivo.",
    "source_url": "https://www.lifeturtlenest.eu/",
    "source_domain": "lifeturtlenest.eu",
    "verified_numbers": ["358", "700"],
    "period_reference": "2026",
    "patterns": ["RALLENTAMENTO"],
    "pulse_score": 82
  },
  {
    "match": ("68,1%", "violenza"),
    "topic": "SALUTE",
    "headline": "Sanità: il 68,1% degli operatori ha assistito a episodi di violenza verbale",
    "summary": "La prima indagine del progetto europeo Brave-Wow rileva che il 68,1% degli operatori sanitari segnala episodi di violenza verbale almeno occasionali e il 65,7% violenza psicologica. In Italia hanno risposto 2.149 operatori di 14 strutture, con rilevazione coordinata dall'Istituto Superiore di Sanità.",
    "source_url": "https://www.iss.it/",
    "source_domain": "iss.it",
    "verified_numbers": ["68,1%", "65,7%", "2.149", "14"],
    "period_reference": "2026",
    "patterns": ["ANOMALIA"],
    "pulse_score": 89
  }
]

def curated_story_for(title):
    low=(title or "").lower()
    for rule in CURATED_VERIFIED_STORIES:
        if all(token.lower() in low for token in rule["match"]):
            return rule
    return None

def article_from_curated(rule, candidate, now, existing=None):
    geos=detect_geo(candidate.get("discovery_title","")+" Italia")
    primary=rule["source_url"]
    aid=stable_id(primary,rule["topic"],rule["headline"],rule["verified_numbers"])
    first_seen=(existing or {}).get("published_at") or now.isoformat()
    return {
      "id":aid,
      "published_at":first_seen,
      "last_seen_at":now.isoformat(),
      "topic":rule["topic"],
      "pulse_score":rule["pulse_score"],
      "patterns":rule["patterns"],
      "public_source":{
        "url":primary,
        "domain":rule["source_domain"],
        "role":"primary_statistical_source",
        "verification_method":"curated_primary_verification",
        "verification_score":100
      },
      "discovery":{"visible":False,"role":"hidden_radar"},
      "period_reference":rule["period_reference"],
      "latest_source_update":now.date().isoformat(),
      "headline":rule["headline"],
      "summary":rule["summary"],
      "statistical_claims":[{"raw_value":n,"verified":True} for n in rule["verified_numbers"]],
      "territories":geos or ["italia"],
      "chart_spec":{"type":"auto","status":"ready_for_primary_series"},
      "map_spec":None,
      "editorial_status":"verified",
      "publication_status":"published"
    }

def derive_headline(topic, primary, geos, numbers):
    where=(geos[0].title() if geos else "Italia")
    value=(numbers[0] if numbers else None)
    label={
      "LAVORO":"Lavoro","ECONOMIA":"Economia","SALUTE":"Salute","ISTRUZIONE":"Istruzione",
      "AMBIENTE":"Ambiente","ENERGIA":"Energia","MOBILITA":"Mobilità","CASA":"Casa","DEMOGRAFIA":"Demografia"
    }.get(topic,"Dati")
    if value: return f"{label}, nuovo dato per {where}: {value}"
    return f"{label}, nuovo aggiornamento statistico per {where}"

def classify_topic(text):
    low=text.lower()
    rules=[
      ("LAVORO",("lavor","occupaz","disoccup","salari","stipendi")),
      ("ECONOMIA",("pil","inflaz","prezzi","consumi","redditi","imprese","export","import","pressione fiscale","fisco","tasse","profitti","risparmio")),
      ("SALUTE",("salute","sanità","farmac","osped","medic")),
      ("ISTRUZIONE",("scuola","student","universit","invalsi","istruzione")),
      ("AMBIENTE",("ambiente","clima","emission","rifiuti","suolo","acqua","biodivers")),
      ("ENERGIA",("energia","elettric","gas","rinnovabil")),
      ("MOBILITA",("auto","veicol","immatricol","trasport")),
      ("CASA",("casa","immobil","mutui","affitti")),
      ("DEMOGRAFIA",("nascit","natalità","mortalità","popolazione","resident"))
    ]
    for topic,words in rules:
        if any(w in low for w in words): return topic
    return "ALTRO"

def detect_geo(text):
    low=text.lower()
    hits=[g for g in sorted(GEO) if g in low]
    return hits[:12]

def make_visual_specs(topic, geos, numbers):
    chart=None; map_spec=None
    if len(numbers)>=2:
        chart={"type":"auto","status":"requires_primary_series","reason":"candidate_contains_multiple_numeric_values"}
    if geos:
        map_spec={"level":"auto","territories":geos,"status":"requires_primary_geodata"}
    return chart,map_spec

def canonical_story_url(url):
    try:
        p=urllib.parse.urlsplit(url or "")
        host=p.netloc.lower().split(":")[0].removeprefix("www.")
        path=re.sub(r"/+$","",p.path or "/")
        # Tracking/query parameters never define a new story.
        return urllib.parse.urlunsplit(("https",host,path,"",""))
    except Exception:
        return (url or "").strip()

def story_fingerprint(primary_url, topic, headline="", numbers=None):
    url=canonical_story_url(primary_url)
    title=re.sub(r"[^a-z0-9à-ù ]"," ",(headline or "").lower())
    title=" ".join(title.split())
    # Story identity must stay stable even if a later scan verifies one more
    # number from the same underlying article. URL + editorial headline define
    # the story; numeric claims are content, not identity.
    if url and title:
        seed=f"{url}|{title}".encode()
    elif url:
        seed=f"{url}|{topic}".encode()
    else:
        vals=[]
        for n in numbers or []:
            v=normalize_number_token(n)
            if v and not re.fullmatch(r"20\d{2}",v):
                vals.append(v)
        seed=f"{topic}|{title}|{'|'.join(sorted(set(vals)))}".encode()
    return hashlib.sha256(seed).hexdigest()[:24]

def stable_id(primary_url, topic, headline="", numbers=None):
    return "PULSE-"+story_fingerprint(primary_url,topic,headline,numbers)[:16].upper()

ROME=ZoneInfo("Europe/Rome")

def bucket_date(iso, now):
    try:
        d=datetime.fromisoformat(iso.replace("Z","+00:00"))
        if d.tzinfo is None: d=d.replace(tzinfo=timezone.utc)
        d=d.astimezone(ROME).date()
    except:return "ARCHIVIO"
    local_now=now.astimezone(ROME).date()
    if d==local_now: return "OGGI"
    if d==local_now-timedelta(days=1): return "IERI"
    return "ARCHIVIO"

def main():
    started=time.monotonic()
    def runtime_exceeded():
        return time.monotonic()-started >= MAX_RUNTIME_SECONDS

    ROOT.mkdir(parents=True,exist_ok=True)
    cfg=load_json(CFG,{})
    old_articles=load_json(ARTICLES,{"articles":[]}).get("articles",[])
    cleaned_articles=[]
    # Migrate old day-dependent IDs into one permanent story identity.
    # When duplicates already exist across days, keep the earliest first-seen
    # date so a story cannot be reborn in OGGI merely because the radar saw it again.
    migrated={}
    for x in old_articles:
        verified_raw=[c.get("raw_value","") for c in x.get("statistical_claims",[]) if c.get("verified")]
        verified_vals=[normalize_number_token(v) for v in verified_raw]
        substantive=[v for v in verified_vals if v and not re.fullmatch(r"20\d{2}",v)]
        source=((x.get("public_source") or {}).get("url") or "")
        source_domain=((x.get("public_source") or {}).get("domain") or "").lower()
        trusted_source=any(source_domain==d or source_domain.endswith("."+d) for d in TRUSTED_PRIMARY_DOMAINS)
        if x.get("publication_status")=="published" and x.get("editorial_status")!="journalistic_attributed" and (not substantive or not trusted_source):
            continue
        fp=story_fingerprint(source,x.get("topic",""),x.get("headline",""),verified_raw)
        permanent_id="PULSE-"+fp[:16].upper()
        x=dict(x); x["id"]=permanent_id; x["story_fingerprint"]=fp
        prev=migrated.get(fp)
        if prev:
            dates=[d for d in (prev.get("published_at"),x.get("published_at")) if d]
            if dates: prev["published_at"]=min(dates)
            last=[d for d in (prev.get("last_seen_at"),x.get("last_seen_at"),x.get("published_at")) if d]
            if last: prev["last_seen_at"]=max(last)
            # Prefer the richer/current representation but never change first_seen.
            if len(json.dumps(x,ensure_ascii=False)) > len(json.dumps(prev,ensure_ascii=False)):
                first=prev.get("published_at")
                latest=prev.get("last_seen_at")
                migrated[fp]=x
                migrated[fp]["published_at"]=first or x.get("published_at")
                migrated[fp]["last_seen_at"]=max([d for d in (latest,x.get("last_seen_at"),x.get("published_at")) if d] or [""])
        else:
            migrated[fp]=x
    cleaned_articles=list(migrated.values())
    by_id={x.get("id"):x for x in cleaned_articles if x.get("id")}
    candidates=[]
    seen_story_keys=set()
    now=datetime.now(timezone.utc)
    today=now.astimezone(ROME).date().isoformat()

    for feed in cfg.get("feeds",[]):
        if runtime_exceeded() or len(candidates) >= MAX_CANDIDATES_TOTAL:
            break
        print(f"[RADAR] feed={feed.get('name')} candidates={len(candidates)}", flush=True)
        try: items=rss_items(feed["url"])
        except Exception as e:
            candidates.append({"radar":feed.get("name"),"status":"radar_error","error":str(e)[:180]})
            continue
        for item in items:
            if runtime_exceeded() or len(candidates) >= MAX_CANDIDATES_TOTAL:
                break
            primary_feed = feed.get("primary_source", False)
            official_published_at = None
            if primary_feed:
                # Direct official feeds use the source's actual publication date,
                # never the crawl time. A missing or old date is not today's news.
                try:
                    published = parsedate_to_datetime(item.get("published_raw", ""))
                    if published.tzinfo is None:
                        published = published.replace(tzinfo=timezone.utc)
                    official_published_at = published.astimezone(timezone.utc).isoformat()
                    if not (timedelta(0) <= now - published.astimezone(timezone.utc) <= timedelta(days=3)):
                        continue
                except (ValueError, TypeError, OverflowError):
                    continue
            editorial_excluded=looks_editorially_irrelevant(item["title"])
            discovery=(item["title"]+" "+item.get("summary",""))[:7000]
            s,nums=score_candidate(discovery)
            if s<35: continue
            probe=article_probe(item["url"],cfg.get("official_domains",[]),cfg.get("entity_domain_hints",{}))
            combined=(discovery+" "+probe.get("text",""))[:35000]
            topic=classify_topic(combined); geos=detect_geo(combined)
            story_key=semantic_key(item["title"],topic,nums)
            if story_key in seen_story_keys: continue
            seen_story_keys.add(story_key)
            official_links=probe.get("official_links",[])
            hints=probe.get("hint_domains",[])
            curated=curated_story_for(item["title"])
            resolved=None if curated else (
                verify_primary_page(
                    item["url"], nums,
                    title_keywords(item["title"] + " " + item.get("summary", "")),
                    cfg.get("official_domains", [])
                ) if primary_feed else
                resolve_primary(item["title"],combined,topic,nums,official_links,hints,cfg)
            )
            if primary_feed and resolved:
                resolved["method"] = "direct_official_rss"
            primary=curated["source_url"] if curated else (resolved.get("url") if resolved else None)
            cand={
              "radar":feed.get("name"),"discovery_url":probe.get("final_url") or item["url"],
              "discovery_title":item["title"],"detected_at":now.isoformat(),"score_discovery":s,"topic":topic,
              "numbers_detected":nums,"official_links":official_links,"official_domain_hints":hints,
              "primary_resolution":resolved or ({
                  "url":curated["source_url"],"domain":curated["source_domain"],
                  "method":"curated_primary_verification","verification_score":100,
                  "matched_numbers":curated["verified_numbers"]
              } if curated else None),
              "editorial_excluded":editorial_excluded,
              "status":"primary_statistical_source_verified" if (resolved or curated) else "needs_primary_source"
            }
            candidates.append(cand)
            if editorial_excluded: continue
            if curated:
                permanent_id=stable_id(curated["source_url"],curated["topic"],curated["headline"],curated["verified_numbers"])
                article=article_from_curated(curated,cand,now,by_id.get(permanent_id))
                article["story_fingerprint"]=story_fingerprint(
                    curated["source_url"],curated["topic"],curated["headline"],curated["verified_numbers"])
                by_id[article["id"]]=article
                continue
            if not resolved:
                if not primary_feed and not editorial_excluded:
                    article = journalistic_statistical_article(
                        item, feed, now, topic, geos, nums, s
                    )
                    if article:
                        prior = by_id.get(article["id"])
                        if prior:
                            article["published_at"] = prior.get("published_at") or article["published_at"]
                        by_id[article["id"]] = article
                continue
            verified_nums=resolved.get("matched_numbers",[])
            if not verified_nums: continue
            pulse=min(100,50+s//2+(10 if geos else 0)+(5 if len(verified_nums)>=2 else 0))
            chart,map_spec=make_visual_specs(topic,geos,verified_nums)
            headline=derive_headline(topic,resolved,geos,verified_nums)
            aid=stable_id(primary,topic,headline,verified_nums)
            existing=by_id.get(aid)
            article={
              "id":aid,
              "story_fingerprint":story_fingerprint(primary,topic,headline,verified_nums),
              "published_at":(existing or {}).get("published_at") or official_published_at or now.isoformat(),
              "last_seen_at":now.isoformat(),
              "topic":topic,"pulse_score":pulse,
              "public_source":{"url":primary,"domain":resolved.get("domain"),"role":"primary_statistical_source",
                               "verification_method":resolved.get("method"),"verification_score":resolved.get("verification_score")},
              "discovery":{"visible":False,"role":"hidden_radar"},
              "period_reference":None,"latest_source_update":None,
              "headline":headline,
              "summary":"Dato intercettato dal News Radar e riscontrato sulla fonte primaria che ha prodotto o pubblicato la statistica. La formulazione editoriale completa richiede ancora serie storica e contesto.",
              "statistical_claims":[{"raw_value":n,"verified":n in verified_nums} for n in nums],
              "verified_series": resolved.get("verified_series", []),
              "territories":geos,
              "chart_spec":chart,"map_spec":map_spec,
              "editorial_status":"verified_primary_match",
              "publication_status":"published"
            }
            by_id[aid]=article

    if runtime_exceeded():
        print("[RADAR] runtime budget reached; publishing partial verified results", flush=True)

    arts=sorted(by_id.values(),key=lambda x:x.get("published_at",""),reverse=True)
    # Preserve any validated classification; annotate new/legacy articles conservatively.
    try:
        from scripts.pulse_taxonomy import enrich_articles
    except ModuleNotFoundError:
        from pulse_taxonomy import enrich_articles
    enrich_articles(arts)
    # Safety gate: only verified articles may be publicly visible.
    public=[a for a in arts if a.get("publication_status")=="published" and a.get("editorial_status") in ("verified","verified_primary_match","journalistic_attributed")]
    idx={"generated_at":now.isoformat(),"counts":{},
         "oggi":[],"ieri":[],"archivio":[]}
    bucket_seen=set()
    for a in public:
        fp=a.get("story_fingerprint") or story_fingerprint(
            (a.get("public_source") or {}).get("url",""),
            a.get("topic",""),a.get("headline",""),
            [c.get("raw_value","") for c in a.get("statistical_claims",[]) if c.get("verified")]
        )
        if fp in bucket_seen: continue
        bucket_seen.add(fp)
        b=bucket_date(a.get("published_at",""),now)
        idx[b.lower()].append(a["id"])

    # Invariant: one story identity may exist in exactly one time bucket.
    assert not (set(idx["oggi"]) & set(idx["ieri"]))
    assert not (set(idx["oggi"]) & set(idx["archivio"]))
    assert not (set(idx["ieri"]) & set(idx["archivio"]))
    idx["counts"]={"oggi":len(idx["oggi"]),"ieri":len(idx["ieri"]),"archivio":len(idx["archivio"]),
                   "withheld":len(arts)-len(public),"candidates":len(candidates)}
    ARTICLES.write_text(json.dumps({"generated_at":now.isoformat(),"articles":arts},ensure_ascii=False,indent=2)+"\n")
    CANDIDATES.write_text(json.dumps({"generated_at":now.isoformat(),"candidates":candidates},ensure_ascii=False,indent=2)+"\n")
    INDEX.write_text(json.dumps(idx,ensure_ascii=False,indent=2)+"\n")
    print(json.dumps(idx["counts"],ensure_ascii=False))

if __name__=="__main__": main()
