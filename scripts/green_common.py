#!/usr/bin/env python3
from __future__ import annotations

from dataclasses import dataclass, asdict
from collections import defaultdict
import hashlib, math, re
from typing import Iterable
import numpy as np
import pandas as pd

EVENT_COLUMNS=[
    "id","municipality_code","municipality","province","region","indicator",
    "patterns","scope","score","validation_status","period","summary","annual",
    "rolling12","benchmark_local","benchmark_rest","analysis","source_family","source_url"
]
OBS_COLUMNS=[
    "pillar","source_name","source_url","territory_level","territory","region",
    "province","municipality_code","indicator","unit","period","value","note","series_key"
]

@dataclass
class Observation:
    pillar:str
    source_name:str
    source_url:str
    territory_level:str
    territory:str
    indicator:str
    unit:str
    period:str
    value:float
    region:str=""
    province:str=""
    municipality_code:str=""
    note:str=""
    series_key:str=""

@dataclass
class AdapterResult:
    source_name:str
    status:str
    observations:list[Observation]
    detail:str=""
    integration_mode:str="direct"
    checked_url:str=""

def clean_text(value)->str:
    return re.sub(r"\s+"," ",str(value or "")).strip()

def to_float(value):
    if value is None: return None
    if isinstance(value,(int,float,np.number)):
        v=float(value); return v if math.isfinite(v) else None
    s=str(value).strip().replace("\xa0"," ")
    if not s or s.lower() in {"nan","na","n/a","nd","n.d.","-","..","...","....",":"}: return None
    s=re.sub(r"[^0-9,\.\-+]","",s)
    if not s:return None
    if "," in s and "." in s:
        # Last separator is interpreted as decimal separator.
        if s.rfind(",")>s.rfind("."): s=s.replace(".","").replace(",",".")
        else: s=s.replace(",","")
    elif "," in s:
        # Italian decimal commas, except clear thousands group.
        parts=s.split(",")
        if len(parts)==2 and len(parts[1])<=3: s=".".join(parts)
        else: s="".join(parts)
    try:
        v=float(s); return v if math.isfinite(v) else None
    except ValueError:return None

def year_key(period:str):
    s=str(period or "")
    m=re.search(r"(19|20)\d{2}",s)
    year=int(m.group(0)) if m else 0
    q=re.search(r"Q([1-4])",s,re.I)
    mon=re.search(r"-(0?[1-9]|1[0-2])(?:\D|$)",s)
    return (year, int(q.group(1))*3 if q else int(mon.group(1)) if mon else 12, s)

def fmt(v:float,unit:str="")->str:
    if abs(v)>=1_000_000: base=f"{v/1_000_000:.2f} mln"
    elif abs(v)>=10_000: base=f"{v:,.0f}".replace(",",".")
    elif abs(v)>=100: base=f"{v:.1f}"
    else: base=f"{v:.2f}"
    base=base.rstrip("0").rstrip(".").replace(".",",")
    return f"{base} {unit}".strip()

def robust_scale(values)->float:
    a=np.asarray(list(values),dtype=float)
    a=a[np.isfinite(a)]
    if len(a)<3:return 0.0
    med=np.median(a); mad=np.median(np.abs(a-med))*1.4826
    if mad>1e-9:return float(mad)
    sd=float(np.std(a))
    return sd if sd>1e-9 else 0.0

def _location(obs:Observation):
    if obs.territory_level=="COMUNE":
        return obs.territory,obs.province,obs.region
    if obs.territory_level=="PROVINCIA":
        return obs.territory,obs.territory,obs.region
    if obs.territory_level=="REGIONE":
        return obs.territory,"",obs.territory
    if obs.territory_level in {"ITALIA","NAZIONALE"}:
        return "Italia","","Italia"
    return obs.territory,"",obs.region or obs.territory

