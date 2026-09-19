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
paths=[base/"pulse_observations_sdmx.tsv",base/"pulse_observations_bes.tsv",base/"pulse_observations_amc.tsv"]
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
# The catalogue must never describe a portal as integrated unless verified
# observations have actually passed the merged-file quality checks.
catalog_path=base/"sources_catalog.json"
catalog=json.loads(catalog_path.read_text(encoding="utf-8"))
counts=meta["by_source"]
for source in catalog.get("sources",[]):
    name=source.get("name","")
    if name=="Bes dei territori — ISTAT" and counts.get(name,0):
        source["feed_status"]=(
            f"Osservazioni regionali scaricate e verificate: {counts[name]} valori. "
            "Fuori dal feed delle notizie correnti."
        )
        source["notes"]="Serie annuali storiche consultabili nella sezione Dati osservati; il periodo statistico e' sempre esplicito."
    elif name=="A misura di Comune — ISTAT" and counts.get(name,0):
        source["feed_status"]=(
            f"Prime tavole ufficiali importate e verificate: {counts[name]} valori regionali. "
            "Ampliamento a tutti i comuni in corso."
        )
        source["notes"]="Famiglie, istruzione, redditi e ambiente: leggere sempre l'anno del dato nel catalogo osservato."
catalog_path.write_text(json.dumps(catalog,ensure_ascii=False,indent=2),encoding="utf-8")
print("PULSE OBSERVED REGISTRY",meta)
