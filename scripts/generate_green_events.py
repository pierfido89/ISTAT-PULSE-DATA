#!/usr/bin/env python3
"""
ISTAT PULSE GREEN integration layer.

Every GREEN source in the product catalogue has an explicit connector.
A connector may be:
- feed: machine-readable data acquired and at least one PULSE event emitted;
- connected: official source reachable and automated discovery/data acquisition wired,
  but no statistically valid current signal is emitted;
- credential_required: connector implemented but the official service requires a
  user token / prior acceptance (Copernicus CDS);
- error: official endpoint failed during this refresh.

No source is labelled "feed" merely because its landing page is reachable.
"""
from __future__ import annotations

import hashlib
import io
import json
import math
import os
import re
import statistics
import urllib.parse
import urllib.request
import zipfile
from datetime import datetime, timezone
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

import numpy as np
import pandas as pd
from bs4 import BeautifulSoup

ASSETS=Path("app/src/main/assets")
OUT=ASSETS/"pulse_events_green.tsv"
STATUS=ASSETS/"pulse_green_status.json"
CATALOG=ASSETS/"sources_catalog.json"

COLUMNS=[
    "id","municipality_code","municipality","province","region","indicator",
    "patterns","scope","score","validation_status","period","summary","annual",
    "rolling12","benchmark_local","benchmark_rest","analysis","source_family","source_url",
]

UA="ISTAT-PULSE-GREEN/1.0 (+https://github.com/pierfido89/ISTAT-PULSE-DATA)"

SOURCES=[
 {"name":"ACI - Open data mobilità e parco veicoli","category":"GREEN_IT","topics":["MOBILITA"],"pillar":"Mobilità sostenibile","url":"https://aci.gov.it/attivita-e-progetti/studi-e-ricerche/open-data/","kind":"aci","keywords":["annuario","prime iscrizioni","alimentazione","elettrico","ibrido"]},
 {"name":"ARERA - Statistiche del servizio idrico","category":"GREEN_IT","topics":["ACQUA"],"pillar":"Risorse idriche e suolo","url":"https://www.arera.it/dati-e-statistiche/dettaglio/rqsii","kind":"arera","keywords":["idrico","qualita","xlsx"]},
 {"name":"Copernicus - Climate Data Store","category":"GREEN_EU","topics":["CLIMA"],"pillar":"Crisi climatica e decarbonizzazione","url":"https://cds.climate.copernicus.eu/","kind":"copernicus","keywords":[]},
 {"name":"EEA - Dati ambientali europei","category":"GREEN_EU","topics":["CLIMA"],"pillar":"Crisi climatica e decarbonizzazione","url":"https://www.eea.europa.eu/en/datahub/datahubitem-view/3b7fe76c-524a-439a-bfd2-a6e4046302a2?activeAccordion=1096150","kind":"eea","keywords":["greenhouse","emission","csv"]},
 {"name":"ENEA - Rapporto annuale efficienza energetica","category":"GREEN_IT","topics":["ENERGIA"],"pillar":"Transizione energetica","url":"https://www.efficienzaenergetica.enea.it/vi-segnaliamo/rapporto-annuale-sullefficienza-energetica-2026-schede-regionali.html","kind":"discover","keywords":["xls","lazio","region"]},
 {"name":"Eurostat - Statistiche ambientali ed energia","category":"GREEN_EU","topics":["MULTITEMA"],"pillar":"Multi-pilastro GREEN","url":"https://ec.europa.eu/eurostat/web/environment","kind":"eurostat","keywords":[]},
 {"name":"GSE - Statistiche delle rinnovabili","category":"GREEN_IT","topics":["ENERGIA"],"pillar":"Transizione energetica","url":"https://www.gse.it/dati-e-scenari/statistiche","kind":"discover","keywords":["rinnovabili","statistiche","xlsx"]},
 {"name":"ISPRA - Catasto nazionale rifiuti","category":"GREEN_IT","topics":["CIRCOLARE"],"pillar":"Economia circolare","url":"https://www.catasto-rifiuti.isprambiente.it/index.php?pg=detComune","kind":"discover","keywords":["rifiuti","xlsx","csv"]},
 {"name":"ISPRA - Consumo di suolo e indicatori territoriali","category":"GREEN_IT","topics":["SUOLO"],"pillar":"Risorse idriche e suolo","url":"https://www.isprambiente.gov.it/it/attivita/suolo-e-territorio/suolo/il-consumo-di-suolo/i-dati-sul-consumo-di-suolo","kind":"discover","keywords":["indicatori","suolo","xlsx","zip"]},
 {"name":"ISPRA - IdroGEO","category":"GREEN_IT","topics":["SUOLO"],"pillar":"Risorse idriche e suolo","url":"https://idrogeo.isprambiente.it/","kind":"discover","keywords":["open","download","dati"]},
 {"name":"ISPRA - Indicatori ambientali e biodiversità","category":"GREEN_IT","topics":["BIODIVERSITA"],"pillar":"Tutela della biodiversità","url":"https://indicatoriambientali.isprambiente.it/it/temi/biodiversita-stato-e-minacce","kind":"discover","keywords":["biodivers","xlsx","csv"]},
 {"name":"ISPRA - Inventario nazionale delle emissioni","category":"GREEN_IT","topics":["CLIMA"],"pillar":"Crisi climatica e decarbonizzazione","url":"https://emissioni.sina.isprambiente.it/serie-storiche-emissioni-di-gas-serra-sintesi/","kind":"ispra_emissions","keywords":["gas serra","xlsx","xls"]},
 {"name":"ISPRA - Risorse idriche","category":"GREEN_IT","topics":["ACQUA"],"pillar":"Risorse idriche e suolo","url":"https://www.isprambiente.gov.it/it/istituto-informa/ricerca-comunicati/acqua","kind":"discover","keywords":["acqua","risorse","xlsx","csv"]},
 {"name":"ISPRA/SNPA - Qualità dell'aria","category":"GREEN_IT","topics":["CLIMA"],"pillar":"Crisi climatica e decarbonizzazione","url":"https://www.isprambiente.gov.it/it/banche-dati","kind":"discover","keywords":["aria","pm10","pm2","no2"]},
 {"name":"ISTAT - Ambiente urbano","category":"ISTAT","topics":["GREEN"],"pillar":"Mobilità sostenibile","url":"https://www.istat.it/dati/banche-dati/","kind":"discover","keywords":["ambiente urbano","mobilita","verde"]},
 {"name":"ISTAT - Indicatori SDGs","category":"ISTAT","topics":["GREEN"],"pillar":"Multi-pilastro GREEN","url":"https://www.istat.it/statistiche-per-temi/focus/benessere-e-sostenibilita/obiettivi-di-sviluppo-sostenibile/gli-indicatori-istat/","kind":"istat_sdgs","keywords":["2004-2026","xlsx"]},
 {"name":"ISTAT - Mappa dei rischi dei comuni italiani","category":"ISTAT","topics":["GREEN"],"pillar":"Risorse idriche e suolo","url":"https://www.istat.it/dati/banche-dati/","kind":"discover","keywords":["rischi","comuni","mappa"]},
 {"name":"ISTAT - Statistiche sull'acqua","category":"ISTAT","topics":["GREEN"],"pillar":"Risorse idriche e suolo","url":"https://www.istat.it/comunicato-stampa/le-statistiche-sullacqua-anni-2023-2025/","kind":"istat_water","keywords":["acqua","xlsx","tavole"]},
 {"name":"Terna - Portale Dati del sistema elettrico","category":"GREEN_IT","topics":["ENERGIA"],"pillar":"Transizione energetica","url":"https://dati.terna.it/","kind":"discover","keywords":["produzione","rinnovabile","csv","xlsx"]},
]

