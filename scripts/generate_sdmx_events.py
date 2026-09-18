#!/usr/bin/env python3
"""
Generate a small, high-confidence national PULSE feed from official IstatData
SDMX series. Queries are intentionally few to respect ISTAT service limits.
"""
from __future__ import annotations

import hashlib
import json
import math
import re
import urllib.request
import xml.etree.ElementTree as ET
from pathlib import Path

import numpy as np
import pandas as pd

BASE = "https://esploradati.istat.it/SDMXWS/rest/v1/data"
OUT = Path("app/src/main/assets/pulse_events_sdmx.tsv")
META = Path("app/src/main/assets/pulse_sdmx_meta.json")

COLUMNS = [
    "id","municipality_code","municipality","province","region","indicator",
    "patterns","scope","score","validation_status","period","summary","annual",
    "rolling12","benchmark_local","benchmark_rest","analysis","source_family","source_url",
]

DATASETS = [
    {
        "name": "Prezzi al consumo NIC",
        "flow": "167_745_DF_DCSP_NIC1B2025_1",
        "start": "2026",
        "target": {"FREQ":"M","REF_AREA":"IT","ECOICOP_2":"00"},
        "note": "Indice generale dei prezzi al consumo per l'intera collettività, base 2025.",
    },
    {
        "name": "Tasso di disoccupazione",
        "flow": "151_874_DF_DCCV_TAXDISOCCUMENS1_1",
        "start": "2024",
        "target": {"FREQ":"M","REF_AREA":"IT","DATA_TYPE":"UNEM_R","SEX":"9","AGE":"Y15-74"},
        "note": "Tasso di disoccupazione mensile, popolazione 15-74 anni, totale sesso.",
    },
]

def local(tag: str) -> str:
    return tag.rsplit("}",1)[-1]

def fetch(flow: str, start: str) -> tuple[bytes,str]:
    url = f"{BASE}/{flow}/all/IT1?startPeriod={start}&endPeriod=2026"
    req = urllib.request.Request(
        url,
        headers={
            "User-Agent":"ISTAT-PULSE/0.6",
            "Accept":"application/vnd.sdmx.genericdata+xml;version=2.1",
        },
    )
    with urllib.request.urlopen(req, timeout=180) as response:
        raw = response.read()
    return raw, url

def parse_series(raw: bytes) -> list[dict]:
    root = ET.fromstring(raw)
    out = []
    for series in root.iter():
        if local(series.tag) != "Series":
            continue
        key = {}
        obs = []
        for child in series:
            t = local(child.tag)
            if t == "SeriesKey":
                key = {v.attrib.get("id",""): v.attrib.get("value","") for v in child}
            elif t == "Obs":
                period = value = None
                for v in child:
                    vt = local(v.tag)
                    if vt == "ObsDimension":
                        period = v.attrib.get("value")
                    elif vt == "ObsValue":
                        value = v.attrib.get("value")
                if period and value:
                    try:
                        obs.append((period,float(value)))
                    except ValueError:
                        pass
        if obs:
            obs.sort(key=lambda x:x[0])
            out.append({"key":key,"obs":obs})
    return out

def choose_series(series: list[dict], target: dict) -> dict | None:
    candidates = []
    for s in series:
        key = s["key"]
        if all(key.get(k) == v for k,v in target.items()):
            candidates.append(s)
    if not candidates:
        return None
    # Latest observation first, then latest edition/revision.
    return max(
        candidates,
        key=lambda s: (
            s["obs"][-1][0],
            s["key"].get("EDITION",""),
            len(s["obs"]),
        ),
    )

def robust_scale(values) -> float:
    a = np.asarray(values,dtype=float)
    a = a[np.isfinite(a)]
    if len(a) < 3:
        return 0.0
    med = np.median(a)
    mad = np.median(np.abs(a-med))*1.4826
    if mad > 1e-9:
        return float(mad)
    sd = float(np.std(a))
    return sd if sd > 1e-9 else 0.0

def fmt(v: float) -> str:
    return f"{v:.2f}".rstrip("0").rstrip(".").replace(".",",")

