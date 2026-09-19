#!/usr/bin/env python3
"""
Generate national PULSE signals from a curated set of official IstatData SDMX
series. Every configured series is monitored even when it does not emit a
signal on the latest observation; that coverage is written to metadata and is
used by the future "Fonti" section of the Android app.
"""
from __future__ import annotations

import hashlib
import json
import math
import urllib.request
import time
import xml.etree.ElementTree as ET
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

import numpy as np
import pandas as pd

BASE = "https://esploradati.istat.it/SDMXWS/rest/v1/data"
OUT = Path("app/src/main/assets/pulse_events_sdmx.tsv")
META = Path("app/src/main/assets/pulse_sdmx_meta.json")
CATALOG = Path("app/src/main/assets/sources_catalog.json")

COLUMNS = [
    "id","municipality_code","municipality","province","region","indicator",
    "patterns","scope","score","validation_status","period","summary","annual",
    "rolling12","benchmark_local","benchmark_rest","analysis","source_family","source_url",
]

# Curated current series chosen from the official ISTATData catalogue.
# "required" contains dimensions that must match; "preferred" only helps choose
# the most aggregate/headline series when a dataflow exposes many variants.
DATASETS = [
    {
        "area":"Prezzi e consumi",
        "name":"Prezzi al consumo NIC",
        "provides":"Indice generale mensile dei prezzi al consumo per l'intera collettività.",
        "flow":"167_745_DF_DCSP_NIC1B2025_1","start":"2026",
        "required":{"FREQ":"M","REF_AREA":"IT","ECOICOP_2":"00"},
        "preferred":{"DATA_TYPE":"85","MEASURE":"4"},
        "note":"Indice generale NIC, base 2025.",
    },
    {
        "area":"Lavoro e redditi",
        "name":"Tasso di disoccupazione",
        "provides":"Tasso di disoccupazione mensile nazionale.",
        "flow":"151_874_DF_DCCV_TAXDISOCCUMENS1_1","start":"2024",
        "required":{"FREQ":"M","REF_AREA":"IT","DATA_TYPE":"UNEM_R","SEX":"9","AGE":"Y15-74"},
        "preferred":{"ADJUSTMENT":"N"},
        "note":"Tasso di disoccupazione, popolazione 15-74 anni, totale sesso.",
    },
    {
        "area":"Lavoro e redditi",
        "name":"Tasso di occupazione",
        "provides":"Tasso di occupazione mensile nazionale.",
        "flow":"150_872_DF_DCCV_TAXOCCUMENS1_1","start":"2024",
        "required":{"FREQ":"M","REF_AREA":"IT","DATA_TYPE":"EMP_R","SEX":"9","AGE":"Y15-64"},
        "preferred":{"ADJUSTMENT":"N"},
        "note":"Tasso di occupazione, popolazione 15-64 anni, totale sesso.",
    },
    {
        "area":"Lavoro e redditi",
        "name":"Occupati",
        "provides":"Numero mensile di occupati a livello nazionale.",
        "flow":"150_875_DF_DCCV_OCCUPATIMENS1_1","start":"2024",
        "required":{"FREQ":"M","REF_AREA":"IT","DATA_TYPE":"EMP","SEX":"9","AGE":"Y15-89"},
        "preferred":{"ADJUSTMENT":"N"},
        "note":"Occupati mensili, totale sesso, 15-89 anni; viene scelta la combinazione più aggregata disponibile.",
    },
    {
        "area":"Lavoro e redditi",
        "name":"Posizioni lavorative dipendenti",
        "provides":"Indice trimestrale delle posizioni lavorative dipendenti.",
        "flow":"149_577_DF_DCSC_OROS_1_3","start":"2022",
        "required":{"FREQ":"Q","REF_AREA":"IT","DATA_TYPE":"FT_EMPL_2"},
        "preferred":{"ADJUSTMENT":"N"},
        "note":"Posizioni lavorative alle dipendenze, base 2021; viene scelta la branca più aggregata disponibile.",
    },
    {
        "area":"Imprese",
        "name":"Produzione industriale",
        "provides":"Indice mensile della produzione industriale, base 2021.",
        "flow":"115_333_DF_DCSC_INDXPRODIND_1_6","start":"2022",
        "required":{"FREQ":"M","REF_AREA":"IT"},
        "preferred":{"ADJUSTMENT":"Y"},
        "note":"Indice della produzione industriale, base 2021; serie nazionale più aggregata disponibile.",
    },
    {
        "area":"Imprese",
        "name":"Fatturato industriale",
        "provides":"Indice mensile del valore del fatturato industriale, base 2021.",
        "flow":"114_191_DF_DCSC_ORDFATT_9","start":"2022",
        "required":{"FREQ":"M","REF_AREA":"IT"},
        "preferred":{"ADJUSTMENT":"Y","MARKET":"T"},
        "note":"Valore del fatturato industriale, base 2021; serie nazionale più aggregata disponibile.",
    },
    {
        "area":"Imprese",
        "name":"Fatturato dei servizi",
        "provides":"Indice mensile del fatturato dei servizi, base 2021.",
        "flow":"119_367_DF_DCSC_FATTSERVIZ_1_4","start":"2022",
        "required":{"FREQ":"M","REF_AREA":"IT"},
        "preferred":{"ADJUSTMENT":"Y"},
        "note":"Indice del fatturato dei servizi, base 2021; serie nazionale più aggregata disponibile.",
    },
    {
        "area":"Prezzi e consumi",
        "name":"Vendite al dettaglio",
        "provides":"Indice mensile del volume delle vendite al dettaglio, base 2021.",
        "flow":"120_337_DF_DCSC_COMMDET_1_15","start":"2022",
        "required":{"FREQ":"M","REF_AREA":"IT"},
        "preferred":{"ADJUSTMENT":"Y"},
        "note":"Volume delle vendite del commercio al dettaglio, base 2021; totale prodotti quando disponibile.",
    },
    {
        "area":"Imprese",
        "name":"Clima di fiducia delle imprese",
        "provides":"Indice mensile sintetico del clima di fiducia delle imprese.",
        "flow":"6_64_DF_DCSC_IESI_2","start":"2022",
        "required":{"FREQ":"M","REF_AREA":"IT"},
        "preferred":{"ADJUSTMENT":"Y"},
        "note":"Clima di fiducia delle imprese, base 2021.",
    },
    {
        "area":"Imprese",
        "name":"Fiducia delle costruzioni",
        "provides":"Indice mensile di fiducia delle imprese delle costruzioni.",
        "flow":"111_40","start":"2022",
        "required":{
            "FREQ":"M","REF_AREA":"IT","DATA_TYPE":"CLIMACOS_21",
            "ECON_ACTIVITY_NACE_2007":"F","PERS_EMPL_SIZE_CLASS":"TOTAL"
        },
        "preferred":{"ADJUSTMENT":"Y"},
        "note":"Clima di fiducia del settore costruzioni, totale settore.",
    },
    {
        "area":"Imprese",
        "name":"Fiducia del commercio",
        "provides":"Indice mensile di fiducia delle imprese del commercio al dettaglio.",
        "flow":"117_266","start":"2022",
        "required":{
            "FREQ":"M","REF_AREA":"IT","DATA_TYPE":"CLIMACOM_21",
            "ECON_ACTIVITY_NACE_2007":"45_47_X46","TYPE_OF_SALES":"9"
        },
        "preferred":{"ADJUSTMENT":"Y"},
        "note":"Clima di fiducia del commercio al dettaglio, aggregato totale.",
    },
    {
        "area":"Prezzi e consumi",
        "name":"Fiducia dei consumatori",
        "provides":"Indice mensile del clima di fiducia dei consumatori.",
        "flow":"30_264","start":"2022",
        "required":{"FREQ":"M","REF_AREA":"IT"},
        "preferred":{"ADJUSTMENT":"Y","DATA_TYPE":"CLIMACONS_21"},
        "note":"Clima di fiducia dei consumatori; serie nazionale sintetica più aggregata disponibile.",
    },
    {
        "area":"Prezzi e consumi",
        "name":"Prezzi alla produzione dell'industria",
        "provides":"Indice mensile dei prezzi alla produzione dell'industria, base 2021.",
        "flow":"145_360_DF_DCSC_PREZZPIND_1_4","start":"2022",
        "required":{"FREQ":"M","REF_AREA":"IT","DATA_TYPE":"IND_PRIC_2021"},
        "preferred":{"ADJUSTMENT":"N","MARKET":"T"},
        "note":"Prezzi alla produzione dell'industria, base 2021; aggregato nazionale più ampio disponibile.",
    },
    {
        "area":"Prezzi e consumi",
        "name":"Prezzi all'importazione",
        "provides":"Indice mensile dei prezzi all'importazione, base 2021.",
        "flow":"143_222_DF_DCSC_PREIMPIND_2","start":"2022",
        "required":{"FREQ":"M","REF_AREA":"IT","DATA_TYPE":"IND_IMPPRIC_2021","MARKET":"T"},
        "preferred":{"ADJUSTMENT":"N"},
        "note":"Prezzi all'importazione, base 2021; aggregato nazionale più ampio disponibile.",
    },
    {
        "area":"Turismo e mobilità",
        "name":"Arrivi turistici",
        "provides":"Arrivi mensili negli esercizi ricettivi italiani.",
        "flow":"122_54_DF_DCSC_TUR_3","start":"2022",
        "required":{
            "FREQ":"M","REF_AREA":"IT","DATA_TYPE":"AR","ADJUSTMENT":"N",
            "TYPE_ACCOMMODATION":"ALL","ECON_ACTIVITY_NACE_2007":"551_553",
            "COUNTRY_RES_GUESTS":"WORLD","LOCALITY_TYPE":"ALL",
            "URBANIZ_DEGREE":"ALL","COASTAL_AREA":"ALL","SIZE_BY_NUMBER_ROOMS":"TOT"
        },
        "preferred":{},
        "note":"Arrivi mensili complessivi negli esercizi ricettivi, ospiti residenti e non residenti.",
    },
    {
        "area":"Turismo e mobilità",
        "name":"Presenze turistiche",
        "provides":"Presenze mensili negli esercizi ricettivi italiani.",
        "flow":"122_54_DF_DCSC_TUR_3","start":"2022",
        "required":{
            "FREQ":"M","REF_AREA":"IT","DATA_TYPE":"NI","ADJUSTMENT":"N",
            "TYPE_ACCOMMODATION":"ALL","ECON_ACTIVITY_NACE_2007":"551_553",
            "COUNTRY_RES_GUESTS":"WORLD","LOCALITY_TYPE":"ALL",
            "URBANIZ_DEGREE":"ALL","COASTAL_AREA":"ALL","SIZE_BY_NUMBER_ROOMS":"TOT"
        },
        "preferred":{},
        "note":"Presenze mensili complessive negli esercizi ricettivi, ospiti residenti e non residenti.",
    },
]

