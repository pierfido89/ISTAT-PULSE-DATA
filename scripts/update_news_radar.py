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
UA="ISTAT-PULSE-NewsRadar/1.0"

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
    nums=re.findall(r"(?<!\w)[+-]?\d{1,3}(?:[\.,]\d+)?\s*(?:%|milioni|miliardi|mila)?",low)
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

def classify_topic(text):
    low=text.lower()
    rules=[
      ("LAVORO",("lavor","occupaz","disoccup","salari","stipendi")),
      ("ECONOMIA",("pil","inflaz","prezzi","consumi","redditi","imprese","export","import")),
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
    now=datetime.now(timezone.utc)
    today=now.date().isoformat()

    for feed in cfg.get("feeds",[]):
        try: items=rss_items(feed["url"])
        except Exception as e:
            candidates.append({"radar":feed.get("name"),"status":"radar_error","error":str(e)[:180]})
            continue
        for item in items:
            discovery=(item["title"]+" "+item.get("summary",""))[:7000]
            s,nums=score_candidate(discovery)
            if s<35: continue
            probe=article_probe(item["url"],cfg.get("official_domains",[]),cfg.get("entity_domain_hints",{}))
            combined=(discovery+" "+probe.get("text",""))[:35000]
            topic=classify_topic(combined); geos=detect_geo(combined)
            official_links=probe.get("official_links",[])
            hints=probe.get("hint_domains",[])
            primary=official_links[0] if official_links else None
            cand={
              "radar":feed.get("name"),"discovery_url":probe.get("final_url") or item["url"],
              "detected_at":now.isoformat(),"score_discovery":s,"topic":topic,
              "numbers_detected":nums,"official_links":official_links,"official_domain_hints":hints,
              "status":"primary_found" if primary else "needs_primary_source"
            }
            candidates.append(cand)
            if not primary: continue
            pulse=min(100,45+s//2+(10 if geos else 0)+(5 if len(nums)>=2 else 0))
            chart,map_spec=make_visual_specs(topic,geos,nums)
            aid=stable_id(primary,topic,today)
            article={
              "id":aid,"published_at":now.isoformat(),"topic":topic,"pulse_score":pulse,
              "public_source":{"url":primary,"domain":canonical_host(primary),"role":"primary_official"},
              "discovery":{"visible":False,"role":"hidden_radar"},
              "period_reference":None,"latest_source_update":None,
              "headline":None,
              "summary":None,
              "statistical_claims":[{"raw_value":n,"verified":False} for n in nums],
              "territories":geos,
              "chart_spec":chart,"map_spec":map_spec,
              "editorial_status":"needs_primary_fact_verification",
              "publication_status":"withheld"
            }
            if aid not in by_id: by_id[aid]=article

    arts=sorted(by_id.values(),key=lambda x:x.get("published_at",""),reverse=True)
    # Safety gate: only verified articles may be publicly visible.
    public=[a for a in arts if a.get("publication_status")=="published" and a.get("editorial_status")=="verified"]
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
