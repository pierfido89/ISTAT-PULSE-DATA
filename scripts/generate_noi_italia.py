#!/usr/bin/env python3
"""Acquire the official Noi Italia downloadable database and build:
1) latest observed values for Italy + the 20 regions;
2) historical PULSE signals from comparable annual series.

No publication year is ever substituted for the statistical reference year.
The generated archive is validated before it can be published to the Android app.
"""
from __future__ import annotations
import hashlib, io, math, re, time, urllib.request, zipfile
from pathlib import Path
import numpy as np
import pandas as pd

URL="https://noi-italia.istat.it/documenti/Dati.zip"
PAGE="https://noi-italia.istat.it/"
BASE=Path("app/src/main/assets")
OBS_OUT=BASE/"pulse_observations_noi.tsv"
EVENT_OUT=BASE/"pulse_events_noi.tsv"

REGIONS={
"Piemonte","Valle d'Aosta/Vallée d'Aoste","Liguria","Lombardia",
"Trentino-Alto Adige/Südtirol","Veneto","Friuli-Venezia Giulia","Emilia-Romagna",
"Toscana","Umbria","Marche","Lazio","Abruzzo","Molise","Campania","Puglia",
"Basilicata","Calabria","Sicilia","Sardegna","Italia"
}
DOMAINS=[
"Sanità e Salute.zip","Istruzione.zip","Condizioni economiche delle famiglie.zip",
"Ambiente.zip","Mercato del lavoro.zip","Popolazione.zip","Turismo.zip",
"Strutture produttive.zip","Cultura e tempo libero.zip","Infrastrutture e trasporti.zip"
]
EVENT_COLS=[
"id","municipality_code","municipality","province","region","indicator","patterns",
"scope","score","validation_status","period","summary","annual","rolling12",
"benchmark_local","benchmark_rest","analysis","source_family","source_url"
]
OBS_COLS=["area","indicator","territory","period","value","unit","source","url","note","status"]

def fetch():
    last=None
    for attempt in range(1,6):
        try:
            req=urllib.request.Request(URL,headers={"User-Agent":"Mozilla/5.0 ISTAT-PULSE/0.10"})
            with urllib.request.urlopen(req,timeout=180) as r:
                raw=r.read()
                if raw[:2]!=b"PK": raise RuntimeError("Noi Italia download is not a ZIP archive")
                print("Noi Italia archive",len(raw),"bytes",flush=True)
                return raw
        except Exception as exc:
            last=exc; print("Noi Italia retry",attempt,repr(exc),flush=True)
            time.sleep(5*attempt)
    raise last

def clean(x):
    return re.sub(r"\s+"," ",str(x if x is not None else "")).strip()

def number(x):
    raw=clean(x)
    if not raw or raw in {"....","...","..",".","-","nan","NaN"}: return None
    raw=raw.replace("%","").replace(" ","")
    if "," in raw and "." not in raw: raw=raw.replace(",",".")
    try:
        v=float(raw)
        return v if math.isfinite(v) else None
    except Exception:
        return None

def area_for(domain,indicator):
    d=domain.casefold(); k=indicator.casefold()
    if "sanità" in d or "salute" in d:
        return "Sanità" if any(q in k for q in ("ospedal","medic","sanitari","spesa sanitaria","posti letto","istituti di cura")) else "Salute"
    if "istruzione" in d: return "Istruzione"
    if "condizioni economiche" in d:
        if any(q in k for q in ("povert","depriv","disagio")): return "Povertà"
        if any(q in k for q in ("disuguagl","gini","s80")): return "Disuguaglianza"
        if any(q in k for q in ("reddito","retribuz")): return "Redditi"
        return "Potere d'acquisto e consumi"
    if "ambiente" in d: return "Ambiente"
    if "lavoro" in d: return "Lavoro e mercato del lavoro"
    if "popolazione" in d: return "Popolazione e demografia"
    if "turismo" in d: return "Turismo"
    if "strutture produttive" in d: return "Imprese e industria"
    if "cultura" in d: return "Società e cultura"
    if "infrastrutture" in d or "trasporti" in d: return "Territorio e mobilità"
    return clean(domain)

