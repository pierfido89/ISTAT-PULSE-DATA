#!/usr/bin/env python3
"""PULSE demo: read-only news freshness and publisher/origin health check.
Never reports a crawl timestamp as a source publication timestamp.
"""
from __future__ import annotations
import argparse
from datetime import datetime, timezone
from pathlib import Path
import json

def utc(raw):
    try:
        dt=datetime.fromisoformat(str(raw).replace("Z","+00:00"))
        return dt.astimezone(timezone.utc) if dt.tzinfo else None
    except (TypeError,ValueError,AttributeError,OverflowError):
        return None

def assess(index, articles, now=None):
    now=now or datetime.now(timezone.utc)
    stamp=utc(index.get("generated_at"))
    rows={a.get("id"):a for a in articles.get("articles",[]) if isinstance(a,dict)}
    visible=[rows[i] for section in ("oggi","ieri") for i in index.get(section,[]) if i in rows]
    newspaper=[r for r in visible if (r.get("discovery") or {}).get("role")=="journalistic_radar"]
    unchecked=[r for r in visible if (r.get("public_source") or {}).get("role")!="primary_statistical_source"]
    age=round((now-stamp).total_seconds()/3600,2) if stamp else None
    stale=age is None or age>24 or age< -1
    return {
        "schema_version":"pulse-news-health-v1",
        "last_successful_export_utc":index.get("generated_at"),
        "age_hours":age,
        "stale":stale,
        "oggi":len(index.get("oggi",[])),
        "ieri":len(index.get("ieri",[])),
        "visible_today_yesterday":len(visible),
        "media_origin_verified":len(newspaper),
        "media_share_pct":round(100*len(newspaper)/len(visible),1) if visible else None,
        "unverified_public":len(unchecked),
        "warning": ("Feed oltre 24 ore: non presentare vecchie notizie come fresche"
                    if stale else ("Nessun nuovo contenuto oggi/ieri" if not visible else "")),
        "media_99pct_guaranteed":False,
    }

def main():
    p=argparse.ArgumentParser()
    p.add_argument("--news-dir",type=Path,default=Path("data/news"))
    p.add_argument("--strict",action="store_true")
    a=p.parse_args()
    idx=json.loads((a.news_dir/"index.json").read_text(encoding="utf-8"))
    arts=json.loads((a.news_dir/"articles.json").read_text(encoding="utf-8"))
    result=assess(idx,arts)
    print(json.dumps(result,ensure_ascii=False,indent=2))
    if a.strict and (result["stale"] or result["unverified_public"]): raise SystemExit(2)

if __name__=="__main__":main()