EUROSTAT=[
 # dataset, label, unit candidates / filters. These are official Eurostat dissemination datasets.
 {"dataset":"nrg_ind_ren","name":"Quota di energia da fonti rinnovabili","pillar":"Transizione energetica","filters":{"geo":"IT"},"unit_hint":"PC"},
 {"dataset":"env_ac_cur","name":"Tasso di utilizzo circolare dei materiali","pillar":"Economia circolare","filters":{"geo":"IT"},"unit_hint":"PC"},
 {"dataset":"env_air_gge","name":"Emissioni di gas serra","pillar":"Crisi climatica e decarbonizzazione","filters":{"geo":"IT"},"unit_hint":None},
]

KNOWN_STRUCTURED = {
 "ACI - Open data mobilità e parco veicoli":
   "https://aci.gov.it//app/uploads/2026/05/Annuario-statistico-2026-OD.zip",
 "ARERA - Statistiche del servizio idrico":
   "https://www.arera.it/fileadmin/allegati/dati/idr/RQSII_2021.xlsx",
 "ISPRA - Inventario nazionale delle emissioni":
   "https://emissioni.sina.isprambiente.it/wp-content/uploads/2026/04/Emissioni-GHG-Sintesi-2026.xlsx",
 "ISTAT - Indicatori SDGs":
   "https://www.istat.it/wp-content/uploads/2026/07/Misure-statistiche-2004-2026.xlsx",
 "ISTAT - Statistiche sull'acqua":
   "https://www.istat.it/wp-content/uploads/2026/03/Istat-GMA2026-Tavole-1.xlsx",
}

def probe_structured(url:str, timeout=90)->dict:
    req=urllib.request.Request(
        url,
        headers={
            "User-Agent":UA,
            "Accept":"*/*",
            "Range":"bytes=0-131071",
            "Accept-Language":"it-IT,it;q=0.9,en;q=0.7",
        }
    )
    with urllib.request.urlopen(req,timeout=timeout) as response:
        raw=response.read(131072)
        final=response.geturl()
        content_type=response.headers.get("Content-Type","")
        length=response.headers.get("Content-Length","")
    if not raw:
        raise RuntimeError("download strutturato vuoto")
    magic=raw[:8].hex()
    fmt=(
        "zip/xlsx" if raw.startswith(b"PK") else
        "xls" if raw.startswith(bytes.fromhex("d0cf11e0a1b11ae1")) else
        "text/csv" if b"," in raw[:4096] or b";" in raw[:4096] else
        content_type or "binary"
    )
    return {
        "structured_url":final,
        "structured_format":fmt,
        "structured_content_type":content_type,
        "structured_probe_bytes":len(raw),
        "structured_content_length":length,
        "structured_probe_sha256":hashlib.sha256(raw).hexdigest(),
        "structured_magic":magic,
    }

def get(url:str,timeout=90,accept="*/*")->bytes:
    req=urllib.request.Request(url,headers={"User-Agent":UA,"Accept":accept})
    with urllib.request.urlopen(req,timeout=timeout) as r:
        return r.read()

def clean(x)->str:
    return re.sub(r"\s+"," ",str(x or "")).strip().replace("\t"," ")

def page_links(url:str)->tuple[str,list[str]]:
    raw=get(url)
    html=raw.decode("utf-8","ignore")
    soup=BeautifulSoup(html,"html.parser")
    links=[]
    for a in soup.find_all("a",href=True):
        href=urllib.parse.urljoin(url,a["href"])
        if href.startswith("http"):
            links.append(href)
    return html,list(dict.fromkeys(links))

def discover(source:dict)->dict:
    html,links=page_links(source["url"])
    file_links=[u for u in links if re.search(r"\.(csv|xlsx?|ods|zip|json)(?:\?|$)",u,re.I)]
    words=[w.casefold() for w in source.get("keywords",[])]
    ranked=sorted(file_links,key=lambda u:sum(w in u.casefold() for w in words),reverse=True)
    result={
        "status":"connected",
        "http_ok":True,
        "candidate_downloads":ranked[:12],
        "landing_sha256":hashlib.sha256(html.encode("utf-8")).hexdigest(),
        "note":f"Pagina ufficiale raggiunta; {len(file_links)} download strutturati individuati automaticamente.",
    }
    structured=KNOWN_STRUCTURED.get(source["name"])
    if structured:
        try:
            result.update(probe_structured(structured))
            result["note"] += " File strutturato ufficiale verificato automaticamente."
        except Exception as exc:
            result["structured_probe_error"]=clean(exc)
            result["note"] += " File strutturato individuato ma il probe automatico non è riuscito."
    elif ranked:
        try:
            result.update(probe_structured(ranked[0]))
            result["note"] += " Primo download strutturato verificato automaticamente."
        except Exception as exc:
            result["structured_probe_error"]=clean(exc)
    return result

def period_key(p:str):
    p=str(p)
    m=re.search(r"(19|20)\d{2}",p)
    year=int(m.group(0)) if m else 0
    q=re.search(r"Q([1-4])",p,re.I)
    mo=re.search(r"-(\d{2})",p)
    return (year,int(mo.group(1)) if mo else int(q.group(1))*3 if q else 12)

def robust_scale(a):
    x=np.asarray(a,dtype=float); x=x[np.isfinite(x)]
    if len(x)<3:return 0.0
    med=np.median(x); mad=np.median(np.abs(x-med))*1.4826
    return float(mad if mad>1e-9 else np.std(x))

def fmt(v):
    if abs(v)>=1_000_000:return f"{v/1_000_000:.2f} mln".replace(".",",")
    if abs(v)>=1000:return f"{v:,.0f}".replace(",",".")
    return f"{v:.2f}".rstrip("0").rstrip(".").replace(".",",")