TOTALISH = {
    "9","ALL","TOT","TOTAL","WORLD","T","00","0000","0010",
    "45_47_X46","551_553","B-D","B_E","B-E","B_S_X_O","B-S_X-O"
}

def local(tag: str) -> str:
    return tag.rsplit("}",1)[-1]

def fetch(dataset: dict) -> tuple[bytes,str]:
    flow=dataset["flow"]; start=dataset["start"]
    url=f"{BASE}/{flow}/all/IT1?startPeriod={start}&endPeriod=2026"
    req=urllib.request.Request(
        url,
        headers={
            "User-Agent":"ISTAT-PULSE/0.6",
            "Accept":"application/vnd.sdmx.genericdata+xml;version=2.1",
        },
    )
    last=None
    for attempt in range(1,4):
        try:
            with urllib.request.urlopen(req,timeout=240) as response:
                return response.read(),url
        except Exception as exc:
            last=exc
            if attempt<3:
                time.sleep(3*attempt)
    raise last

def parse_series(raw: bytes) -> list[dict]:
    root=ET.fromstring(raw)
    out=[]
    for series in root.iter():
        if local(series.tag)!="Series":
            continue
        key={}; obs=[]
        for child in series:
            t=local(child.tag)
            if t=="SeriesKey":
                key={v.attrib.get("id",""):v.attrib.get("value","") for v in child}
            elif t=="Obs":
                period=value=None
                for v in child:
                    vt=local(v.tag)
                    if vt=="ObsDimension":
                        period=v.attrib.get("value")
                    elif vt=="ObsValue":
                        value=v.attrib.get("value")
                if period and value:
                    try: obs.append((period,float(value)))
                    except ValueError: pass
        if obs:
            obs.sort(key=lambda x:x[0])
            out.append({"key":key,"obs":obs})
    return out

