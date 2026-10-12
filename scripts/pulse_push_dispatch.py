#!/usr/bin/env python3
"""PULSE real push dispatcher. Firebase Cloud Messaging HTTP v1 via Admin SDK.

Invoked by GitHub Actions on a *committed NEW news feed*, never by Android polling.
No Firebase key in source: runtime identity is injected through Actions Secrets.
All recipient eligibility is deterministic; no NLP or guessed geography.
At-least-once network delivery with server claim + on-device idempotent rendering.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timedelta, timezone
import hashlib
import json
import os
import re

REGIONS = {
    "piemonte":"01","valle d'aosta":"02","lombardia":"03",
    "trentino-alto adige":"04","veneto":"05","friuli-venezia giulia":"06",
    "liguria":"07","emilia-romagna":"08","toscana":"09","umbria":"10",
    "marche":"11","lazio":"12","abruzzo":"13","molise":"14",
    "campania":"15","puglia":"16","basilicata":"17","calabria":"18",
    "sicilia":"19","sardegna":"20"
}
TOPICS = {"AMBIENTE", "ENERGIA", "ECONOMIA", "LAVORO", "SALUTE",
          "ISTRUZIONE", "MOBILITA", "DEMOGRAFIA", "CASA", "TUTTE"}
REGION_OR_NATIONAL = {"ITALIA":"", "REGIONE":r"\d{2}",
                      "PROVINCIA":r"\d{3}", "COMUNE":r"\d{6}"}
MAX_AGE = timedelta(hours=24)
CONSENT_VERSION = "pulse-push-consent-v1"


def iso(value):
    try:
        t = datetime.fromisoformat(value.replace("Z","+00:00"))
        if t.tzinfo is None:
            return None
        return t.astimezone(timezone.utc)
    except (ValueError, AttributeError, TypeError, OverflowError):
        return None


def canonical_topic(value):
    return str(value or "").upper().replace("À","A").strip()


def authoritative_geo(article):
    """Only explicit structured codes or EXACT known official region labels.

    A municipality/province cannot be inferred from fuzzy headline text.
    """
    explicit = article.get("push_geo")
    if isinstance(explicit, dict):
        level = explicit.get("level")
        code = str(explicit.get("code", ""))
        if level in REGION_OR_NATIONAL and re.fullmatch(REGION_OR_NATIONAL[level], code):
            if level == "REGIONE" and code not in REGIONS.values():
                return None
            return {"level":level,"code":code}
        return None
    territories = article.get("territories")
    if not isinstance(territories, list) or len(territories) != 1:
        return None
    val = str(territories[0]).strip().casefold()
    if val == "italia":
        return {"level":"ITALIA","code":""}
    if val in REGIONS:
        return {"level":"REGIONE","code":REGIONS[val]}
    return None


def validate_subscription(sub):
    if not isinstance(sub, dict) or sub.get("enabled") is not True:
        return False
    if sub.get("consent_version") != CONSENT_VERSION or not iso(sub.get("consent_at")):
        return False
    if not isinstance(sub.get("token"), str) or not 24 <= len(sub["token"]) <= 4096:
        return False
    topics = sub.get("topics")
    if (not isinstance(topics, list) or not 1 <= len(topics) <= 12 or
            any(t not in TOPICS for t in topics)):
        return False
    if type(sub.get("min_score")) is not int or not 50 <= sub["min_score"] <= 100:
        return False
    area = sub.get("territory")
    if not isinstance(area, dict):
        return False
    level = area.get("level")
    code = area.get("code")
    if level not in REGION_OR_NATIONAL or not isinstance(code, str):
        return False
    if not re.fullmatch(REGION_OR_NATIONAL[level], code):
        return False
    if level == "REGIONE" and code not in REGIONS.values():
        return False
    return type(sub.get("include_national")) is bool


def geo_matches(geo, subscription):
    area = subscription["territory"]
    if area["level"] == "ITALIA":
        return True
    if geo["level"] == "ITALIA":
        return subscription["include_national"]
    if area["level"] == "REGIONE":
        if geo["level"] == "REGIONE":
            return geo["code"] == area["code"]
        # A 6-digit municipality code is NOT equivalent to region code.
        # Region inference requires explicit *region_code* from publisher.
        return geo.get("region_code") == area["code"]
    if area["level"] == "PROVINCIA":
        if geo["level"] == "PROVINCIA":
            return geo["code"] == area["code"]
        return geo.get("province_code") == area["code"]
    if area["level"] == "COMUNE":
        return geo["level"] == "COMUNE" and geo["code"] == area["code"]
    return False


def article_is_eligible(article, now):
    if not isinstance(article, dict):
        return False
    if article.get("publication_status") != "published":
        return False
    if article.get("editorial_status") not in {
        "verified", "verified_primary_match", "journalistic_attributed"
    }:
        return False
    at = iso(article.get("first_published_at_utc"))
    if at is None or at > now or now - at >= MAX_AGE:
        return False
    if not re.fullmatch(r"PULSE-[A-Z0-9-]{5,70}", str(article.get("id",""))):
        return False
    if not authoritative_geo(article):
        return False
    if type(article.get("pulse_score")) is not int:
        return False
    return bool(article.get("headline"))


def eligible_recipient(article, sub, now):
    if not validate_subscription(sub) or not article_is_eligible(article, now):
        return False
    if article["pulse_score"] < sub["min_score"]:
        return False
    topic = canonical_topic(article.get("topic"))
    if "TUTTE" not in sub["topics"] and topic not in sub["topics"]:
        return False
    # No old news blasts on first sign-up or resubscription.
    pub = iso(article["first_published_at_utc"])
    if pub <= iso(sub["consent_at"]):
        return False
    return geo_matches(authoritative_geo(article), sub)


def document_key(uid, article_id):
    return hashlib.sha256((uid+"\0"+article_id).encode("utf-8")).hexdigest()


def push_data(article):
    geo = authoritative_geo(article)
    return {
        "article_id":str(article["id"]),
        "headline":str(article["headline"])[:150],
        "topic":canonical_topic(article.get("topic")),
        "territory_level":geo["level"],
        "territory_code":geo["code"],
        "publication_utc":article["first_published_at_utc"],
        "pulse_score":str(article["pulse_score"]),
    }


def reserve_once(db, uid, article, now):
    """Firestore transaction reserves a delivery slot per user/article.

    Failure/retry lease = 10m. There is still an unavoidable crash interval
    between FCM success and setting sent: Android de-duplicates that interval.
    """
    from firebase_admin import firestore
    key = document_key(uid, article["id"])
    ref = db.collection("push_delivery_receipts").document(key)
    transaction = db.transaction()
    @firestore.transactional
    def transaction_reserve(tx):
        snap = ref.get(transaction=tx)
        if snap.exists:
            row = snap.to_dict() or {}
            if row.get("status") == "sent":
                return False
            lock = row.get("reserved_at")
            if isinstance(lock, datetime) and now - lock.astimezone(timezone.utc) < timedelta(minutes=10):
                return False
        tx.set(ref, {"uid":uid, "article_id":article["id"],
                     "status":"reserved","reserved_at":now})
        return True
    return transaction_reserve(transaction)


def dispatch(db, messaging, articles, *, now=None, max_sends=500):
    now = now or datetime.now(timezone.utc)
    stats = {"new_articles":0,"matched":0,"sent":0,"skipped":0,"failed":0}
    news = [a for a in articles if article_is_eligible(a, now)]
    stats["new_articles"] = len(news)
    if not news:
        return stats
    for sub_doc in db.collection("push_subscriptions").where(
        "enabled", "==", True).stream():
        uid = sub_doc.id
        sub = sub_doc.to_dict() or {}
        if not validate_subscription(sub):
            continue
        for item in news:
            if stats["sent"] >= max_sends:
                return stats
            if not eligible_recipient(item, sub, now):
                continue
            stats["matched"] += 1
            if not reserve_once(db, uid, item, now):
                stats["skipped"] += 1
                continue
            receipt = db.collection("push_delivery_receipts").document(document_key(uid,item["id"]))
            try:
                # Re-read revocation/consent immediately before sending.
                latest = db.collection("push_subscriptions").document(uid).get().to_dict() or {}
                if not eligible_recipient(item, latest, datetime.now(timezone.utc)):
                    receipt.set({"status":"cancelled", "reserved_at":now}, merge=True)
                    stats["skipped"] += 1
                    continue
                msg = messaging.Message(
                    token=latest["token"],
                    data=push_data(item),
                    android=messaging.AndroidConfig(
                        ttl=timedelta(minutes=180),
                        priority="normal"
                    )
                )
                message_id = messaging.send(msg)
                receipt.set({"status":"sent", "sent_at":datetime.now(timezone.utc),
                             "fcm_id":message_id},merge=True)
                stats["sent"] += 1
            except Exception as exc:
                # No tokens, FCM secrets, personal prefs or full error bodies in logs.
                receipt.set({"status":"retryable", "reserved_at":now},merge=True)
                stats["failed"] += 1
    return stats


def main():
    p=argparse.ArgumentParser()
    p.add_argument("--feed",required=True)
    p.add_argument("--dry-run",action="store_true")
    p.add_argument("--max-sends",type=int,default=500)
    args=p.parse_args()
    with open(args.feed,encoding="utf-8") as f:
        raw=json.load(f)
    now=datetime.now(timezone.utc)
    articles=raw.get("articles",[])
    if args.dry_run:
        print(json.dumps({"mode":"dry-run","eligible_articles":sum(
            article_is_eligible(a,now) for a in articles),"sent":0}))
        return
    # Uses ADC securely injected by GitHub Actions. Never commit private keys.
    import firebase_admin
    from firebase_admin import credentials, firestore, messaging
    if not firebase_admin._apps:
        firebase_admin.initialize_app(credentials.ApplicationDefault())
    print(json.dumps(dispatch(firestore.client(),messaging,articles,
                              now=now,max_sends=args.max_sends)))


if __name__=="__main__":
    main()