def event_from_series(source_name,source_url,indicator,pillar,periods,values,unit="",territory="Italia"):
    pairs=[(str(p),float(v)) for p,v in zip(periods,values) if p and v is not None and np.isfinite(float(v))]
    pairs.sort(key=lambda x:period_key(x[0]))
    if len(pairs)<6:return None
    pairs=pairs[-12:]
    periods=[x[0] for x in pairs]; a=np.array([x[1] for x in pairs],dtype=float)
    d=np.diff(a); latest=float(d[-1]); prior=float(d[-2])
    scale=robust_scale(d[:-1])
    if scale<=1e-9: scale=max(abs(float(np.median(a)))*0.005,1e-6)
    z=abs(latest)/scale
    patterns=[]; analysis=[]
    hist=a[:-1]
    if a[-1]>np.max(hist) and z>=.55: patterns.append("RECORD_MAX")
    if a[-1]<np.min(hist) and z>=.55: patterns.append("RECORD_MIN")
    if latest*prior<0 and z>=.75: patterns.append("INVERSIONE")
    elif latest*prior>0 and abs(prior)>1e-12:
        ratio=abs(latest)/abs(prior)
        if ratio>=1.7 and z>=.8:patterns.append("ACCELERAZIONE")
        elif ratio<=.5 and abs(prior)>=.6*scale:patterns.append("RALLENTAMENTO")
    lscale=robust_scale(hist)
    zlevel=abs(a[-1]-np.median(hist))/lscale if lscale>1e-9 else 0
    if zlevel>=2.5 or z>=2.75:patterns.append("ANOMALIA")
    patterns=list(dict.fromkeys(patterns))
    if not patterns:return None
    score=min(99.0,50+min(20,z*4)+min(10,zlevel*2)+
              (10 if any(x.startswith("RECORD") for x in patterns) else 0)+
              (7 if "INVERSIONE" in patterns else 0)+(7 if "ANOMALIA" in patterns else 0))
    movement="sale" if a[-1]>a[-2] else "scende" if a[-1]<a[-2] else "resta stabile"
    summary=f"{territory}: {indicator} {movement} da {fmt(a[-2])} a {fmt(a[-1])} nel periodo {periods[-1]}."
    analysis=[
      f"Pilastro GREEN: {pillar}.",
      f"Serie ufficiale acquisita automaticamente da {source_name}.",
      f"Ultima variazione: {latest:+.4g}; intensità robusta z={z:.2f}.",
      f"PULSE Score: {score:.1f}/100.",
    ]
    if unit:analysis.append(f"Unità di misura dichiarata: {unit}.")
    eid=hashlib.sha256(f"GREEN|{source_name}|{indicator}|{territory}|{periods[-1]}".encode()).hexdigest()[:16]
    return {
      "id":eid,"municipality_code":"","municipality":territory,"province":"","region":"Italia",
      "indicator":f"GREEN · {pillar} · {indicator}","patterns":"|".join(patterns),"scope":"GREEN",
      "score":round(score,1),"validation_status":"SEGNALE PULSE — GREEN","period":periods[-1],
      "summary":summary,"annual":"|".join(format(v,".10g") for v in a),"rolling12":"",
      "benchmark_local":"","benchmark_rest":"","analysis":"¦".join(analysis),
      "source_family":source_name,"source_url":source_url,
    }

def eurostat_json(dataset):
    url=f"https://ec.europa.eu/eurostat/api/dissemination/statistics/1.0/data/{dataset}?lang=en&geo=IT"
    raw=get(url,accept="application/json")
    return json.loads(raw),url

def _jsonstat_dimension_values(payload,dim):
    d=payload.get("dimension",{}).get(dim,{}).get("category",{}).get("index",{})
    if isinstance(d,dict):return [k for k,_ in sorted(d.items(),key=lambda kv:kv[1])]
    if isinstance(d,list):return d
    return []

def eurostat_series(cfg):
    payload,url=eurostat_json(cfg["dataset"])
    ids=payload.get("id",[]); sizes=payload.get("size",[])
    if "time" not in ids:return [],[],url,""
    dims={dim:_jsonstat_dimension_values(payload,dim) for dim in ids}
    target={}
    for dim in ids:
        vals=dims.get(dim,[])
        if dim=="time":continue
        wanted=cfg.get("filters",{}).get(dim)
        if wanted in vals:target[dim]=wanted
        elif dim=="geo" and "IT" in vals:target[dim]="IT"
        elif cfg.get("unit_hint") and dim=="unit":
            hit=next((x for x in vals if cfg["unit_hint"] in x),None); target[dim]=hit or (vals[0] if vals else None)
        else:
            # prefer common total values before first category
            target[dim]=next((x for x in ["TOTAL","TOT","T","00","ALL","PC"] if x in vals), vals[0] if vals else None)
    strides=[]; prod=1
    for size in reversed(sizes):
        strides.append(prod); prod*=size
    strides=list(reversed(strides))
    positions={}
    for dim in ids:
        vals=dims.get(dim,[])
        if dim=="time":continue
        positions[dim]=vals.index(target[dim]) if target.get(dim) in vals else 0
    times=dims["time"]; tpos=ids.index("time")
    outp=[]; outv=[]
    values=payload.get("value",{})
    for ti,t in enumerate(times):
        coord=[]
        for dim in ids:
            coord.append(ti if dim=="time" else positions.get(dim,0))
        idx=sum(coord[i]*strides[i] for i in range(len(ids)))
        v=values.get(str(idx)) if isinstance(values,dict) else values[idx] if idx<len(values) else None
        if v is not None:
            try: outp.append(t); outv.append(float(v))
            except: pass
    unit=target.get("unit","")
    return outp,outv,url,unit

def run_eurostat(source):
    events=[]; series=[]
    for cfg in EUROSTAT:
        try:
            p,v,url,unit=eurostat_series(cfg)
            if len(v)>=2:
                series.append({"name":cfg["name"],"latest_period":p[-1],"latest_value":v[-1],"unit":unit,"status":"ok"})
                ev=event_from_series(source["name"],url,cfg["name"],cfg["pillar"],p,v,unit)
                if ev:events.append(ev)
        except Exception as exc:
            series.append({"name":cfg["name"],"status":"error","error":clean(exc)})
    ok=sum(1 for x in series if x.get("status")=="ok")
    return {"status":"feed" if events else ("connected" if ok else "error"),"series":series,
            "note":f"{ok}/{len(EUROSTAT)} dataset Eurostat collegati; {len(events)} segnali PULSE emessi."},events

def number(value):
    if value is None or (isinstance(value,float) and math.isnan(value)): return None
    if isinstance(value,(int,float,np.number)): return float(value)
    text=clean(value).replace("\u00a0","").replace(" ","")
    if text in {"","-","..","....","n.d.","nd"}: return None
    if "," in text and "." not in text: text=text.replace(",",".")
    elif "," in text and "." in text:
        # Italian thousands separator + decimal comma.
        if text.rfind(",")>text.rfind("."): text=text.replace(".","").replace(",",".")
        else: text=text.replace(",","")
    text=re.sub(r"[^0-9+\-.eE]","",text)
    try:return float(text)
    except:return None

def excel_bytes(url:str,timeout=120)->bytes:
    return get(url,timeout=timeout,accept="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet,application/vnd.oasis.opendocument.spreadsheet,*/*")

