#!/usr/bin/env python3
"""Merge only current-year DEMO and IstatData SDMX PULSE feeds."""
from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd

ASSETS=Path("app/src/main/assets")
DEMO=ASSETS/"pulse_events_demo.tsv"
SDMX=ASSETS/"pulse_events_sdmx.tsv"
OUT=ASSETS/"pulse_events.tsv"
MANIFEST=ASSETS/"pulse_manifest.json"
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
    sdmx=read(SDMX,"SDMX")
    combined=pd.concat([demo,sdmx],ignore_index=True)

    # The home feed is a CURRENT radar, not an historical archive.
    # Keep only events whose trigger period belongs to the latest year available.
    combined["_year"]=combined["period"].astype(str).str.extract(r"^(\\d{4})",expand=False)
    valid_years=pd.to_numeric(combined["_year"],errors="coerce").dropna()
    if valid_years.empty:
        raise RuntimeError("No valid event years found in PULSE feed")
    current_year=int(valid_years.max())
    combined=combined[combined["_year"].eq(str(current_year))].copy()

    combined=combined.drop_duplicates(subset=["id"],keep="first")
    combined=combined.sort_values(["score_num","period"],ascending=[False,False])
    combined=combined.drop(columns=["score_num","_year"])
    combined.to_csv(OUT,sep="\t",index=False)

    manifest=json.loads(MANIFEST.read_text(encoding="utf-8"))
    sdmx_meta=json.loads(SDMX_META.read_text(encoding="utf-8"))

    periods=[p for p in combined["period"].tolist() if isinstance(p,str) and p]
    latest=max(periods,default=manifest.get("latest_period",""))
    families=sorted(set(x for x in combined["source_family"].tolist() if x))
    counts=combined["source_family"].value_counts().to_dict()

    manifest.update({
        "version":"0.6-data-current",
        "generated_at":datetime.now(timezone.utc).isoformat(),
        "feed_events":int(len(combined)),
        "latest_period":latest,
        "source_period":f"feed corrente {current_year} · ultimo dato {latest}",
        "current_feed_year":current_year,
        "historical_sources_excluded":["BES dei territori — ISTAT"],
        "indicators":sorted(set(combined["indicator"].tolist())),
        "source_families":families,
        "events_by_source":{str(k):int(v) for k,v in counts.items()},
        "istatdata_sdmx":sdmx_meta,
    })
    manifest["feed_sha256"]=hashlib.sha256(OUT.read_bytes()).hexdigest()
    MANIFEST.write_text(json.dumps(manifest,ensure_ascii=False,indent=2),encoding="utf-8")

    print(f"Current-year PULSE feed ({current_year}): {len(combined)} events")
    for family,count in counts.items():
        print(f"  {family}: {count}")
    print(f"Latest period across sources: {latest}")
    print(f"SHA256: {manifest['feed_sha256']}")

if __name__=="__main__":
    main()
