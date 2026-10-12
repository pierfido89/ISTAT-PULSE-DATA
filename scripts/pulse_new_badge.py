#!/usr/bin/env python3
"""NEW in PULSE (not new on source website): exact 180-minute eligibility.

Only articles newly admitted to a current PULSE news feed carry a first-publication
timestamp. Historic/source catalogue records never gain NEW on import or refresh.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from email.utils import parsedate_to_datetime


def parse_utc(value):
    if not isinstance(value, str) or not value.strip():
        return None
    try:
        point = datetime.fromisoformat(value.strip().replace("Z", "+00:00"))
        if point.tzinfo is None:
            return None
        return point.astimezone(timezone.utc)
    except (TypeError, ValueError, OverflowError):
        return None


def original_date_utc(rss_date):
    if not isinstance(rss_date, str) or not rss_date.strip():
        return None
    try:
        date = parsedate_to_datetime(rss_date)
        if date.tzinfo is None:
            return None  # no guess about the RSS publisher's timezone
        return date.astimezone(timezone.utc)
    except (TypeError, ValueError, OverflowError, IndexError):
        return None


def stamp_first_pulse_publication(article, previous, now, original_source_date):
    """Mutate candidate only when truly first published in PULSE and source is recent.

    Existing records without this metadata are intentionally NOT backfilled.
    Preserve verified PULSE first-published timestamp after a re-crawl/edit.
    Source documentation dated >24h ago is NOT revived as a fresh article.
    """
    if not isinstance(article, dict):
        raise ValueError("Article dict required")
    previous = previous or {}
    saved = previous.get("first_published_at_utc")
    if saved:
        date = parse_utc(saved)
        if date and date <= now.astimezone(timezone.utc):
            article["first_published_at_utc"] = date.isoformat()
        return article
    if previous:
        # Legacy record with no first-publication evidence: no fabricated NEW.
        return article
    if article.get("publication_status") != "published":
        return article
    if article.get("editorial_status") not in {
        "verified", "verified_primary_match", "journalistic_attributed"
    }:
        return article
    now = now.astimezone(timezone.utc)
    source = (original_date_utc(original_source_date) if isinstance(original_source_date, str)
              else original_source_date)
    if source is None or source.tzinfo is None:
        return article
    source = source.astimezone(timezone.utc)
    age = now - source
    if timedelta(0) <= age <= timedelta(hours=24):
        article["first_published_at_utc"] = now.isoformat()
    return article


def is_new(article, now):
    source_time = parse_utc(article.get("first_published_at_utc"))
    if source_time is None or not article.get("id"):
        return False
    age = now.astimezone(timezone.utc) - source_time
    return timedelta(0) <= age < timedelta(minutes=180)
