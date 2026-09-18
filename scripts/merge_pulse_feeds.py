#!/usr/bin/env python3
"""Merge DEMO, BES Territories and IstatData SDMX PULSE feeds."""
from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd

ASSETS=Path("app/src/main/assets")
DEMO=ASSETS/"pulse_events_demo.tsv"
BES=ASSETS/"pulse_events_bes.tsv"
SDMX=ASSETS/"pulse_events_sdmx.tsv"
OUT=ASSETS/"pulse_events.tsv"
MANIFEST=ASSETS/"pulse_manifest.json"
BES_META=ASSETS/"pulse_bes_meta.json"
SDMX_META=ASSETS/"pulse_sdmx_meta.json"

REQUIRED=[
    "id","municipality_code","municipality","province","region","indicator",
    "patterns","scope","score","validation_status","period","summary","annual",
    "rolling12","benchmark_local","benchmark_rest","analysis","source_family","source_url",
]

def read(path: Path, label: str) -> pd.DataFrame:
    if not path.exists():
        raise RuntimeError(f"{label} feed missing: {path}")
    frame=pd.read_csv(path,sep="\t",dtype=str,keep_default_na=False)
    missing=[c for c in REQUIRED if c not in frame.columns]
    if missing:
        raise RuntimeError(f"{label} feed missing columns: {missing}")
    frame=frame[REQUIRED].copy()
    frame["score_num"]=pd.to_numeric(frame["score"],errors="coerce").fillna(0)
    return frame

def main():
    demo=read(DEMO,"DEMO")
    bes=read(BES,"BES")
    sdmx=read(SDMX,"SDMX")
    combined=pd.concat([demo,bes,sdmx],ignore_index=True)
    combined=combined.drop_duplicates(subset=["id"],keep="first")
    combined=combined.sort_values(["score_num","period"],ascending=[False,False])
    combined=combined.drop(columns=["score_num"])
    combined.to_csv(OUT,sep="\t",index=False)

    manifest=json.loads(MANIFEST.read_text(encoding="utf-8"))
    bes_meta=json.loads(BES_META.read_text(encoding="utf-8"))
    sdmx_meta=json.loads(SDMX_META.read_text(encoding="utf-8"))

    periods=[p for p in combined["period"].tolist() if isinstance(p,str) and p]
    latest=max(periods,default=manifest.get("latest_period",""))
    families=sorted(set(x for x in combined["source_family"].tolist() if x))
    counts=combined["source_family"].value_counts().to_dict()

    manifest.update({
        "version":"0.6-data",
        "generated_at":datetime.now(timezone.utc).isoformat(),
        "feed_events":int(len(combined)),
        "latest_period":latest,
        "source_period":f"multi-fonte · ultimo dato {latest}",
        "indicators":sorted(set(combined["indicator"].tolist())),
        "source_families":families,
        "events_by_source":{str(k):int(v) for k,v in counts.items()},
        "bes_territori":bes_meta,
        "istatdata_sdmx":sdmx_meta,
    })
    manifest["feed_sha256"]=hashlib.sha256(OUT.read_bytes()).hexdigest()
    MANIFEST.write_text(json.dumps(manifest,ensure_ascii=False,indent=2),encoding="utf-8")

    print(f"Merged PULSE feed: {len(combined)} events")
    for family,count in counts.items():
        print(f"  {family}: {count}")
    print(f"Latest period across sources: {latest}")
    print(f"SHA256: {manifest['feed_sha256']}")

if __name__=="__main__":
    main()
