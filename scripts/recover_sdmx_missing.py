#!/usr/bin/env python3
from __future__ import annotations
import hashlib, json, time
from datetime import datetime, timezone
from pathlib import Path
import pandas as pd
import scripts.generate_sdmx_events as g

TARGET_NAMES = {
    "Produzione industriale",
    "Fiducia del commercio",
    "Prezzi all'importazione",
    "Arrivi turistici",
    "Presenze turistiche",
}
DATA = Path("data")
FEED = DATA / "pulse_events.tsv"
MANIFEST = DATA / "pulse_manifest.json"
CATALOG = DATA / "sources_catalog.json"

def period_key(value: str):
    value=str(value or "")
    if "-Q" in value:
        y,q=value.split("-Q",1)
        return (int(y),int(q)*3,0)
    if "-" in value:
        try:
            y,m=value.split("-",1)[:2]
            return (int(y),int(m),1)
        except Exception:
            pass
    try:
        return (int(value),12,0)
    except Exception:
        return (0,0,0)

def main():
    datasets=[d for d in g.DATASETS if d["name"] in TARGET_NAMES]
    if {d["name"] for d in datasets} != TARGET_NAMES:
        raise RuntimeError("Recovery target list no longer matches configured SDMX datasets.")

    unique={}
    for d in datasets:
        unique[(d["flow"],d["start"])]=d

    fetched={}
    unresolved=set(unique)
    for outer in range(1,5):
        for key in list(unresolved):
            d=unique[key]
            try:
                raw,url=g.fetch(d)
                fetched[key]=(raw,url,g.parse_series(raw))
                unresolved.remove(key)
                print(f"RECOVERED FLOW {key[0]} on outer attempt {outer}: {len(raw):,} bytes")
            except Exception as exc:
                print(f"RETRY FLOW {key[0]} outer attempt {outer}: {exc!r}")
                time.sleep(5)
        if not unresolved:
            break
        time.sleep(8 * outer)

    if unresolved:
        raise RuntimeError(f"Still unavailable after recovery retries: {sorted(unresolved)}")

    recovered=[]
    recovered_meta={}
    for d in datasets:
        raw,url,parsed=fetched[(d["flow"],d["start"])]
        chosen=g.choose_series(parsed,d)
        if chosen is None:
            raise RuntimeError(f"Configured headline series not found for {d['name']}")
        event=g.build_event(d,chosen,url)
        if event is not None:
            recovered.append(event)
            print(f"RECOVERED SIGNAL {d['name']} -> {event['period']} score {event['score']}")
        else:
            print(f"RECOVERED MONITOR {d['name']} -> {chosen['obs'][-1][0]} (no current signal)")
        recovered_meta[d["name"]]={
            "latest_period": chosen["obs"][-1][0],
            "status": "ok" if event is not None else "monitored_no_signal",
            "flow": d["flow"],
            "series_key": chosen["key"],
        }

    feed=pd.read_csv(FEED,sep="\t",dtype=str,keep_default_na=False)
    mask=(feed["source_family"].eq("IstatData SDMX — ISTAT") & feed["indicator"].isin(TARGET_NAMES))
    feed=feed.loc[~mask].copy()
    if recovered:
        add=pd.DataFrame(recovered)
        feed=pd.concat([feed,add[feed.columns]],ignore_index=True)
    feed["_score"]=pd.to_numeric(feed["score"],errors="coerce").fillna(0)
    feed=feed.sort_values(["_score","period"],ascending=[False,False]).drop(columns=["_score"])
    feed.to_csv(FEED,sep="\t",index=False)

    catalog=json.loads(CATALOG.read_text(encoding="utf-8"))
    sdmx_source=next(s for s in catalog["sources"] if "SDMX" in s["name"])
    for item in sdmx_source["provides"]:
        if isinstance(item,dict) and item.get("series") in recovered_meta:
            meta=recovered_meta[item["series"]]
            item["latest_period"]=meta["latest_period"]
            item["status"]=meta["status"]
    CATALOG.write_text(json.dumps(catalog,ensure_ascii=False,indent=2),encoding="utf-8")

    manifest=json.loads(MANIFEST.read_text(encoding="utf-8"))
    counts=feed["source_family"].value_counts().to_dict()
    periods=[p for p in feed["period"].tolist() if p]
    latest=max(periods,key=period_key,default=manifest.get("latest_period",""))
    manifest.update({
        "generated_at":datetime.now(timezone.utc).isoformat(),
        "feed_events":int(len(feed)),
        "latest_period":latest,
        "source_period":f"multi-fonte · ultimo dato {latest}",
        "indicators":sorted(set(feed["indicator"])),
        "source_families":sorted(set(feed["source_family"])),
        "events_by_source":{str(k):int(v) for k,v in counts.items()},
    })
    sdmx=manifest.get("istatdata_sdmx",{})
    old_sources={s.get("name"):s for s in sdmx.get("sources",[]) if isinstance(s,dict)}
    for d in datasets:
        meta=recovered_meta[d["name"]]
        entry=old_sources.get(d["name"],{"name":d["name"],"area":d["area"],"provides":d["provides"]})
        entry.update(meta)
        entry["signal_emitted"]=any(e["indicator"]==d["name"] for e in recovered)
        old_sources[d["name"]]=entry
    sdmx["sources"]=list(old_sources.values())
    sdmx["connected_series"]=17
    sdmx["monitored_series"]=17
    sdmx["events"]=int(counts.get("IstatData SDMX — ISTAT",0))
    sdmx["latest_period"]=max(
        [s.get("latest_period","") for s in old_sources.values() if s.get("latest_period")],
        key=period_key,
        default=sdmx.get("latest_period",""),
    )
    manifest["istatdata_sdmx"]=sdmx
    manifest["feed_sha256"]=hashlib.sha256(FEED.read_bytes()).hexdigest()
    MANIFEST.write_text(json.dumps(manifest,ensure_ascii=False,indent=2),encoding="utf-8")

    print("FINAL FEED EVENTS",len(feed))
    print("FINAL SDMX SIGNALS",counts.get("IstatData SDMX — ISTAT",0))
    print("FINAL LATEST",latest)
    assert int(counts.get("IstatData SDMX — ISTAT",0)) >= 13

if __name__=="__main__":
    main()
