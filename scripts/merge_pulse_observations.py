#!/usr/bin/env python3
"""Combine monitored SDMX measurements and BesT annual regional observations.

Historical observed values belong to the independent observation catalogue.
Never copy this file into the PULSE current-news feed.
"""
from pathlib import Path
import pandas as pd
import hashlib
import json
from datetime import datetime,timezone

base=Path("app/src/main/assets")
out=base/"pulse_observations.tsv"
paths=[base/"pulse_observations_sdmx.tsv",base/"pulse_observations_bes.tsv"]
fields=["area","indicator","territory","period","value","unit","source","url","note","status"]
frames=[]
for source in paths:
    if not source.exists(): raise RuntimeError(f"Expected observed values missing: {source}")
    df=pd.read_csv(source,sep="\t",dtype=str,keep_default_na=False)
    if any(c not in df for c in fields): raise RuntimeError(f"Schema mismatch: {source}")
    if any(df[x].str.strip().eq("").any() for x in ["indicator","territory","period","value","source","url"]):
        raise RuntimeError(f"Missing provenance or observation: {source}")
    df["value_num"]=pd.to_numeric(df["value"],errors="coerce")
    if df["value_num"].isna().any(): raise RuntimeError(f"Non-numeric observed values: {source}")
    frames.append(df[fields])
combined=pd.concat(frames,ignore_index=True)
combined=combined.drop_duplicates(subset=["source","indicator","territory","period"])
combined.to_csv(out,sep="\t",index=False)
meta={
  "generated_at":datetime.now(timezone.utc).isoformat(),
  "rows":len(combined),
  "by_source":{str(k):int(v) for k,v in combined["source"].value_counts().items()},
  "sha256":hashlib.sha256(out.read_bytes()).hexdigest(),
  "file":"pulse_observations.tsv",
  "note":"Serie osservate, non micro-notizie PULSE. L'anno nella colonna period e' il riferimento statistico."
}
(base/"pulse_observations_manifest.json").write_text(json.dumps(meta,ensure_ascii=False,indent=2),encoding="utf-8")
print("PULSE OBSERVED REGISTRY",meta)
