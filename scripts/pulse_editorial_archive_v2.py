#!/usr/bin/env python3
"""Offline PULSE paginated article archive V2 prototype. No GitHub/API writes.

Compatible with currently human-approved items only. Future automatic approval
requires a new independently audited contract and explicit production rollout.
"""
from __future__ import annotations
import argparse
from datetime import datetime, timezone
from pathlib import Path
import hashlib
import json

SCHEMA="pulse-editorial-archive-v2"
PAGE_LIMIT=25


def parse_iso_utc(s):
    if not isinstance(s,str):
        raise ValueError("UTC publish timestamp missing")
    x=datetime.fromisoformat(s.replace("Z","+00:00"))
    if x.tzinfo is None:
        raise ValueError("Publication timestamp must have timezone")
    return x.astimezone(timezone.utc)


def paginate(articles: list[dict], *, page_limit:int=PAGE_LIMIT) -> tuple[dict,dict]:
    if not isinstance(page_limit,int) or not 1 <= page_limit <= 50:
        raise ValueError("Page size must be 1 to 50")
    if not isinstance(articles,list):
        raise ValueError("Expected article list")
    by_id={}
    for article in articles:
        if not isinstance(article,dict):
            raise ValueError("Malformed article")
        identity=article.get("id")
        if not identity or identity in by_id:
            raise ValueError("Missing/duplicate article ID")
        if (article.get("publication_status") != "approved_for_pulse"
                or article.get("human_approved") is not True):
            # Never ingest model-generated draft directly.
            raise ValueError("Unapproved article cannot enter public archive")
        at=parse_iso_utc(article.get("first_published_at_utc"))
        if not article.get("primary_source_url","").startswith("https://"):
            raise ValueError("Official source URL mandatory")
        if not article.get("headline") or not article.get("paragraphs"):
            raise ValueError("Missing article content")
        by_id[identity]=(at,article)
    ordered=sorted(by_id.values(),key=lambda r:(r[0],r[1]["id"]),reverse=True)
    pages={}
    for pos in range(0,len(ordered),page_limit):
        page_number=pos//page_limit+1
        filename=f"pages/page_{page_number:05d}.json"
        batch=[a for _,a in ordered[pos:pos+page_limit]]
        page_body={"schema_version":SCHEMA,"page":page_number,"articles":batch}
        pages[filename]=page_body
    manifest={
        "schema_version":SCHEMA,
        "auto_publish_enabled":False,
        "publication_allowed_by_this_script":False,
        "article_count":len(ordered),
        "page_size":page_limit,
        "page_count":len(pages),
        "pages":[{
            "url_path":name,
            "count":len(page["articles"]),
            "sha256":hashlib.sha256(
                (json.dumps(page,ensure_ascii=False,sort_keys=True,separators=(',',':'))+"\n")
                .encode("utf-8")).hexdigest(),
        } for name,page in pages.items()]
    }
    return manifest,pages


def main():
    p=argparse.ArgumentParser()
    p.add_argument("--approved-input",type=Path,required=True)
    p.add_argument("--output-dir",type=Path,required=True)
    p.add_argument("--page-size",type=int,default=PAGE_LIMIT)
    args=p.parse_args()
    if args.output_dir.resolve() == args.approved_input.resolve().parent:
        raise ValueError("Never overwrite original approved feed directory")
    d=json.loads(args.approved_input.read_text(encoding="utf-8"))
    if d.get("schema_version") != "pulse-editorial-approved-v1":
        raise ValueError("Not a reviewed v1 feed")
    index,pages=paginate(d.get("articles"),page_limit=args.page_size)
    args.output_dir.mkdir(parents=True,exist_ok=True)
    for name,body in pages.items():
        file=args.output_dir/name
        file.parent.mkdir(parents=True,exist_ok=True)
        file.write_text(json.dumps(body,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
    (args.output_dir/"index.json").write_text(
        json.dumps(index,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
    print(json.dumps({
        "mode":"dry_run_export_only","indexed_articles":index["article_count"],
        "pages":index["page_count"],"uploaded":False,"auto_publish_enabled":False
    }))


if __name__=="__main__":
    main()