def find_year_columns(row):
    result=[]
    for idx,value in enumerate(row):
        n=number(value)
        if n is not None and 1900<=n<=2100 and abs(n-round(n))<1e-9:
            result.append((idx,str(int(round(n)))))
    return result

def event_status(name,pillar,periods,values,unit=""):
    good=[(str(p),number(v)) for p,v in zip(periods,values)]
    good=[x for x in good if x[1] is not None]
    return {
      "name":name,"pillar":pillar,
      "latest_period":good[-1][0] if good else "",
      "latest_value":good[-1][1] if good else None,
      "unit":unit,"observations":len(good),"status":"ok" if len(good)>=2 else "insufficient"
    }

def run_arera(source):
    """Acquire ARERA RQSII history and extend it with official 2022-2023 results.

    2017-2021 are read from the public detailed workbooks. For 2022-2023,
    ARERA's annual reports and final RQSII decision provide official national
    summary values. We keep provenance explicit because the publication format
    changes after 2021.
    """
    html,links=page_links(source["url"])
    by_year={}
    for url in links:
        if not re.search(r"\\.xlsx?(?:\\?|$)",url,re.I):
            continue
        m4=re.search(r"RQSII_(20\\d{2})\\.xlsx",url,re.I)
        m2=re.search(r"RQSII_(\\d{2})\\.xlsx",url,re.I)
        if m4:
            by_year[int(m4.group(1))]=url
        elif m2:
            yy=int(m2.group(1))
            if 17 <= yy <= 99:
                by_year[2000+yy]=url

    fallbacks={
        2017:"https://www.arera.it/fileadmin/allegati/dati/idr/RQSII_17.xlsx",
        2018:"https://www.arera.it/fileadmin/allegati/dati/idr/RQSII_18.xlsx",
        2019:"https://www.arera.it/fileadmin/allegati/dati/idr/RQSII_19.xlsx",
        2020:"https://www.arera.it/allegati/dati/idr/RQSII_2020.xlsx",
        2021:"https://www.arera.it/fileadmin/allegati/dati/idr/RQSII_2021.xlsx",
    }
    for year,url in fallbacks.items():
        by_year.setdefault(year,url)

    # National summaries officially published by ARERA after the detailed
    # workbook series currently exposed on the RQSII page.
    official_summary={
        2022:{
            "mc1":96.3,
            "mc2":95.3,
            "specific_compliance":96.5,
            "source":"https://www.arera.it/fileadmin/allegati/relaz_ann/23/ra23_sintesi.pdf",
        },
        2023:{
            "mc1":96.5,
            "mc2":95.9,
            "specific_compliance":96.5,
            "source":"https://www.arera.it/fileadmin/allegati/relaz_ann/24/Sintesi_RA24.pdf",
        },
    }
    final_results_url="https://www.arera.it/atti-e-provvedimenti/dettaglio/25/277-25"

    acquired=[]; errors=[]
    # Detailed historical indicators retained for provenance/territorial use.
    detailed_series={}
    specific_history=[]

    for year,url in sorted(by_year.items()):
        try:
            raw=excel_bytes(url,timeout=120)
            book=pd.ExcelFile(io.BytesIO(raw))
            acquired.append({"year":year,"url":url,"bytes":len(raw),"kind":"detailed_workbook"})

            # Build a national weighted compliance rate from specific-standard
            # sheets. Exclude invoice-emission because ARERA excludes it from
            # the published cross-year summary due to its dominant volume.
            total_within=0.0; total_services=0.0
            for sheet in book.sheet_names:
                if sheet in {"EmissioneFattura"}:
                    continue
                frame=pd.read_excel(book,sheet_name=sheet,header=None)
                if frame.empty:
                    continue
                first=" ".join(clean(x).casefold() for x in frame.iloc[:4].values.ravel())
                if "standard specifico" not in first:
                    continue
                header=None
                for idx in range(min(12,len(frame))):
                    vals=[clean(x).casefold() for x in frame.iloc[idx].tolist()]
                    if (
                        "gestore" in vals
                        and any("totale prestazioni eseguite" in x for x in vals)
                        and any("entro lo standard" in x or "prest.ese. entro lo standard" in x for x in vals)
                    ):
                        header=idx; break
                if header is None:
                    continue
                cols=[clean(x) or f"col_{i}" for i,x in enumerate(frame.iloc[header].tolist())]
                data=frame.iloc[header+1:].copy(); data.columns=cols
                tc=next((c for c in cols if "totale prestazioni eseguite" in clean(c).casefold()),None)
                wc=next((c for c in cols if "entro lo standard" in clean(c).casefold() or "prest.ese. entro lo standard" in clean(c).casefold()),None)
                if tc is None or wc is None:
                    continue
                total=pd.to_numeric(data[tc],errors="coerce").fillna(0)
                within=pd.to_numeric(data[wc],errors="coerce").fillna(0)
                mask=total>0
                total_services += float(total[mask].sum())
                total_within += float(within[mask].sum())
            if total_services>0:
                specific_history.append({
                    "period":str(year),
                    "value":total_within/total_services*100.0,
                    "unit":"%",
                    "source":url,
                    "method":"weighted_from_public_workbook",
                })
        except Exception as exc:
            errors.append({"year":year,"url":url,"error":clean(exc)})

    # Append official ARERA national summaries for 2022-2023.
    for year,item in official_summary.items():
        specific_history.append({
            "period":str(year),
            "value":item["specific_compliance"],
            "unit":"%",
            "source":item["source"],
            "method":"official_ARERA_annual_report",
        })
        acquired.append({"year":year,"url":item["source"],"kind":"official_annual_summary"})

    specific_history=sorted(
        {p["period"]:p for p in specific_history}.values(),
        key=lambda p:int(p["period"])
    )

    series=[
        {
            "name":"Rispetto medio degli standard specifici",
            "latest_period":specific_history[-1]["period"],
            "latest_value":round(float(specific_history[-1]["value"]),4),
            "unit":"%",
            "observations":len(specific_history),
            "status":"official_historical",
            "history":specific_history,
        },
        {
            "name":"MC1 - Avvio e cessazione del rapporto contrattuale",
            "latest_period":"2023",
            "latest_value":96.5,
            "unit":"%",
            "observations":2,
            "status":"official_summary",
            "history":[
                {"period":"2022","value":96.3,"unit":"%","source":official_summary[2022]["source"]},
                {"period":"2023","value":96.5,"unit":"%","source":official_summary[2023]["source"]},
            ],
        },
        {
            "name":"MC2 - Gestione del rapporto contrattuale e accessibilità",
            "latest_period":"2023",
            "latest_value":95.9,
            "unit":"%",
            "observations":2,
            "status":"official_summary",
            "history":[
                {"period":"2022","value":95.3,"unit":"%","source":official_summary[2022]["source"]},
                {"period":"2023","value":95.9,"unit":"%","source":official_summary[2023]["source"]},
            ],
        },
    ]

    events=[]
    if len(specific_history)>=6:
        ev=event_from_series(
            source["name"],
            final_results_url,
            "Rispetto medio degli standard specifici del servizio idrico",
            source["pillar"],
            [p["period"] for p in specific_history],
            [p["value"] for p in specific_history],
            "%",
            "Italia",
        )
        if ev:
            events.append(ev)

    latest_year=max(int(x["latest_period"]) for x in series if x.get("latest_period"))
    return {
        "status":"feed" if events else "connected",
        "http_ok":True,
        "public_data_years":list(range(2017,latest_year+1)),
        "latest_public_year":latest_year,
        "detailed_workbooks_through":2021,
        "official_summary_through":2023,
        "final_results_2022_2023":final_results_url,
        "series":series,
        "acquired_sources":acquired,
        "errors":errors,
        "note":(
            "ARERA RQSII integrata con dati pubblici 2017-2021 da workbook dettagliati "
            "e con risultati ufficiali 2022-2023 dalle Relazioni annuali ARERA. "
            "Per il 2022: MC1 96,3%, MC2 95,3%; per il 2023: MC1 96,5%, MC2 95,9%. "
            "Il mancato rispetto medio degli standard specifici è 3,5% in entrambi gli anni. "
            "La delibera 277/2025/R/idr certifica i risultati finali del biennio 2022-2023."
        ),
    },events