def _candidate_score(series: dict,dataset: dict) -> tuple:
    key=series["key"]
    preferred=dataset.get("preferred",{})
    pscore=0
    for dim,wanted in preferred.items():
        actual=key.get(dim)
        if actual==wanted:
            pscore+=30
        elif actual is not None:
            pscore-=3
    for dim,val in key.items():
        if dim in {"FREQ","REF_AREA","DATA_TYPE","ADJUSTMENT","EDITION"}:
            continue
        if val in TOTALISH:
            pscore+=3
    # Prefer adjusted headline series when not explicitly constrained.
    if "ADJUSTMENT" not in preferred:
        pscore += {"Y":3,"S":2,"N":1}.get(key.get("ADJUSTMENT"),0)
    latest=series["obs"][-1][0]
    edition=key.get("EDITION","")
    return (latest,pscore,edition,len(series["obs"]))

def choose_series(series: list[dict],dataset: dict) -> dict|None:
    required=dataset.get("required",{})
    candidates=[]
    for s in series:
        key=s["key"]
        if all(key.get(k)==v for k,v in required.items()):
            candidates.append(s)
    if not candidates:
        return None
    return max(candidates,key=lambda s:_candidate_score(s,dataset))

def robust_scale(values) -> float:
    a=np.asarray(values,dtype=float)
    a=a[np.isfinite(a)]
    if len(a)<3:
        return 0.0
    med=np.median(a)
    mad=np.median(np.abs(a-med))*1.4826
    if mad>1e-9:
        return float(mad)
    sd=float(np.std(a))
    return sd if sd>1e-9 else 0.0

