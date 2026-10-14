#!/usr/bin/env python3
"""No-network regression QA for primary institutional RSS ingestion."""
from datetime import datetime, timedelta, timezone
from pulse_primary_rss_daily import (
    add_first_party_publications, actual_published_at, canonical, first_party
)
assert actual_published_at("Mon, 14 Oct 2024 10:00:00 GMT").year == 2024
assert actual_published_at("not a date") is None
assert canonical("https://www.istat.it/documenti/test/?from=news") == (
    "istat.it", "istat.it/documenti/test"
)
assert not first_party({"url":"https://other-website.example/article"}, "istat.it")
now=datetime.now(timezone.utc)
today=now.strftime("%a, %d %b %Y %H:%M:%S GMT")
def mocked(url):
    if "istat.it" not in url:return []
    return [
      {"title":"ISTAT nuove statistiche ufficiali per tutte le regioni italiane",
       "url":"https://www.istat.it/comunicato-stampa/prova-statistica-2026/",
       "summary":"Il testo pubblicato sul sito originale contiene i riferimenti ai dati e alla metodologia.",
       "published_raw":today},
      {"title":"Statistiche non verificate su sito estraneo alla fonte",
       "url":"https://news.google.com/rss/articles/something",
       "summary":"", "published_raw":today},
      {"title":"ISTAT concorso selezione del personale interno",
       "url":"https://www.istat.it/comunicato-stampa/selezione-2026/",
       "summary":"", "published_raw":today},
    ]
by_id={}
n=add_first_party_publications(by_id,now,mocked)
assert n==1,(n,by_id)
item=list(by_id.values())[0]
assert item["pulse_score"]==0 and not item["patterns"]
assert abs((actual_published_at(item["published_at"]) - now).total_seconds()) < 1
assert item["public_source"]["role"]=="primary_statistical_source"
assert add_first_party_publications(by_id,now,mocked)==0
print("PASS: source provenance, real date, trust host, no invented score, stable dedup")