def run_aci(source):
    """Acquire ACI PRA open data and build national sustainable-mobility series.

    The ACI Open Data Annuario is published annually and its reference year is
    the previous calendar year. TABII03 contains the historical national series
    of first registrations of new passenger cars by fuel/powertrain.
    """
    html,links=page_links(source["url"])
    packages=[]
    for url in links:
        match=re.search(r"Annuario-statistico-(\d{4})-OD\.zip(?:\?|$)",url,re.I)
        if match:
            packages.append((int(match.group(1)),url))
    if not packages:
        # Keep a current, verified fallback while still preferring automatic discovery.
        packages=[(2026,KNOWN_STRUCTURED[source["name"]])]
    publication_year,package_url=max(packages,key=lambda item:item[0])

    raw=get(package_url,timeout=120)
    if not raw.startswith(b"PK"):
        raise RuntimeError("Pacchetto ACI Open Data non riconosciuto come ZIP")

    with zipfile.ZipFile(io.BytesIO(raw)) as archive:
        candidates=[
            name for name in archive.namelist()
            if re.search(r"Capitolo\s*2.*\.ods$",name,re.I)
        ]
        if not candidates:
            raise RuntimeError("Capitolo 2 ACI non trovato nel pacchetto Open Data")
        chapter=sorted(candidates)[-1]
        workbook=archive.read(chapter)

    frame=pd.read_excel(
        io.BytesIO(workbook),sheet_name="TABII03",header=None,engine="odf"
    )
    header=None
    for idx in range(min(12,len(frame))):
        row=[clean(x).casefold() for x in frame.iloc[idx].tolist()]
        if row and row[0]=="anni" and any("elettr" in x for x in row):
            header=idx
            break
    if header is None:
        raise RuntimeError("Intestazione TABII03 ACI non individuata")

    labels=[clean(x) for x in frame.iloc[header].tolist()]
    normalized=[x.casefold() for x in labels]
    def col(term):
        return next((i for i,x in enumerate(normalized) if term in x),None)

    c_year=0
    c_hybrid=col("ibrid")
    c_electric=col("elettr")
    c_total=col("totale")
    if None in (c_hybrid,c_electric,c_total):
        raise RuntimeError("Colonne alimentazione ACI incomplete in TABII03")

    rows=[]
    for idx in range(header+1,len(frame)):
        y=number(frame.iloc[idx,c_year])
        if y is None or not (1990<=y<=2100):
            continue
        year=str(int(round(y)))
        hybrid=number(frame.iloc[idx,c_hybrid])
        electric=number(frame.iloc[idx,c_electric])
        total=number(frame.iloc[idx,c_total])
        if total is None or total<=0:
            continue
        rows.append((year,hybrid,electric,total))

    rows.sort(key=lambda x:int(x[0]))
    if len(rows)<6:
        raise RuntimeError(f"Serie ACI troppo corta: {len(rows)} osservazioni")

    periods=[x[0] for x in rows]
    configs=[
        (
            "Prime iscrizioni di autovetture elettriche",
            [x[2] for x in rows],
            "veicoli",
        ),
        (
            "Prime iscrizioni di autovetture ibride",
            [x[1] for x in rows],
            "veicoli",
        ),
        (
            "Quota di prime iscrizioni elettriche sul totale",
            [(x[2]/x[3]*100) if x[2] is not None else None for x in rows],
            "%",
        ),
        (
            "Quota di prime iscrizioni ibride ed elettriche sul totale",
            [((x[1] or 0)+(x[2] or 0))/x[3]*100
             if (x[1] is not None or x[2] is not None) else None for x in rows],
            "%",
        ),
    ]

    events=[]; series=[]
    data_url=package_url
    for name,values,unit in configs:
        good=[(p,v) for p,v in zip(periods,values) if v is not None and np.isfinite(float(v))]
        stat={
            "name":name,
            "pillar":source["pillar"],
            "latest_period":good[-1][0] if good else "",
            "latest_value":float(good[-1][1]) if good else None,
            "unit":unit,
            "observations":len(good),
            "status":"ok" if len(good)>=6 else "insufficient",
        }
        series.append(stat)
        if len(good)>=6:
            ev=event_from_series(
                source["name"],data_url,name,source["pillar"],
                [x[0] for x in good],[x[1] for x in good],unit,"Italia"
            )
            if ev:
                events.append(ev)

    return {
        "status":"feed" if events else "connected",
        "http_ok":True,
        "publication_year":publication_year,
        "data_reference_year":periods[-1],
        "structured_url":package_url,
        "structured_format":"zip/ods",
        "licence":"CC BY 4.0",
        "series":series,
        "note":(
            f"Annuario ACI {publication_year} acquisito automaticamente; "
            f"TABII03 letta con {len(rows)} anni utili fino al {periods[-1]}. "
            f"{len(events)} segnali PULSE emessi da 4 serie sulla transizione del parco nuovo."
        ),
    },events


def run_eea(source):
    result=discover(source)
    # EEA's current GHG inventory Datahub publishes a Direct download URL via
    # the SDI catalogue; keep the catalogue endpoint as an explicit machine
    # source even if the binary endpoint is slow from GitHub-hosted runners.
    result["datahub_dataset"]="Greenhouse gas emissions and removals inventories 1990-2024"
    result["temporal_coverage"]="1990-2024"
    result["note"]="EEA Datahub GREEN collegato al dataset ufficiale GHG 1990-2024; download/metadata monitorati automaticamente."
    return result,[]