def build_temporal_event(series:list[Observation]):
    series=sorted(series,key=lambda o:year_key(o.period))
    if len(series)<4:return None
    # duplicate periods: last one wins
    unique={}
    for o in series: unique[str(o.period)]=o
    series=sorted(unique.values(),key=lambda o:year_key(o.period))
    if len(series)<4:return None
    vals=np.array([float(o.value) for o in series],dtype=float)
    if not np.all(np.isfinite(vals)):return None
    deltas=np.diff(vals)
    latest=float(deltas[-1]); prior=float(deltas[-2])
    scale=robust_scale(deltas[:-1])
    if scale<=1e-9: scale=max(abs(float(np.median(vals)))*0.004,1e-6)
    z=abs(latest)/scale
    patterns=[]; why=[]
    hist=vals[:-1][-12:]
    if len(hist)>=3 and vals[-1]>np.max(hist) and z>=.45:
        patterns.append("RECORD_MAX");why.append("Record: ultimo valore sopra il massimo della finestra storica recente.")
    elif len(hist)>=3 and vals[-1]<np.min(hist) and z>=.45:
        patterns.append("RECORD_MIN");why.append("Record: ultimo valore sotto il minimo della finestra storica recente.")
    if latest*prior<0 and z>=.75:
        patterns.append("INVERSIONE");why.append("Inversione: l'ultima variazione cambia segno rispetto alla precedente.")
    elif latest*prior>0 and abs(prior)>1e-9:
        ratio=abs(latest)/abs(prior)
        if ratio>=1.65 and z>=.8:
            patterns.append("ACCELERAZIONE");why.append("Accelerazione: la variazione più recente è molto più ampia della precedente.")
        elif ratio<=.52 and abs(prior)>=.65*scale:
            patterns.append("RALLENTAMENTO");why.append("Rallentamento: la variazione più recente si è nettamente attenuata.")
    lscale=robust_scale(hist)
    zlevel=abs(vals[-1]-np.median(hist))/lscale if len(hist)>=3 and lscale>1e-9 else 0.0
    if zlevel>=2.4 or z>=2.7:
        patterns.append("ANOMALIA");why.append("Anomalia: livello o variazione oltre la soglia robusta PULSE.")
    patterns=list(dict.fromkeys(patterns))
    if not patterns:return None
    score=45+min(22,z*4.2)+min(12,zlevel*2.0)
    score+=9 if any(x.startswith("RECORD") for x in patterns) else 0
    score+=8 if "INVERSIONE" in patterns else 0
    score+=7 if "ANOMALIA" in patterns else 0
    score=min(99,score)
    last,prev=series[-1],series[-2]
    movement="sale" if last.value>prev.value else "scende" if last.value<prev.value else "resta stabile"
    municipality,province,region=_location(last)
    eid=hashlib.sha256(
        f"GREEN|{last.source_name}|{last.indicator}|{last.territory}|{last.period}".encode()
    ).hexdigest()[:18]
    return {
        "id":eid,"municipality_code":last.municipality_code,
        "municipality":municipality,"province":province,"region":region,
        "indicator":last.indicator,"patterns":"|".join(patterns),"scope":"GREEN",
        "score":round(score,1),"validation_status":"SEGNALE GREEN — DATO UFFICIALE",
        "period":str(last.period),
        "summary":f"{last.territory}: {last.indicator} {movement} da {fmt(prev.value,last.unit)} a {fmt(last.value,last.unit)} ({last.period}).",
        "annual":"|".join(format(float(x.value),".8g") for x in series[-20:]),
        "rolling12":"","benchmark_local":"","benchmark_rest":"",
        "analysis":"¦".join(
            [f"GREEN_PILLAR:{last.pillar}"]+why+
            ([last.note] if last.note else [])+
            [f"Serie ufficiale: {len(series)} osservazioni; ultimo periodo {last.period}."]
        ),
        "source_family":last.source_name,"source_url":last.source_url
    }

def build_divergence_events(observations:list[Observation]):
    # One cross-sectional signal per extreme territory per indicator/period/level.
    groups=defaultdict(list)
    for o in observations:
        if o.territory_level not in {"REGIONE","PROVINCIA","COMUNE"}: continue
        groups[(o.source_name,o.indicator,o.period,o.territory_level,o.pillar)].append(o)
    events=[]
    for key,rows in groups.items():
        if len(rows)<5: continue
        vals=np.array([r.value for r in rows],dtype=float)
        med=float(np.median(vals)); scale=robust_scale(vals)
        if scale<=1e-9:continue
        ranked=sorted(rows,key=lambda r:abs(r.value-med)/scale,reverse=True)[:2]
        for o in ranked:
            z=abs(o.value-med)/scale
            if z<2.0:continue
            score=min(96.0,55+z*8)
            municipality,province,region=_location(o)
            eid=hashlib.sha256(
                f"GREEN-DIV|{o.source_name}|{o.indicator}|{o.period}|{o.territory}".encode()
            ).hexdigest()[:18]
            events.append({
                "id":eid,"municipality_code":o.municipality_code,
                "municipality":municipality,"province":province,"region":region,
                "indicator":o.indicator,"patterns":"DIVERGENZA","scope":"GREEN",
                "score":round(score,1),"validation_status":"SEGNALE GREEN — DIVERGENZA TERRITORIALE",
                "period":str(o.period),
                "summary":f"{o.territory}: {o.indicator} è distante dal valore mediano dei territori comparabili ({fmt(o.value,o.unit)} vs {fmt(med,o.unit)}).",
                "annual":format(float(o.value),".8g"),"rolling12":"",
                "benchmark_local":format(float(o.value),".8g"),
                "benchmark_rest":format(float(med),".8g"),
                "analysis":"¦".join([
                    f"GREEN_PILLAR:{o.pillar}",
                    f"Divergenza territoriale robusta: scarto {z:.2f} scale MAD dalla mediana.",
                    o.note or "Confronto tra territori omogenei nello stesso periodo."
                ]),
                "source_family":o.source_name,"source_url":o.source_url
            })
    return events

def events_from_observations(observations:list[Observation]):
    grouped=defaultdict(list)
    for o in observations:
        key=(o.source_name,o.pillar,o.indicator,o.territory_level,o.territory,o.region,o.province,o.municipality_code)
        grouped[key].append(o)
    events=[]
    for series in grouped.values():
        e=build_temporal_event(series)
        if e:events.append(e)
    events.extend(build_divergence_events(observations))
    # Stable ranking, avoid flooding mobile UI.
    unique={e["id"]:e for e in events}
    return sorted(unique.values(),key=lambda e:(-float(e["score"]),e["source_family"],e["indicator"]))[:240]

def observations_frame(items:Iterable[Observation]):
    return pd.DataFrame([asdict(x) for x in items],columns=OBS_COLUMNS)

def events_frame(events:list[dict]):
    return pd.DataFrame(events,columns=EVENT_COLUMNS)
