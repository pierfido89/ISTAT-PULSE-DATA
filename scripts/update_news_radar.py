#!/usr/bin/env python3
from __future__ import annotations
import hashlib, html, json, re, time, urllib.parse, urllib.request
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta, timezone
from pathlib import Path
from bs4 import BeautifulSoup

ROOT=Path("data/news")
CFG=Path("data/news_radar_sources.json")
ARTICLES=ROOT/"articles.json"
CANDIDATES=ROOT/"candidates.json"
INDEX=ROOT/"index.json"
UA="Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 Chrome/154 Safari/537.36 ISTAT-PULSE-NewsRadar/1.1"

TOPIC_DOMAINS={
 "LAVORO":["istat.it","inps.it","inail.it","unioncamere.gov.it"],
 "ECONOMIA":["istat.it","bancaditalia.it","mef.gov.it","unioncamere.gov.it"],
 "SALUTE":["salute.gov.it","iss.it","agenas.gov.it","aifa.gov.it"],
 "ISTRUZIONE":["invalsi.it","istruzione.it","istat.it","mur.gov.it"],
 "AMBIENTE":["isprambiente.gov.it","istat.it","eea.europa.eu"],
 "ENERGIA":["terna.it","gse.it","arera.it","istat.it"],
 "MOBILITA":["aci.it","unrae.it","anfia.it","istat.it"],
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

def fetch(url, timeout=25, max_bytes=700000):
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
    return out[:60]

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
        raw,final,ct=fetch(url,timeout=18,max_bytes=500000)
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
        raw,_,_=fetch(url,timeout=20,max_bytes=600000)
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

def verify_primary_page(url, numbers, keywords, allowed_domains):
    host=canonical_host(url)
    dom=official_domain(host,allowed_domains)
    if not dom: return None
    try:
        raw,final,ct=fetch(url,timeout=20,max_bytes=900000)
        if "html" not in ct.lower() and "text" not in ct.lower() and "json" not in ct.lower():
            return None
        text=clean_text(raw.decode("utf-8","ignore"))[:60000]
        low=text.lower()
        matched_numbers=[]
        for n in numbers:
            nn=normalize_number_token(n)
            if len(nn)>=1 and (nn in low or nn.replace(",",".") in low or nn.replace(".",",") in low):
                matched_numbers.append(n)
        matched_keywords=[k for k in keywords if k in low]
        score=(35 if matched_numbers else 0)+min(40,len(matched_keywords)*8)+(15 if dom else 0)
        if score<50: return None
        return {"url":final,"domain":dom,"matched_numbers":matched_numbers[:6],
                "matched_keywords":matched_keywords[:8],"verification_score":min(100,score),
                "text_excerpt":text[:900]}
    except Exception:
        return None


PRIMARY_ENTITY_PATTERNS=[
 ("istat","istat.it"),
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
 ("unrae","unrae.it")
]

def extract_named_primary_domains(text):
    low=(text or "").lower()
    out=[]
    for name,dom in PRIMARY_ENTITY_PATTERNS:
        if name in low and dom not in out: out.append(dom)
    return out

def looks_editorially_irrelevant(title):
    low=(title or "").lower()
    bad=("pronostico","quote e statistiche","scommesse","oddschecker","calendario partite",
         "ospita","evento","festival","dal 2027/28 limite","decreto scuola")
    return any(x in low for x in bad)

def semantic_key(title, topic, numbers):
    clean=re.sub(r"[^a-z0-9à-ù ]"," ",(title or "").lower())
    words=[w for w in clean.split() if len(w)>=4 and w not in {"italia","dati","statistiche","rapporto","news"}]
    core=" ".join(sorted(set(words[:8])))
    nums="|".join(sorted(set(normalize_number_token(n) for n in numbers if normalize_number_token(n))))
    return hashlib.sha256(f"{topic}|{core}|{nums}".encode()).hexdigest()[:20]

def resolve_primary(discovery_title, discovery_text, topic, numbers, direct_links, hint_domains, cfg):
    domains=cfg.get("official_domains",[])
    kws=title_keywords(discovery_title+" "+discovery_text[:1500])
    # 1) direct official links from the article
    for u in direct_links:
        v=verify_primary_page(u,numbers,kws,domains)
        if v:
            v["method"]="direct_official_link"; return v
    # 2) domains inferred from named entities + topic
    candidates=[]
    named_domains=extract_named_primary_domains(discovery_title+" "+discovery_text[:4000])
    for d in named_domains+list(hint_domains)+TOPIC_DOMAINS.get(topic,[]):
        if d not in candidates: candidates.append(d)
    qwords=" ".join(kws[:5])
    nums=" ".join(numbers[:2])
    for dom in candidates[:8]:
        query=f'site:{dom} "{qwords}" {nums}'.strip()
        results=ddg_search(query,limit=4)
        if not results and qwords:
            results=ddg_search(f"site:{dom} {qwords}",limit=4)
        for rr in results:
            v=verify_primary_page(rr["url"],numbers,kws,domains)
            if v:
                v["method"]="official_domain_search"; v["search_domain"]=dom; return v
    return None

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

def stable_id(primary_url, topic, day):
    seed=f"{primary_url}|{topic}|{day}".encode()
    return "PULSE-"+hashlib.sha256(seed).hexdigest()[:16].upper()

def bucket_date(iso, now):
    try:d=datetime.fromisoformat(iso.replace("Z","+00:00")).date()
    except:return "ARCHIVIO"
    if d==now.date(): return "OGGI"
    if d==now.date()-timedelta(days=1): return "IERI"
    return "ARCHIVIO"

def main():
    ROOT.mkdir(parents=True,exist_ok=True)
    cfg=load_json(CFG,{})
    old_articles=load_json(ARTICLES,{"articles":[]}).get("articles",[])
    by_id={x.get("id"):x for x in old_articles if x.get("id")}
    candidates=[]
    seen_story_keys=set()
    now=datetime.now(timezone.utc)
    today=now.date().isoformat()

    for feed in cfg.get("feeds",[]):
        try: items=rss_items(feed["url"])
        except Exception as e:
            candidates.append({"radar":feed.get("name"),"status":"radar_error","error":str(e)[:180]})
            continue
        for item in items:
            if looks_editorially_irrelevant(item["title"]): continue
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
            resolved=resolve_primary(item["title"],combined,topic,nums,official_links,hints,cfg)
            primary=resolved.get("url") if resolved else None
            cand={
              "radar":feed.get("name"),"discovery_url":probe.get("final_url") or item["url"],
              "discovery_title":item["title"],"detected_at":now.isoformat(),"score_discovery":s,"topic":topic,
              "numbers_detected":nums,"official_links":official_links,"official_domain_hints":hints,
              "primary_resolution":resolved,
              "status":"primary_statistical_source_verified" if resolved else "needs_primary_source"
            }
            candidates.append(cand)
            if not resolved: continue
            verified_nums=resolved.get("matched_numbers",[])
            if not verified_nums: continue
            pulse=min(100,50+s//2+(10 if geos else 0)+(5 if len(verified_nums)>=2 else 0))
            chart,map_spec=make_visual_specs(topic,geos,verified_nums)
            aid=stable_id(primary,topic,today)
            headline=derive_headline(topic,resolved,geos,verified_nums)
            article={
              "id":aid,"published_at":now.isoformat(),"topic":topic,"pulse_score":pulse,
              "public_source":{"url":primary,"domain":resolved.get("domain"),"role":"primary_statistical_source",
                               "verification_method":resolved.get("method"),"verification_score":resolved.get("verification_score")},
              "discovery":{"visible":False,"role":"hidden_radar"},
              "period_reference":None,"latest_source_update":None,
              "headline":headline,
              "summary":"Dato intercettato dal News Radar e riscontrato sulla fonte primaria che ha prodotto o pubblicato la statistica. La formulazione editoriale completa richiede ancora serie storica e contesto.",
              "statistical_claims":[{"raw_value":n,"verified":n in verified_nums} for n in nums],
              "territories":geos,
              "chart_spec":chart,"map_spec":map_spec,
              "editorial_status":"verified_primary_match",
              "publication_status":"published"
            }
            if aid not in by_id or by_id[aid].get("publication_status")!="published": by_id[aid]=article

    arts=sorted(by_id.values(),key=lambda x:x.get("published_at",""),reverse=True)
    # Safety gate: only verified articles may be publicly visible.
    public=[a for a in arts if a.get("publication_status")=="published" and a.get("editorial_status") in ("verified","verified_primary_match")]
    idx={"generated_at":now.isoformat(),"counts":{},
         "oggi":[],"ieri":[],"archivio":[]}
    for a in public:
        b=bucket_date(a.get("published_at",""),now)
        idx[b.lower()].append(a["id"])
    idx["counts"]={"oggi":len(idx["oggi"]),"ieri":len(idx["ieri"]),"archivio":len(idx["archivio"]),
                   "withheld":len(arts)-len(public),"candidates":len(candidates)}
    ARTICLES.write_text(json.dumps({"generated_at":now.isoformat(),"articles":arts},ensure_ascii=False,indent=2)+"\n")
    CANDIDATES.write_text(json.dumps({"generated_at":now.isoformat(),"candidates":candidates},ensure_ascii=False,indent=2)+"\n")
    INDEX.write_text(json.dumps(idx,ensure_ascii=False,indent=2)+"\n")
    print(json.dumps(idx["counts"],ensure_ascii=False))

if __name__=="__main__": main()