def build_event(dataset: dict, chosen: dict, source_url: str) -> dict | None:
    obs = chosen["obs"][-30:]
    if len(obs) < 6:
        return None
    periods = [p for p,_ in obs]
    values = np.array([v for _,v in obs],dtype=float)
    deltas = np.diff(values)
    latest_delta = float(deltas[-1])
    prior_delta = float(deltas[-2])
    scale = robust_scale(deltas[:-1])
    if scale <= 1e-9:
        scale = max(abs(float(np.median(values)))*0.002,1e-6)
    z = abs(latest_delta)/scale

    patterns=[]
    analysis=[]
    prior_window = values[max(0,len(values)-13):-1]
    if len(prior_window) >= 5 and values[-1] > np.max(prior_window) and z >= 0.5:
        patterns.append("RECORD_MAX")
        analysis.append("Record: l'ultimo valore supera tutti i valori dei dodici mesi precedenti disponibili.")
    elif len(prior_window) >= 5 and values[-1] < np.min(prior_window) and z >= 0.5:
        patterns.append("RECORD_MIN")
        analysis.append("Record: l'ultimo valore è inferiore a tutti i valori dei dodici mesi precedenti disponibili.")

    if latest_delta*prior_delta < 0 and z >= 0.8:
        patterns.append("INVERSIONE")
        analysis.append("Inversione: l'ultima variazione mensile cambia segno rispetto alla precedente.")
    elif latest_delta*prior_delta > 0 and abs(prior_delta) > 1e-9:
        ratio=abs(latest_delta)/abs(prior_delta)
        if ratio >= 1.7 and z >= 0.9:
            patterns.append("ACCELERAZIONE")
            analysis.append("Accelerazione: l'ultima variazione è nettamente più ampia della precedente.")
        elif ratio <= 0.5 and abs(prior_delta) >= 0.7*scale:
            patterns.append("RALLENTAMENTO")
            analysis.append("Rallentamento: l'ultima variazione è nettamente più contenuta della precedente.")

    level_hist=values[max(0,len(values)-13):-1]
    lscale=robust_scale(level_hist)
    zlevel=abs(values[-1]-np.median(level_hist))/lscale if lscale>1e-9 and len(level_hist)>=5 else 0.0
    if zlevel>=2.5 or z>=2.75:
        patterns.append("ANOMALIA")
        analysis.append("Anomalia: l'ultimo valore o la sua variazione supera la soglia robusta PULSE.")

    patterns=list(dict.fromkeys(patterns))
    if not patterns:
        return None

    score=48.0+min(20.0,z*4.0)+min(10.0,zlevel*2.0)
    score += 10 if any(p.startswith("RECORD") for p in patterns) else 0
    score += 8 if "INVERSIONE" in patterns else 0
    score += 8 if "ANOMALIA" in patterns else 0
    score += 5 if ("ACCELERAZIONE" in patterns or "RALLENTAMENTO" in patterns) else 0
    score=min(99.0,score)

    prev,cur=values[-2],values[-1]
    movement="sale" if cur>prev else "scende" if cur<prev else "resta stabile"
    summary=(
        f"Italia: {dataset['name']} {movement} da {fmt(prev)} a {fmt(cur)} "
        f"nel periodo {periods[-1]}."
    )
    analysis.append(dataset["note"])
    analysis.append(f"PULSE Score: {score:.1f}/100. Fonte: IstatData SDMX, ISTAT.")
    event_id=hashlib.sha256(
        f"SDMX|{dataset['flow']}|{periods[-1]}".encode()
    ).hexdigest()[:16]
    return {
        "id":event_id,
        "municipality_code":f"SDMX-IT-{dataset['flow']}",
        "municipality":"Italia",
        "province":"",
        "region":"Italia",
        "indicator":dataset["name"],
        "patterns":"|".join(patterns),
        "scope":"GENERAL",
        "score":round(score,1),
        "validation_status":"SEGNALE PULSE — ISTATDATA",
        "period":periods[-1],
        "summary":summary,
        "annual":"",
        "rolling12":"|".join(f"{v:.6g}" for v in values),
        "benchmark_local":"",
        "benchmark_rest":"",
        "analysis":"¦".join(analysis),
        "source_family":"IstatData SDMX — ISTAT",
        "source_url":source_url,
    }

def main():
    events=[]
    sources=[]
    for dataset in DATASETS:
        raw,url=fetch(dataset["flow"],dataset["start"])
        parsed=parse_series(raw)
        chosen=choose_series(parsed,dataset["target"])
        if chosen is None:
            print(f"SKIP {dataset['name']}: requested aggregate series not found.")
            continue
        event=build_event(dataset,chosen,url)
        if event:
            events.append(event)
            print(f"SDMX event: {dataset['name']} -> {event['period']} score {event['score']}")
        else:
            print(f"NO SIGNAL {dataset['name']}: series loaded but no PULSE pattern at latest observation.")
        sources.append({
            "name":dataset["name"],
            "flow":dataset["flow"],
            "url":url,
            "bytes":len(raw),
            "sha256":hashlib.sha256(raw).hexdigest(),
            "latest_period":chosen["obs"][-1][0],
            "series_key":chosen["key"],
        })

    OUT.parent.mkdir(parents=True,exist_ok=True)
    pd.DataFrame(events,columns=COLUMNS).to_csv(OUT,sep="\t",index=False)
    META.write_text(json.dumps({
        "source_family":"IstatData SDMX — ISTAT",
        "events":len(events),
        "sources":sources,
        "latest_period":max((s["latest_period"] for s in sources),default=""),
    },ensure_ascii=False,indent=2),encoding="utf-8")
    print(f"IstatData SDMX events: {len(events)}")
    print(f"Asset: {OUT}")

if __name__=="__main__":
    main()