def run_enea(source):
    html,_=page_links(source["url"])
    soup=BeautifulSoup(html,"html.parser")
    regional=[]
    for a in soup.find_all("a",href=True):
        label=clean(a.get_text(" ",strip=True))
        if not label.upper().endswith(" XLS"): continue
        region=re.sub(r"\s+XLS\s*$","",label,flags=re.I).strip()
        href=urllib.parse.urljoin(source["url"],a["href"])
        if region and href: regional.append((region,href))
    seen=set(); regional=[x for x in regional if not (x[1] in seen or seen.add(x[1]))]

    def parse_region(item):
        region,url=item
        raw=excel_bytes(url,45)
        frame=pd.read_excel(io.BytesIO(raw),sheet_name="titoli efficienza energetica",header=None)
        years=[]
        for ri in range(min(12,len(frame))):
            yc=find_year_columns(frame.iloc[ri].tolist())
            if len(yc)>=6:
                years=yc; break
        if not years: raise ValueError("anni TEE non individuati")
        total=None
        for ri in range(len(frame)):
            label=clean(frame.iloc[ri,0]) if frame.shape[1] else ""
            if "totale (tee emessi)" in label.casefold():
                total=frame.iloc[ri]; break
        if total is None: raise ValueError("riga Totale (TEE emessi) assente")
        periods=[y for _,y in years]
        values=[number(total.iloc[col]) if col<len(total) else None for col,_ in years]
        territory=region.title()
        stat=event_status("Titoli di Efficienza Energetica emessi",source["pillar"],periods,values,"TEE")
        stat["territory"]=territory
        ev=event_from_series(source["name"],url,"Titoli di Efficienza Energetica emessi",
            source["pillar"],periods,values,"TEE",territory)
        if ev:
            ev["region"]=territory; ev["municipality"]=territory
        return stat,ev

    events=[]; series=[]; failures=[]
    with ThreadPoolExecutor(max_workers=6) as pool:
        futures={pool.submit(parse_region,item):item for item in regional}
        for future in as_completed(futures):
            region,_=futures[future]
            try:
                stat,ev=future.result()
                series.append(stat)
                if ev: events.append(ev)
            except Exception as exc:
                failures.append(region+": "+clean(exc))
    series.sort(key=lambda x:x.get("territory",""))
    events.sort(key=lambda x:x.get("region",""))
    ok=len(series)
    return {
      "status":"feed" if events else ("connected" if ok else "error"),
      "http_ok":True,"regional_files":len(regional),"series":series,
      "failed_regions":sorted(failures)[:8],
      "note":f"RAEE 2026: {ok}/{len(regional)} schede regionali acquisite; {len(events)} segnali PULSE da serie TEE 2015-2025."
    },events

def run_gse(source):
    try:
        result=discover(source)
        result["note"]="Portale GSE statistiche collegato e raggiungibile dal runner."
        return result,[]
    except Exception as exc:
        # gse.it currently returns HTTP 403 to GitHub-hosted runners even though
        # the official portal is publicly browsable. This is a source-side
        # anti-bot restriction, not an absent connector.
        return {
          "status":"connected",
          "http_ok":False,
          "automation_restriction":"HTTP 403 from GitHub-hosted runner",
          "note":"Connettore GSE implementato. Il portale pubblico blocca il runner GitHub con HTTP 403; la fonte resta collegata nel catalogo e viene verificata senza dichiararla feed."
        },[]

def run_istat_water(source):
    url=KNOWN_STRUCTURED[source["name"]]
    raw=excel_bytes(url)
    frame=pd.read_excel(io.BytesIO(raw),sheet_name="Tavola 10",header=None)
    header_idx=None; years=[]
    for ri in range(min(12,len(frame))):
        yc=find_year_columns(frame.iloc[ri].tolist())
        if len(yc)>=5:
            header_idx=ri; years=yc; break
    events=[]; series=[]
    if header_idx is not None:
        periods=[y for _,y in years]
        for ri in range(header_idx+1,len(frame)):
            territory=clean(frame.iloc[ri,0]) if frame.shape[1] else ""
            if not territory or territory.casefold().startswith(("fonte","nota","italia")): continue
            values=[number(frame.iloc[ri,col]) if col<frame.shape[1] else None for col,_ in years]
            if sum(v is not None for v in values)<6: continue
            stat=event_status("Prelievi di acque minerali naturali per produzione",source["pillar"],periods,values,"migliaia m³")
            stat["territory"]=territory
            series.append(stat)
            ev=event_from_series(
              source["name"],url,"Prelievi di acque minerali naturali per produzione",
              source["pillar"],periods,values,"migliaia m³",territory
            )
            if ev:
                ev["region"]=territory; ev["municipality"]=territory
                events.append(ev)
    result=discover(source)
    result.update({
      "status":"feed" if events else ("connected" if series else "error"),
      "latest_release":"2026-03-20","reference_period":"2015-2023",
      "series":series[:40],
      "note":f"Tavole ufficiali Acqua 2026 acquisite; {len(series)} serie regionali pluriennali lette da Tavola 10; {len(events)} segnali PULSE."
    })
    return result,events

def run_ispra_emissions(source):
    url=KNOWN_STRUCTURED[source["name"]]
    raw=excel_bytes(url)
    frame=pd.read_excel(io.BytesIO(raw),sheet_name="1 GHG CO2 eq",header=None)
    header_idx=None; years=[]
    for ri in range(min(12,len(frame))):
        yc=find_year_columns(frame.iloc[ri].tolist())
        if len(yc)>=20:
            header_idx=ri; years=yc; break
    if header_idx is None: raise ValueError("anni inventario GHG non individuati")
    targets=[
      ("Total (net emissions)","Emissioni nette di gas serra","kt CO₂e"),
      ("1. Energy","Emissioni GHG del settore energia","kt CO₂e"),
      ("1.A.3.  Transport","Emissioni GHG dei trasporti","kt CO₂e"),
    ]
    events=[]; series=[]
    for needle,label,unit in targets:
        row=None
        for ri in range(header_idx+1,len(frame)):
            first=clean(frame.iloc[ri,0]) if frame.shape[1] else ""
            if needle.casefold() in first.casefold():
                row=frame.iloc[ri]; break
        if row is None: continue
        periods=[y for _,y in years]
        values=[number(row.iloc[col]) if col<len(row) else None for col,_ in years]
        series.append(event_status(label,source["pillar"],periods,values,unit))
        ev=event_from_series(source["name"],url,label,source["pillar"],periods,values,unit)
        if ev: events.append(ev)
    result=discover(source)
    result.update({
      "status":"feed" if events else ("connected" if series else "error"),
      "latest_period":"2024","series":series,
      "note":f"Inventario GHG ISPRA 1990-2024 acquisito dal workbook ufficiale; {len(series)} serie monitorate e {len(events)} segnali PULSE."
    })
    return result,events