def robust_scale(values):
    a=np.asarray([v for v in values if v is not None and np.isfinite(v)],dtype=float)
    if len(a)<3:return 0.0
    med=np.median(a); mad=np.median(np.abs(a-med))*1.4826
    if mad>1e-9:return float(mad)
    sd=float(np.std(a)); return sd if sd>1e-9 else 0.0

def periods_and_values(row,year_cols):
    out=[]
    for year,col in year_cols:
        v=number(row.get(col))
        if v is not None: out.append((year,v))
    return out

def preferred_rows(frame):
    cols={clean(c):c for c in frame.columns}
    needed=["Indicatore","Territorio"]
    if any(k not in cols for k in needed):
        return pd.DataFrame()
    frame=frame.copy()
    frame["_indicator"]=frame[cols["Indicatore"]].map(clean)
    frame["_territory"]=frame[cols["Territorio"]].map(clean)
    frame=frame[frame["_territory"].isin(REGIONS) & frame["_indicator"].ne("")]
    if frame.empty:return frame
    modal_col=cols.get("Modalità")
    if modal_col is None:
        return frame
    frame["_mode"]=frame[modal_col].map(clean)
    def rank_mode(v):
        k=v.casefold()
        if k in {"totale","totali","total","t"} or k.startswith("totale "): return 0
        if "totale" in k: return 1
        if k in {"","nan"}: return 2
        return 3
    frame["_mode_rank"]=frame["_mode"].map(rank_mode)
    # Keep each source-defined mode as a distinct series, but if a Total exists,
    # use it for the headline indicator and avoid silently mixing sex/age modes.
    totals=frame[frame["_mode_rank"]<=1]
    if not totals.empty:
        keys=set(zip(totals["_indicator"],totals["_territory"]))
        mask=[(i,t) not in keys or r<=1 for i,t,r in zip(frame["_indicator"],frame["_territory"],frame["_mode_rank"])]
        frame=frame.loc[mask]
    return frame

def discover_main_book(nested):
    candidates=[x for x in nested.namelist() if x.lower().endswith(".xlsx")]
    for name in candidates:
        try:
            xls=pd.ExcelFile(io.BytesIO(nested.read(name)))
            if "Dati Italia e Regioni" in xls.sheet_names:
                return name
        except Exception:
            continue
    return None

def make_patterns(values, national_values=None):
    if len(values)<6:return [],[],0.0
    vals=np.asarray(values[-8:],dtype=float)
    deltas=np.diff(vals)
    latest=float(deltas[-1]); prev=float(deltas[-2])
    scale=robust_scale(deltas[:-1])
    if scale<=1e-9:scale=max(abs(float(np.median(vals)))*0.005,1e-6)
    z=abs(latest)/scale
    patterns=[]; analysis=[]
    prior=vals[:-1]
    if vals[-1]>np.max(prior) and z>=0.65:
        patterns.append("RECORD_MAX"); analysis.append("Record: ultimo valore sopra i precedenti valori recenti.")
    elif vals[-1]<np.min(prior) and z>=0.65:
        patterns.append("RECORD_MIN"); analysis.append("Record: ultimo valore sotto i precedenti valori recenti.")
    if latest*prev<0 and z>=0.75:
        patterns.append("INVERSIONE"); analysis.append("Inversione: l'ultima variazione cambia segno.")
    elif latest*prev>0 and abs(prev)>1e-9:
        ratio=abs(latest)/abs(prev)
        if ratio>=1.65 and z>=0.8:
            patterns.append("ACCELERAZIONE"); analysis.append("Accelerazione: variazione più intensa della precedente.")
        elif ratio<=0.55 and abs(prev)>=0.65*scale:
            patterns.append("RALLENTAMENTO"); analysis.append("Rallentamento: variazione meno intensa della precedente.")
    lscale=robust_scale(prior)
    zlevel=abs(vals[-1]-np.median(prior))/lscale if lscale>1e-9 else 0.0
    if zlevel>=2.5 or z>=2.75:
        patterns.append("ANOMALIA"); analysis.append("Anomalia: livello o variazione insoliti rispetto alla storia recente.")
    if national_values is not None and len(national_values)>=2:
        nd=float(national_values[-1]-national_values[-2])
        if latest*nd<0 and abs(latest)>=0.35*scale:
            patterns.append("DIVERGENZA")
            analysis.append("Divergenza: il territorio e l'Italia si muovono in direzioni opposte nell'ultimo periodo.")
    patterns=list(dict.fromkeys(patterns))
    score=48+min(22,z*4)+min(12,zlevel*2)
    if any(p.startswith("RECORD") for p in patterns):score+=8
    if "INVERSIONE" in patterns:score+=7
    if "ANOMALIA" in patterns:score+=7
    if "DIVERGENZA" in patterns:score+=7
    if "ACCELERAZIONE" in patterns or "RALLENTAMENTO" in patterns:score+=4
    return patterns,analysis,min(99.0,float(score))