def fmt(v: float) -> str:
    if abs(v)>=1_000_000:
        return f"{v/1_000_000:.2f} mln".replace(".",",")
    if abs(v)>=10_000:
        return f"{v:,.0f}".replace(",",".")
    return f"{v:.2f}".rstrip("0").rstrip(".").replace(".",",")

def build_event(dataset: dict,chosen: dict,source_url: str) -> dict|None:
    obs=chosen["obs"][-30:]
    if len(obs)<6:
        return None
    periods=[p for p,_ in obs]
    values=np.array([v for _,v in obs],dtype=float)
    deltas=np.diff(values)
    latest_delta=float(deltas[-1]); prior_delta=float(deltas[-2])
    scale=robust_scale(deltas[:-1])
    if scale<=1e-9:
        scale=max(abs(float(np.median(values)))*0.002,1e-6)
    z=abs(latest_delta)/scale

    patterns=[]; analysis=[]
    prior_window=values[max(0,len(values)-13):-1]
    if len(prior_window)>=5 and values[-1]>np.max(prior_window) and z>=0.5:
        patterns.append("RECORD_MAX")
        analysis.append("Record: l'ultimo valore supera i dodici periodi precedenti disponibili.")
    elif len(prior_window)>=5 and values[-1]<np.min(prior_window) and z>=0.5:
        patterns.append("RECORD_MIN")
        analysis.append("Record: l'ultimo valore è inferiore ai dodici periodi precedenti disponibili.")

    if latest_delta*prior_delta<0 and z>=0.8:
        patterns.append("INVERSIONE")
        analysis.append("Inversione: l'ultima variazione cambia segno rispetto alla precedente.")
    elif latest_delta*prior_delta>0 and abs(prior_delta)>1e-9:
        ratio=abs(latest_delta)/abs(prior_delta)
        if ratio>=1.7 and z>=0.9:
            patterns.append("ACCELERAZIONE")
            analysis.append("Accelerazione: l'ultima variazione è nettamente più ampia della precedente.")
        elif ratio<=0.5 and abs(prior_delta)>=0.7*scale:
            patterns.append("RALLENTAMENTO")
            analysis.append("Rallentamento: l'ultima variazione è nettamente più contenuta della precedente.")

    level_hist=values[max(0,len(values)-13):-1]
    lscale=robust_scale(level_hist)
    zlevel=abs(values[-1]-np.median(level_hist))/lscale if lscale>1e-9 and len(level_hist)>=5 else 0.0
    if zlevel>=2.5 or z>=2.75:
        patterns.append("ANOMALIA")
        analysis.append("Anomalia: l'ultimo livello o la sua variazione supera la soglia robusta PULSE.")

    patterns=list(dict.fromkeys(patterns))
    if not patterns:
        return None

    score=48.0+min(20.0,z*4.0)+min(10.0,zlevel*2.0)
    score+=10 if any(p.startswith("RECORD") for p in patterns) else 0
    score+=8 if "INVERSIONE" in patterns else 0
    score+=8 if "ANOMALIA" in patterns else 0
    score+=5 if ("ACCELERAZIONE" in patterns or "RALLENTAMENTO" in patterns) else 0
    score=min(99.0,score)

    prev,cur=values[-2],values[-1]
    movement="sale" if cur>prev else "scende" if cur<prev else "resta stabile"
    summary=f"Italia: {dataset['name']} {movement} da {fmt(prev)} a {fmt(cur)} nel periodo {periods[-1]}."
    analysis.append(dataset["note"])
    analysis.append(f"PULSE Score: {score:.1f}/100. Fonte: IstatData SDMX, ISTAT.")
    event_id=hashlib.sha256(
        f"SDMX|{dataset['flow']}|{dataset['name']}|{periods[-1]}".encode()
    ).hexdigest()[:16]
    return {
        "id":event_id,
        "municipality_code":f"SDMX-IT-{dataset['flow']}",
        "municipality":"Italia","province":"","region":"Italia",
        "indicator":dataset["name"],"patterns":"|".join(patterns),"scope":"GENERAL",
        "score":round(score,1),"validation_status":"SEGNALE PULSE — ISTATDATA",
        "period":periods[-1],"summary":summary,"annual":"",
        "rolling12":"|".join(f"{v:.6g}" for v in values),
        "benchmark_local":"","benchmark_rest":"","analysis":"¦".join(analysis),
        "source_family":"IstatData SDMX — ISTAT","source_url":source_url,
    }

