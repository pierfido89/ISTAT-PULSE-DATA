#!/usr/bin/env python3
"""Twelve PULSE source connectors: official-origin publications, fail-closed.

This is NOT a numeric fact extractor. It discovers attributable publications
or dataset catalog entries; numerical statements require separate evidence QA.
It never counts a webpage as verified just because it returns HTTP 200.
"""
from __future__ import annotations
import argparse
import hashlib
import json
import os
import re
import sys
from datetime import date, datetime, timezone
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError
from pathlib import Path
from urllib.parse import urljoin, urlsplit, urlunsplit
from bs4 import BeautifulSoup
import requests

ROOT = Path(__file__).resolve().parents[1]
REGISTRY = ROOT / 'data/observer_sources_12_registry.json'
STATUS = ROOT / 'data/observer_sources_12_status.json'
OUT = ROOT / 'data/observer_articles_12.json'
ALLOWED_EXT = ('.pdf', '.csv', '.xls', '.xlsx', '.zip', '.json', '.xml', '.ods')
PUBLISHED_EXT = ('.pdf', '.xls', '.xlsx', '.csv', '.zip')
UA = 'PULSE-official-observer-probe/1.0 (+https://github.com/pierfido89/ISTAT-PULSE-DATA)'
MONTHS = {'gennaio':1,'febbraio':2,'marzo':3,'aprile':4,'maggio':5,'giugno':6,
          'luglio':7,'agosto':8,'settembre':9,'ottobre':10,'novembre':11,'dicembre':12,
          'gen':1,'feb':2,'mar':3,'apr':4,'mag':5,'giu':6,'lug':7,'ago':8,'set':9,'ott':10,'nov':11,'dic':12}
DATE_NUMERIC = re.compile(r'(?<!\d)([0-3]?\d)[/.-]([01]?\d)[/.-](20\d{2})(?!\d)')
DATE_WORD = re.compile(r'(?<!\d)([0-3]?\d)\s+('+'|'.join(MONTHS)+r')\s+(20\d{2})(?!\d)', re.I)
ISO = re.compile(r'\b(20\d{2})-([01]\d)-([0-3]\d)\b')
TITLE_REJECT = {'download','scarica','scopri','scopri di più','leggi','visualizza','pdf','csv','xlsx','vai alla sezione','vai','continua','more','read more'}


def official_url(candidate: str, domain: str) -> bool:
    try:
        parsed = urlsplit(candidate)
        host = (parsed.hostname or '').lower().removeprefix('www.')
        return parsed.scheme == 'https' and (host == domain or host.endswith('.' + domain)) and not (parsed.username or parsed.password)
    except ValueError:
        return False


def safe_link(base: str, href: str, domain: str) -> str | None:
    href = (href or '').strip()
    if not href or href.startswith(('#','javascript:','data:','mailto:','tel:')):
        return None
    url = urljoin(base, href)
    parts = urlsplit(url)
    canonical = urlunsplit((parts.scheme, parts.netloc, parts.path, parts.query, ''))
    return canonical if official_url(canonical, domain) else None


def today_in_rome() -> date:
    """Current Rome date; safe UTC fallback if Python Windows has no tzdata.

    Near local midnight, UTC may be a day behind Rome: temporarily omitting
    a valid record is safer than inventing an unverified future date.
    """
    try:
        return datetime.now(ZoneInfo("Europe/Rome")).date()
    except ZoneInfoNotFoundError:
        return datetime.now(timezone.utc).date()


def parse_date(raw: str, *, today: date | None = None) -> str | None:
    if not raw:
        return None
    if today is None:
        today = today_in_rome()
    match = ISO.search(raw)
    if match:
        parts = tuple(map(int, match.groups()))
    else:
        match = DATE_NUMERIC.search(raw)
        if match:
            d,m,y = map(int,match.groups());parts = (y,m,d)
        else:
            match = DATE_WORD.search(raw.lower())
            if not match: return None
            d,month,y = match.groups();parts = (int(y),MONTHS[month.lower()],int(d))
    try: found = date(*parts)
    except ValueError: return None
    if found.year < 2026 or found > today: return None
    return found.isoformat()


def explicit_date(element, *, today: date | None = None) -> str | None:
    # Never pull an unrelated page's date or the crawler's current time.
    for time_tag in element.select('time[datetime],time,meta[itemprop="datePublished"]'):
        value = time_tag.get('datetime') or time_tag.get('content') or time_tag.get_text(' ',strip=True)
        parsed = parse_date(value,today=today)
        if parsed: return parsed
    # Parent card may contain an explicit publication date in its visible text.
    return parse_date(element.get_text(' ',strip=True),today=today)


def clean_title(anchor, card, source) -> str:
    title = anchor.get_text(' ',strip=True)
    if title.lower() in TITLE_REJECT or len(title) < 16:
        for head in card.select('h2,h3,h4,h5,[class*="title"],[class*="heading"]'):
            candidate = head.get_text(' ',strip=True)
            if len(candidate) >= 16 and candidate.lower() not in TITLE_REJECT:
                title=candidate;break
    # Never use an invented title or the generic "Scarica" label as a publication.
    return re.sub(r'\s+', ' ',title).strip()[:230] if 16 <= len(title.strip()) <= 320 else ''


def candidate_card(anchor):
    # Nearest small editorial card. Avoid body/main because its date might
    # refer to an entirely different publication elsewhere on the page.
    for parent in anchor.parents:
        if not getattr(parent,'name',None): continue
        if parent.name in ('article','li'):
            return parent
        klass=' '.join(parent.get('class',[])).lower()
        if any(c in klass for c in ('card','result','news-item','document-item','list-item','publication')):
            if len(parent.get_text(' ',strip=True)) < 2200: return parent
        if parent.name in ('main','body','html'): break
    return anchor.parent