def fmt(v):
    if abs(v)>=1_000_000:return (f"{v/1_000_000:.2f} mln").replace(".",",")
    if abs(v)>=10_000:return f"{v:,.0f}".replace(",",".")
    return f"{v:.2f}".rstrip("0").rstrip(".").replace(".",",")

def main():
    outer=zipfile.ZipFile(io.BytesIO(fetch()))
    series=[]
    observations=[]
    for domain_zip in DOMAINS:
        if domain_zip not in outer.namelist():
            raise RuntimeError(f"Missing Noi Italia domain {domain_zip}")
        nested=zipfile.ZipFile(io.BytesIO(outer.read(domain_zip)))
        main_book=discover_main_book(nested)
        if not main_book:
            raise RuntimeError(f"No Dati Italia e Regioni workbook in {domain_zip}")
        raw=nested.read(main_book)
        frame=pd.read_excel(io.BytesIO(raw),sheet_name="Dati Italia e Regioni",dtype=str)
        frame.columns=[clean(c) for c in frame.columns]
        colmap={clean(c):c for c in frame.columns}
        for key in ["Indicatore","Territorio"]:
            if key not in colmap: raise RuntimeError(f"{domain_zip}: missing {key}")
        year_cols=sorted((int(str(c)),c) for c in frame.columns if re.fullmatch(r"20\d{2}",str(c)))
        if len(year_cols)<2: raise RuntimeError(f"{domain_zip}: not enough year columns")
        unit_col=colmap.get("Unità di misura"); source_col=colmap.get("Fonte")
        chosen=preferred_rows(frame)
        for _,row in chosen.iterrows():
            indicator=clean(row[colmap["Indicatore"]]); territory=clean(row[colmap["Territorio"]])
            mode=clean(row.get(colmap.get("Modalità",""),""))
            pv=periods_and_values(row,year_cols)
            if not pv: continue
            year,value=pv[-1]
            title=indicator if mode.casefold() in {"","totale","totali","total","t"} else f"{indicator} · {mode}"
            unit=clean(row.get(unit_col,"")) if unit_col else ""
            source_detail=clean(row.get(source_col,"")) if source_col else ""
            area=area_for(domain_zip,indicator)
            observations.append({
                "area":area,"indicator":title,"territory":territory,"period":str(year),
                "value":format(float(value),".10g"),"unit":unit,
                "source":"Noi Italia — ISTAT","url":PAGE,
                "note":("Fonte originaria: "+source_detail+". " if source_detail else "")+
                    "Serie annuale del database ufficiale Noi Italia; anno statistico preservato.",
                "status":"ultimo valore osservato, non necessariamente un nuovo segnale PULSE"
            })
            # Only uninterrupted annual sequences are comparable for
            # year-on-year acceleration, inversion and recent-record tests.
            # Nonconsecutive observations still remain in the observed catalogue.
            contiguous=[pv[-1]]
            for pair in reversed(pv[:-1]):
                if pair[0] != contiguous[-1][0]-1:
                    break
                contiguous.append(pair)
            contiguous=list(reversed(contiguous))
            if len(contiguous)>=6:
                series.append({
                    "domain":domain_zip,"area":area,"indicator":title,"territory":territory,
                    "periods":[y for y,_ in contiguous],"values":[v for _,v in contiguous],
                    "unit":unit,"source_detail":source_detail
                })
        print(domain_zip,"observations",sum(1 for o in observations if o["area"]==area_for(domain_zip,"")),flush=True)

    national={(s["domain"],s["indicator"]):s for s in series if s["territory"]=="Italia"}
    events=[]
    for s in series:
        national_values=None
        n=national.get((s["domain"],s["indicator"]))
        # Divergence needs the exact same two statistical reference years:
        # never compare a regional 2023→2024 change with Italy 2024→2025.
        if n and s["territory"]!="Italia":
            nv=dict(zip(n["periods"],n["values"]))
            current_year,previous_year=s["periods"][-1],s["periods"][-2]
            if current_year in nv and previous_year in nv:
                national_values=np.asarray([nv[previous_year],nv[current_year]],dtype=float)
        patterns,analysis,score=make_patterns(s["values"],national_values)
        if not patterns: continue
        period=str(s["periods"][-1]); cur=s["values"][-1]; prev=s["values"][-2]
        movement="sale" if cur>prev else "scende" if cur<prev else "resta stabile"
        summary=f"{s['territory']}: {s['indicator']} {movement} da {fmt(prev)} a {fmt(cur)} nel {period}."
        identity=f"NOI|{s['domain']}|{s['indicator']}|{s['territory']}|{period}"
        eid=hashlib.sha256(identity.encode()).hexdigest()[:16]
        region=s["territory"] if s["territory"]!="Italia" else "Italia"
        events.append({
            "id":eid,"municipality_code":"NOI-"+hashlib.sha1(s["territory"].encode()).hexdigest()[:8],
            "municipality":s["territory"],"province":"","region":region,
            "indicator":s["indicator"],"patterns":"|".join(patterns),"scope":"GENERAL",
            "score":round(score,1),"validation_status":"SEGNALE PULSE — NOI ITALIA",
            "period":period,"summary":summary,
            "annual":"|".join(format(v,".8g") for v in s["values"][-8:]),
            "rolling12":"","benchmark_local":"","benchmark_rest":"",
            "analysis":"¦".join(analysis+[
                "Serie storica annuale ufficiale Noi Italia.",
                "ANNUAL_PERIODS:"+"|".join(str(y) for y in s["periods"][-8:]),
                "Periodo della notizia = ultimo anno statistico disponibile, non anno di download."
            ]),
            "source_family":"Noi Italia — ISTAT","source_url":PAGE
        })

    BASE.mkdir(parents=True,exist_ok=True)
    obs=pd.DataFrame(observations,columns=OBS_COLS).drop_duplicates(
        subset=["source","indicator","territory","period"])
    ev=pd.DataFrame(events,columns=EVENT_COLS).drop_duplicates(subset=["id"])
    obs.to_csv(OBS_OUT,sep="\t",index=False)
    ev.to_csv(EVENT_OUT,sep="\t",index=False)
    print("NOI ITALIA OBSERVATIONS",len(obs),flush=True)
    print("NOI ITALIA HISTORICAL SIGNALS",len(ev),flush=True)
    print("NOI AREAS",obs["area"].value_counts().to_dict(),flush=True)
    if len(obs)<500: raise RuntimeError(f"Noi Italia import unexpectedly small: {len(obs)}")
    if len(ev)<100: raise RuntimeError(f"Noi Italia historical signal set unexpectedly small: {len(ev)}")

if __name__=="__main__":
    main()