def main():
    # Fetch each unique flow/start once, concurrently.
    unique={}
    for d in DATASETS:
        unique[(d["flow"],d["start"])]=d
    fetched={}
    with ThreadPoolExecutor(max_workers=4) as pool:
        futures={pool.submit(fetch,d):key for key,d in unique.items()}
        for future in as_completed(futures):
            key=futures[future]
            try:
                raw,url=future.result()
                fetched[key]=(raw,url,parse_series(raw),None)
                print(f"FETCH {key[0]}: {len(raw):,} bytes")
            except Exception as exc:
                fetched[key]=(b"","",[],repr(exc))
                print(f"FETCH ERROR {key[0]}: {exc!r}")

    events=[]; sources=[]
    for dataset in DATASETS:
        key=(dataset["flow"],dataset["start"])
        raw,url,parsed,error=fetched[key]
        chosen=choose_series(parsed,dataset) if not error else None
        status="ok"
        event=None
        if error:
            status="fetch_error"
            print(f"SKIP {dataset['name']}: {error}")
        elif chosen is None:
            status="series_not_found"
            print(f"SKIP {dataset['name']}: aggregate series not found.")
        else:
            event=build_event(dataset,chosen,url)
            if event:
                events.append(event)
                print(f"SIGNAL {dataset['name']} -> {event['period']} score {event['score']}")
            else:
                status="monitored_no_signal"
                print(f"MONITORED {dataset['name']} -> {chosen['obs'][-1][0]} (no current signal)")

        sources.append({
            "area":dataset["area"],
            "name":dataset["name"],
            "provides":dataset["provides"],
            "flow":dataset["flow"],
            "url":url or f"{BASE}/{dataset['flow']}/all/IT1",
            "status":status,
            "bytes":len(raw),
            "sha256":hashlib.sha256(raw).hexdigest() if raw else "",
            "latest_period":chosen["obs"][-1][0] if chosen else "",
            "series_key":chosen["key"] if chosen else {},
            "signal_emitted":bool(event),
        })

    OUT.parent.mkdir(parents=True,exist_ok=True)
    pd.DataFrame(events,columns=COLUMNS).to_csv(OUT,sep="\t",index=False)
    def period_key(value: str):
        value=str(value or "")
        if "-Q" in value:
            year,q=value.split("-Q",1)
            return (int(year),int(q)*3,0)
        if "-" in value:
            year,month=value.split("-",1)[:2]
            try:
                return (int(year),int(month),1)
            except ValueError:
                pass
        try:
            return (int(value),12,0)
        except ValueError:
            return (0,0,0)

    latest_period=max(
        (s["latest_period"] for s in sources if s["latest_period"]),
        key=period_key,
        default="",
    )
    meta={
        "source_family":"IstatData SDMX — ISTAT",
        "events":len(events),
        "monitored_series":len(DATASETS),
        "connected_series":sum(1 for s in sources if s["status"] in {"ok","monitored_no_signal"}),
        "sources":sources,
        "latest_period":latest_period,
    }
    META.write_text(json.dumps(meta,ensure_ascii=False,indent=2),encoding="utf-8")

    # Backend catalogue already prepared for the future app section "Fonti".
    catalog={
        "version":1,
        "title":"Fonti dati di ISTAT PULSE",
        "sources":[
            {
                "name":"DEMO ISTAT — Bilancio demografico mensile",
                "level":"Comunale",
                "frequency":"Mensile",
                "provides":[
                    "Nati vivi","Morti","Immigrati da altro comune","Emigrati per altro comune",
                    "Immigrati dall'estero","Emigrati per l'estero"
                ],
                "official":True,
                "notes":"Fonte attiva nel feed corrente. I dati comunali più recenti possono essere indicati da ISTAT come provvisori."
            },
            {
                "name":"IstatData SDMX — ISTAT",
                "level":"Prevalentemente nazionale",
                "frequency":"Mensile e trimestrale",
                "provides":[
                    {"area":s["area"],"series":s["name"],"description":s["provides"],
                     "latest_period":s["latest_period"],"status":s["status"]}
                    for s in sources
                ],
                "official":True,
                "notes":"Fonte attiva nel feed corrente. Serie congiunturali ufficiali interrogate tramite servizio SDMX IstatData."
            },
        ],
    }

    # I portali storici e complementari restano accessibili come fonti:
    # non dichiariamo che alimentino il feed se non sono acquisiti dal Radar.
    urls = {
        "DEMO ISTAT": ("https://demo.istat.it/app/?i=D7B", "Attiva nel Radar · notizie riferite all'anno del fenomeno"),
        "IstatData SDMX": ("https://esploradati.istat.it/SDMXWS/", "Attiva nel Radar"),
    }
    for source in catalog["sources"]:
        for prefix, (url, status) in urls.items():
            if source["name"].startswith(prefix):
                source["url"] = url
                source["feed_status"] = status
    catalog["sources"].extend([
        {
            "name": "BES dei territori — ISTAT",
            "level": "Regionale e provinciale", "frequency": "Annuale",
            "provides": ["Benessere, salute, istruzione, lavoro, ambiente e qualità dei servizi."],
            "official": True,
            "url": "https://www.istat.it/comunicato-territoriale/il-benessere-equo-e-sostenibile-dei-territori-report-regionali-anno-2025/",
            "feed_status": "Archivio ufficiale consultabile · fuori dal feed corrente",
            "notes": "I dati annuali del 2024/2025 non vengono presentati come notizie attuali."
        },
        {
            "name": "A misura di Comune — ISTAT",
            "level": "Comunale, provinciale e regionale", "frequency": "Secondo indicatore",
            "provides": ["Indicatori socio-demografici, economici, ambientali e territoriali."],
            "official": True,
            "url": "https://www.istat.it/statistica-sperimentale/aggiornamento-degli-indicatori-del-sistema-informativo-a-misura-di-comune/",
            "feed_status": "Database consultabile · integrazione nel Radar da sviluppare",
            "notes": "Portale ufficiale esterno, non ancora acquisito automaticamente dalla pipeline."
        },
        {
            "name": "Noi Italia — ISTAT",
            "level": "Italia, regioni ed Europa", "frequency": "Annuale",
            "provides": ["Oltre 100 statistiche tematiche sull'Italia e sui suoi territori."],
            "official": True,
            "url": "https://noi-italia.istat.it/home.php",
            "feed_status": "Database consultabile · integrazione nel Radar da sviluppare",
            "notes": "Portale ufficiale esterno, non ancora acquisito automaticamente dalla pipeline."
        }
    ])
    CATALOG.write_text(json.dumps(catalog,ensure_ascii=False,indent=2),encoding="utf-8")

    print(f"IstatData monitored series: {len(DATASETS)}")
    print(f"IstatData connected series: {meta['connected_series']}")
    print(f"IstatData PULSE signals now: {len(events)}")
    print(f"Latest IstatData period: {meta['latest_period']}")
    print(f"Asset: {OUT}")

if __name__=="__main__":
    main()
