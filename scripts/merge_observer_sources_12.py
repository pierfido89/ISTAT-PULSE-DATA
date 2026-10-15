#!/usr/bin/env python3
"""Append eligible dated institutional publication pointers without replacing archive.

Operator must supply the complete original archive. Output is always separate.
Old articles are preserved byte-for-byte at JSON object level; no generated
statistical interpretation is substituted for reviewed PULSE editorial copy.
"""
import argparse
import json
from pathlib import Path
from urllib.parse import urlsplit


def merge(original: dict, pending: dict) -> dict:
    old=original.get('articles')
    if not isinstance(old,list) or len(old)<1000:
        raise ValueError('Full official Observer archive required (>=1000 entries)')
    if pending.get('origin')!='12_pending_official_sources':
        raise ValueError('Invalid pending feed origin')
    seen_ids={v.get('id') for v in old}
    seen_urls={v.get('public_source',{}).get('url') for v in old}
    inserted=[]
    for row in pending.get('articles',[]):
        url=row.get('public_source',{}).get('url')
        role=row.get('public_source',{}).get('role')
        if role!='primary_institutional_publication':continue
        if not url or urlsplit(url).scheme!='https':continue
        if not row.get('published_at','').startswith('2026-') and not row.get('published_at','').startswith('2027-'):continue
        if not row.get('observer') or not row.get('headline'):continue
        if row.get('id') in seen_ids or url in seen_urls:continue
        inserted.append(row);seen_ids.add(row['id']);seen_urls.add(url)
    combined={**original,'articles':old+inserted}
    combined['observer_12_additions']=len(inserted)
    # Keep original generated_at: source-specific publication dates must be
    # preserved, and merging is not equivalent to regenerating the archive.
    return combined


def main():
    p=argparse.ArgumentParser()
    p.add_argument('--archive',required=True,type=Path)
    p.add_argument('--additions',type=Path,default=Path(__file__).resolve().parents[1]/'data/observer_articles_12.json')
    p.add_argument('--output',required=True,type=Path)
    args=p.parse_args()
    if args.output.resolve()==args.archive.resolve():raise ValueError('Output must be separate from original archive')
    original=json.loads(args.archive.read_text(encoding='utf8'))
    pending=json.loads(args.additions.read_text(encoding='utf8'))
    combined=merge(original,pending)
    args.output.parent.mkdir(parents=True,exist_ok=True)
    args.output.write_text(json.dumps(combined,ensure_ascii=False,indent=2)+'\n',encoding='utf8')
    print(f"Base: {len(original['articles'])}; new {combined['observer_12_additions']}; total: {len(combined['articles'])}")

if __name__=='__main__':main()
