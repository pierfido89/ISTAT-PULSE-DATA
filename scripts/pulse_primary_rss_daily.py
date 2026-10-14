"""Add first-party statistical releases to the PULSE news feed every scheduled run.

This is a *source-release* layer, not an automatically written analytical article.
Only the publisher's actual RSS publication time is used. No synthetic pattern
score, percentage, editorial analysis, or publication date is generated.
"""
from datetime import datetime, timedelta, timezone
from email.utils import parsedate_to_datetime
from hashlib import sha256
from html import unescape
import re
from urllib.parse import urlsplit
from zoneinfo import ZoneInfo

FEEDS = (
    ("ISTAT updates", "https://www.istat.it/feed", "istat.it"),
    ("ISTAT official releases", "https://www.istat.it/documenti/comunicato-stampa/feed", "istat.it"),
    ("INPS statistical news", "https://www.inps.it/it/it.rss.news.xml", "inps.it"),
    ("INPS releases", "https://www.inps.it/it/it.rss.comunicati.xml", "inps.it"),
)
STATS = re.compile(
    r"(statistic|rapport|osservatorio|dati|istat|prezzi|inflazione|"
    r"pension|assegno|occupazion|disoccupazion|lavoro|redditi|"
    r"econom|pil|produzion|turism|welfare|region|abitazion|"
    r"censiment|imprese|mercato|ambient|scuola|salute|"
    r"indagin|previden|consum|spesa|popolazion|"
    r"nascite|mortalit|energia|istruzion|assistenza|"
    r"pubblicazion|serie storiche)", re.I)
NOT_STATISTICS = re.compile(
    r"(concorso|interpello|posti funzione|selezione del personale|"
    r"assunzioni interne|avviso di gara|inaugurazione sede)", re.I)
ROME = ZoneInfo("Europe/Rome")

def canonical(url):
    try:
        parsed = urlsplit(url)
        host = (parsed.hostname or "").lower().removeprefix("www.")
        if parsed.scheme != "https" or parsed.username or parsed.password:
            return None
        path = parsed.path.rstrip("/")
        if not path or path == "/": return None
        return host, host + path.lower()
    except ValueError:
        return None

def first_party(item, expected):
    link = canonical(item.get("url", ""))
    return link is not None and link[0] == expected

def actual_published_at(raw):
    try:
        stamp = parsedate_to_datetime(raw)
        if stamp.tzinfo is None: return None
        return stamp.astimezone(timezone.utc)
    except (TypeError, ValueError, OverflowError):
        try:
            stamp = datetime.fromisoformat((raw or "").replace("Z", "+00:00"))
            return stamp.astimezone(timezone.utc) if stamp.tzinfo else None
        except (TypeError, ValueError):
            return None

def add_first_party_publications(by_id, now, rss_items):
    """Mutate existing PULSE news by_id, preserving existing verified items.

    rss_items is passed by the caller so the discovery and release ingestion
    share the same documented RSS parser and network timeout policy.
    """
    published_links = {
        item: row["id"]
        for row in by_id.values()
        if (item := canonical((row.get("public_source") or {}).get("url", "")))
        and (row.get("public_source") or {}).get("role") == "primary_statistical_source"
        and row.get("id")
    }
    added = 0
    failures = []
    for name, feed_url, host in FEEDS:
        try:
            items = rss_items(feed_url)
        except Exception as exc:
            failures.append(f"{name}: {type(exc).__name__}: {str(exc)[:90]}")
            continue
        for item in items[:100]:
            title = re.sub(r"\s+", " ", unescape(item.get("title") or "")).strip()
            if len(title) < 25 or NOT_STATISTICS.search(title) or not STATS.search(title):
                continue
            if not first_party(item, host): continue
            published = actual_published_at(item.get("published_raw", ""))
            if published is None or published > now + timedelta(minutes=5):
                continue
            if published.astimezone(ROME).date() < (now.astimezone(ROME).date() - timedelta(days=7)):
                continue
            canonical_link = canonical(item["url"])
            if canonical_link in published_links: continue
            identifier = "PULSE-RSS-" + sha256(canonical_link[1].encode()).hexdigest()[:20].upper()
            teaser = re.sub(r"\s+", " ", unescape(re.sub(r"<[^>]+>", " ", item.get("summary") or ""))).strip()
            if len(teaser) < 65:
                teaser = ("Pubblicazione statistica della fonte ufficiale. "
                          "Consulta il documento originale per dati, metodologia e testo completo.")
            by_id[identifier] = {
                "id": identifier,
                "published_at": published.isoformat().replace("+00:00", "Z"),
                "first_published_at_utc": now.isoformat().replace("+00:00", "Z"),
                "last_seen_at": now.isoformat(),
                "topic": "ISTITUZIONI",
                "pulse_score": 0, "patterns": [],
                "headline": title,
                "summary": teaser[:1600],
                "public_source": {
                    "url": item["url"], "domain": host,
                    "role": "primary_statistical_source",
                    "verification_method": "first_party_publisher_rss",
                    "verification_score": 100
                },
                "period_reference": None, "latest_source_update": None,
                "verified_series": [],
                "statistical_claims": [],
                "editorial_status": "verified",
                "publication_status": "published",
            }
            published_links[canonical_link] = identifier
            added += 1
    print("[OFFICIAL-NEWS] added =", added, "rss_errors =", failures, flush=True)
    return added