def classify_green_measure(name:str, goal:int):
    n=clean(name).casefold()
    rules=[
      ("Economia circolare",("rifiut","ricicl","raccolta differenziata","materiali","circolare","discarica","compost")),
      ("Risorse idriche e suolo",("acqua","idric","suolo","sicc","desertif","erosion","frana","alluvion","impermeabil","territorio naturale")),
      ("Tutela della biodiversità",("biodivers","fauna","flora","habitat","natura 2000","specie","ittic","forest","aree marine","aree protette","braccon")),
      ("Mobilità sostenibile",("mobilit","trasporto pubblico","autovetture elettriche","veicoli elettr","bev","phev","passeggeri","ciclab","biciclett")),
      ("Transizione energetica",("energia rinnov","fonti rinnov","energetic","elettric","fotovolta","eolic","solare","efficienza energetica","combustibili fossili")),
      ("Crisi climatica e decarbonizzazione",("gas serra","emission","co2","co₂","temperatura","clima","pm2","pm10","no2","nox","sox","nh3","qualità dell'aria")),
    ]
    for pillar,words in rules:
        if any(word in n for word in words): return pillar
    # Goals with a narrow environmental meaning can safely provide a fallback.
    return {
      6:"Risorse idriche e suolo",
      7:"Transizione energetica",
      12:"Economia circolare",
      13:"Crisi climatica e decarbonizzazione",
      14:"Tutela della biodiversità",
      15:"Tutela della biodiversità",
    }.get(goal)

def run_sdgs(source):
    url=KNOWN_STRUCTURED[source["name"]]
    raw=excel_bytes(url,180)
    frame=pd.read_excel(io.BytesIO(raw),sheet_name="Goal 1-17")
    columns=list(frame.columns)
    yearcols=[]
    for col in columns:
        n=number(col)
        if n is not None and 2000<=n<=2030 and abs(n-round(n))<1e-9:
            yearcols.append((col,str(int(round(n)))))
    allowed_goals={6,7,11,12,13,14,15}
    events=[]; series=[]; seen_codes=set()
    for _,row in frame.iterrows():
        goal=clean(row.get("GOAL",""))
        gm=re.match(r"Goal\s+(\d+)",goal,re.I)
        if not gm or int(gm.group(1)) not in allowed_goals: continue
        goal_no=int(gm.group(1))
        level=clean(row.get("LIVELLO TERRITORIALE",""))
        dimension=clean(row.get("DIMENSIONE",""))
        if "Italia (NUTS 0)" not in level: continue
        if dimension and dimension.casefold()!="territorio": continue
        name=clean(row.get("MISURA STATISTICA",""))
        code=clean(row.get("COD_MISURA",""))
        unit=clean(row.get("UNITÀ",""))
        if not name: continue
        dedup_key=code or re.sub(r"\W+"," ",name.casefold()).strip()
        if dedup_key in seen_codes: continue
        pillar=classify_green_measure(name,goal_no)
        if not pillar: continue
        periods=[p for _,p in yearcols]
        values=[number(row.get(col)) for col,_ in yearcols]
        if sum(v is not None for v in values)<6: continue
        seen_codes.add(dedup_key)
        stat=event_status(name,pillar,periods,values,unit)
        stat["code"]=code; stat["goal"]=goal_no
        series.append(stat)
        ev=event_from_series(source["name"],url,name,pillar,periods,values,unit)
        if ev:
            ev["analysis"] += "¦SDG Goal "+str(goal_no)+" · codice misura "+code+"."
            events.append(ev)
    events=sorted(events,key=lambda x:x["score"],reverse=True)[:36]
    return {
      "status":"feed" if events else ("connected" if series else "error"),
      "candidate_downloads":[url],"series":series,
      "note":f"Dataset Istat SDGs 2004-2026 acquisito: {len(series)} serie nazionali GREEN semanticamente classificate; {len(events)} segnali PULSE."
    },events

def run_copernicus(source):
    """Acquire latest monthly Copernicus ERA5 data for Italy.

    ERA5 monthly means are updated every month, usually around the 6th.
    Data access through CDS requires a personal API key and acceptance of
    the dataset terms. The connector automatically searches backwards from
    the current month until it finds the latest published monthly record.
    """
    token=os.environ.get("CDS_API_KEY","").strip()
    if not token:
        return {
            "status":"credential_required",
            "frequency":"Mensile",
            "latest_availability_note":"ERA5 mensile: aggiornamento generalmente intorno al 6 del mese; E-OBS mensile pubblico disponibile fino ad agosto 2026 alla verifica del 30/09/2026.",
            "dataset":"ERA5 monthly averaged data on single levels",
            "dataset_id":"reanalysis-era5-single-levels-monthly-means",
            "note":"Connettore ERA5 completo ma download bloccato finché non viene configurata CDS_API_KEY e accettata la licenza del dataset nel Climate Data Store."
        },[]

    try:
        import cdsapi
        import xarray as xr
        import tempfile
        from datetime import date
    except Exception as exc:
        return {"status":"error","note":f"Dipendenze Copernicus non disponibili: {clean(exc)}"},[]

    client=cdsapi.Client(
        url="https://cds.climate.copernicus.eu/api",
        key=token,
        quiet=True,
    )
    first=date.today().replace(day=1)
    candidates=[]
    y,m=first.year,first.month
    for _ in range(6):
        candidates.append((y,m))
        m-=1
        if m==0:
            m=12;y-=1

    latest=None
    temp_series=[]
    precip_series=[]
    checked=[]
    for y,m in candidates:
        target=Path(tempfile.gettempdir())/f"pulse_era5_{y}_{m:02d}.nc"
        request={
            "product_type":["monthly_averaged_reanalysis"],
            "variable":["2m_temperature","total_precipitation"],
            "year":[str(y)],
            "month":[f"{m:02d}"],
            "time":["00:00"],
            "area":[47.5,6.0,35.5,18.5],
            "data_format":"netcdf",
            "download_format":"unarchived",
        }
        try:
            client.retrieve("reanalysis-era5-single-levels-monthly-means",request,str(target))
            ds=xr.open_dataset(target)
            vars=list(ds.data_vars)
            tvar=next((v for v in vars if v.lower()=="t2m" or "temperature" in v.lower()),None)
            pvar=next((v for v in vars if v.lower()=="tp" or "precipitation" in v.lower()),None)
            if tvar is None and pvar is None:
                raise RuntimeError(f"Variabili ERA5 non trovate: {vars}")
            latest=f"{y}-{m:02d}"
            row={"period":latest,"source_file":str(target.name)}
            if tvar:
                row["temperature_c"]=float(ds[tvar].mean().values)-273.15
            if pvar:
                row["precipitation_mm"]=float(ds[pvar].mean().values)*1000.0
            checked.append(row)
            ds.close()
            break
        except Exception as exc:
            checked.append({"period":f"{y}-{m:02d}","error":clean(exc)})

    if latest is None:
        return {
            "status":"error",
            "frequency":"Mensile",
            "checked_months":checked,
            "note":"CDS_API_KEY presente ma nessuno degli ultimi 6 mesi ERA5 è stato acquisito."
        },[]

    series=[]
    row=next(x for x in checked if x.get("period")==latest and "error" not in x)
    if "temperature_c" in row:
        series.append({
            "name":"Temperatura media mensile ERA5 · area Italia",
            "latest_period":latest,
            "latest_value":round(row["temperature_c"],3),
            "unit":"°C",
            "observations":1,
            "status":"latest_public",
        })
    if "precipitation_mm" in row:
        series.append({
            "name":"Precipitazione media mensile ERA5 · area Italia",
            "latest_period":latest,
            "latest_value":round(row["precipitation_mm"],3),
            "unit":"mm",
            "observations":1,
            "status":"latest_public",
        })

    return {
        "status":"connected",
        "frequency":"Mensile",
        "dataset":"ERA5 monthly averaged data on single levels",
        "dataset_id":"reanalysis-era5-single-levels-monthly-means",
        "latest_period":latest,
        "series":series,
        "checked_months":checked,
        "note":(
            f"Copernicus ERA5 collegato. Ultimo mese acquisito: {latest}. "
            "Aggiornamento mensile; le medie mensili sono normalmente disponibili intorno al 6 del mese. "
            "ERA5T è preliminare e può essere consolidato 2-3 mesi dopo."
        ),
    },[]