def entries_from_html(html: str, base: str, source: dict, *,today:date|None=None) -> list[dict]:
    soup = BeautifulSoup(html,'html.parser')
    seen: dict[str,dict] = {}
    for anchor in soup.select('a[href]'):
        url=safe_link(base,anchor.get('href',''),source['domain'])
        if not url: continue
        path=urlsplit(url).path.lower()
        if path.rstrip('/') == urlsplit(base).path.rstrip('/'): continue
        if any(v in path for v in ('/privacy','/cookie','/contatti','/contact','/login','/accesso','/register','/iscriviti')): continue
        card=candidate_card(anchor)
        title=clean_title(anchor,card,source)
        if not title or title.lower() in TITLE_REJECT:continue
        words=(title+' '+path).lower()
        extension=path.endswith(ALLOWED_EXT)
        if not extension and not any(word in words for word in source.get('keywords',[])):continue
        date_str=explicit_date(card,today=today)
        if not date_str:
            # Keep only as a discoverable URL, never fabricate published_at.
            continue
        # No blanket publication claim: datasets are catalog discoveries, not
        # verified time-series or automatically written news articles.
        ref_type='dataset_catalog' if source['type']=='datasets' else 'official_publication'
        key=hashlib.sha256((source['id']+'|'+url).encode('utf8')).hexdigest()[:18].upper()
        entry={'id':'PULSE-OBS12-'+key,'observer':source['name'],
               'published_at':date_str,
               'topic':'ALTRO', 'headline':title,
               'summary':(f"Scheda dataset dell'ente {source['name']} (data rilevata nel catalogo, da verificare se data di pubblicazione). Numeri non ancora estratti/validati da PULSE." if source['type']=='datasets' else f"Pubblicazione dell'ente {source['name']}. Contenuto numerico non ancora estratto/verificato da PULSE."),
               'article_type':ref_type,'date_semantics':('dataset_update' if source['type']=='datasets' else 'publication'),
               'public_source':{'url':url,'domain':source['domain'],
               'role':('primary_data_catalog' if source['type']=='datasets' else 'primary_institutional_publication'),'verification_method':'official_listing_date_and_url'},
               'pulse_title':'','pulse_summary':'','pulse_article_body':[],
               'key_figures':[],'chart_points':[]}
        if url not in seen or len(title)>len(seen[url]['headline']):seen[url]=entry
    return sorted(seen.values(),key=lambda x:(x['published_at'],x['id']),reverse=True)[:35]


def probe(source:dict, session:requests.Session, *,timeout:int=18) -> tuple[dict,list[dict]]:
    result={'id':source['id'],'institution':source['name'],'catalog_url':source['url'],
            'kind':source['type'],'status':'not_checked','entries':0,'http_status':None,
            'error':None,'last_official_publication':None}
    try:
        response=session.get(source['url'],timeout=timeout,allow_redirects=True)
        result['http_status']=response.status_code
        response.raise_for_status()
        if not official_url(response.url,source['domain']):raise ValueError('Redirect outside official institution')
        if 'html' not in response.headers.get('Content-Type','').lower():raise ValueError('Catalog response is not HTML')
        if len(response.content)<120:raise ValueError('Suspiciously short HTML')
        articles=entries_from_html(response.text,response.url,source)
        result['entries']=len(articles)
        result['status']='dated_publications_discovered' if articles else 'reachable_no_dated_records'
        if articles:result['last_official_publication']=articles[0]['published_at']
        return result,articles
    except (requests.RequestException,ValueError) as error:
        result['status']='source_unavailable';result['error']=type(error).__name__+': '+str(error)[:350]
        return result,[]


def atomic_json(path:Path,payload:dict):
    path.parent.mkdir(parents=True,exist_ok=True)
    temp=path.with_suffix(path.suffix+'.tmp')
    temp.write_text(json.dumps(payload,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    os.replace(temp,path)


def execute(*,registry=REGISTRY,status_file=STATUS,out_file=OUT,session=None) -> dict:
    data=json.loads(Path(registry).read_text(encoding='utf8'))
    records=data['sources']
    if len(records)!=12 or len({x['id'] for x in records})!=12:raise ValueError('Expected 12 unique source IDs')
    http=session or requests.Session();http.headers.update({'User-Agent':UA,'Accept':'text/html'})
    results=[];all_articles=[]
    for source in records:
        result,articles=probe(source,http)
        results.append(result);all_articles.extend(articles)
        print(f"{source['id']}: {result['status']} ({len(articles)} dated records)")
    stamp=datetime.now(timezone.utc).isoformat()
    summary={'generated_at':stamp,'total_sources':12,
             'reachable':sum(x['status']!='source_unavailable' for x in results),
             'with_dated_publications':sum(x['status']=='dated_publications_discovered' for x in results),
             'dated_publications':len(all_articles),
             'source_results':results,
             'note':'Reachability is not evidence that a statistical claim has been validated.'}
    atomic_json(Path(status_file),summary)
    atomic_json(Path(out_file),{'generated_at':stamp,'origin':'12_pending_official_sources',
        'articles':sorted(all_articles,key=lambda x:(x['published_at'],x['id']),reverse=True)})
    return summary


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--status',type=Path,default=STATUS)
    parser.add_argument('--articles',type=Path,default=OUT)
    args=parser.parse_args()
    results=execute(status_file=args.status,out_file=args.articles)
    print(f"Verified dated metadata {results['dated_publications']}, official pages reached {results['reachable']}/12")

if __name__=='__main__':main()