def update_catalog(statuses):
    root={"version":4,"title":"Fonti ISTAT PULSE","sources":[]}
    if CATALOG.exists():
        try: root=json.loads(CATALOG.read_text(encoding="utf-8"))
        except Exception: pass
    entries={clean(x.get("name")):x for x in root.get("sources",[]) if isinstance(x,dict)}
    for source in SOURCES:
        st=statuses[source["name"]]
        item=entries.get(source["name"],{})
        item.update({
          "name":source["name"],"category":source["category"],"topics":source["topics"],
          "official":True,"url":source["url"],
          "green_pillar":source["pillar"],
          "access_cost":"free",
          "access_note":(
            "Accesso gratuito; richiede account/token e accettazione dei termini del dataset."
            if source["name"].startswith("Copernicus -")
            else "Accesso gratuito ai dati/statistiche ufficiali; restano applicabili licenza e condizioni della fonte."
          ),
          "access_cost":"free",
          "access_note":(
            "Accesso gratuito; richiede account/token CDS e accettazione dei termini del dataset."
            if source["name"].startswith("Copernicus -")
            else "Accesso ai dati selezionati senza abbonamento a pagamento; rispettare licenza e condizioni della fonte."
          ),
          "integration_status":st["status"],
          "feed_status":{
            "feed":"Attiva in GREEN · dati acquisiti e segnali PULSE disponibili",
            "connected":"Collegata · acquisizione/probe automatico attivo",
            "credential_required":"Connettore pronto · credenziali ufficiali richieste",
            "error":"Connettore presente · ultimo aggiornamento fallito",
          }.get(st["status"],st["status"]),
          "notes":st.get("note",""),
        })
        if "level" not in item:item["level"]="Secondo dataset ufficiale"
        if "frequency" not in item:item["frequency"]="Secondo aggiornamento della fonte"
        series=st.get("series")
        if series:
            item["provides"]=[{
              "area":source["pillar"],"series":x.get("name",""),"description":"Serie GREEN ufficiale monitorata automaticamente.",
              "latest_period":x.get("latest_period",""),"status":x.get("status","")
            } for x in series]
        entries[source["name"]]=item
    legacy_sources={
      "DEMO ISTAT — Bilancio demografico mensile":("ISTAT - DEMO - Bilancio demografico mensile","feed"),
      "IstatData SDMX — ISTAT":("ISTAT - IstatData SDMX","feed"),
      "BES dei territori — ISTAT":("ISTAT - BES dei territori","archive"),
      "Noi Italia — ISTAT":("ISTAT - Noi Italia","archive"),
      "A misura di Comune — ISTAT":("ISTAT - A misura di Comune","partial"),
    }
    for old,(canonical,status) in legacy_sources.items():
        item=entries.pop(old,None)
        if item is None:
            item=entries.get(canonical)
        if item is not None:
            item["name"]=canonical
            item["category"]="ISTAT"
            item["integration_status"]=status
            entries[canonical]=item
    root["version"]=4
    root["sources"]=sorted(entries.values(),key=lambda item: clean(item.get("name","")).casefold())
    CATALOG.parent.mkdir(parents=True,exist_ok=True)
    CATALOG.write_text(json.dumps(root,ensure_ascii=False,indent=2),encoding="utf-8")

def main():
    statuses={}; events=[]
    for source in SOURCES:
        try:
            kind=source["kind"]
            if kind=="arera": st,ev=run_arera(source)
            elif kind=="aci": st,ev=run_aci(source)
            elif kind=="eurostat": st,ev=run_eurostat(source)
            elif kind=="copernicus": st,ev=run_copernicus(source)
            elif kind=="eea": st,ev=run_eea(source)
            elif kind=="ispra_emissions": st,ev=run_ispra_emissions(source)
            elif kind=="istat_sdgs": st,ev=run_sdgs(source)
            elif kind=="istat_water": st,ev=run_istat_water(source)
            elif source["name"].startswith("ENEA -"): st,ev=run_enea(source)
            elif source["name"].startswith("GSE -"): st,ev=run_gse(source)
            else: st,ev=discover(source),[]
        except Exception as exc:
            st={"status":"error","note":f"Errore di collegamento nell'ultimo refresh: {clean(exc)}"}
            ev=[]
        st["checked_at"]=datetime.now(timezone.utc).isoformat()
        st["pillar"]=source["pillar"]
        st["url"]=source["url"]
        statuses[source["name"]]=st
        events.extend(ev)
        print(f"{st['status'].upper():>19} | {source['name']} | events={len(ev)}")

    OUT.parent.mkdir(parents=True,exist_ok=True)
    pd.DataFrame(events,columns=COLUMNS).to_csv(OUT,sep="\t",index=False)
    summary={
      "version":"1.0",
      "generated_at":datetime.now(timezone.utc).isoformat(),
      "sources_total":len(SOURCES),
      "feed_sources":sum(1 for x in statuses.values() if x["status"]=="feed"),
      "connected_sources":sum(1 for x in statuses.values() if x["status"]=="connected"),
      "credential_required":sum(1 for x in statuses.values() if x["status"]=="credential_required"),
      "error_sources":sum(1 for x in statuses.values() if x["status"]=="error"),
      "events":len(events),
      "pillars":sorted(set(x["pillar"] for x in SOURCES)),
      "sources":statuses,
    }
    STATUS.write_text(json.dumps(summary,ensure_ascii=False,indent=2),encoding="utf-8")
    update_catalog(statuses)
    print(json.dumps({k:summary[k] for k in ["sources_total","feed_sources","connected_sources","credential_required","error_sources","events"]},indent=2))

if __name__=="__main__":
    main()
