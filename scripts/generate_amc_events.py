#!/usr/bin/env python3
"""Generate verified historical PULSE signals from ISTAT A misura di Comune.

The source page was updated in 2026, but the statistical reference years in the
selected tables are mostly 2023/2024. Events keep the real statistical year and
are published as a territorial historical feed, never as current-2026 news.
"""
from __future__ import annotations
from pathlib import Path
from urllib.parse import urljoin,urlparse
import hashlib,io,json,math,re,urllib.request
import numpy as np
import pandas as pd
from bs4 import BeautifulSoup

PAGE="https://www.istat.it/statistica-sperimentale/aggiornamento-degli-indicatori-del-sistema-informativo-a-misura-di-comune/"
SOURCE="ISTAT - A misura di Comune"
OUT=Path("app/src/main/assets/pulse_events_amc.tsv")
CATALOG=Path("app/src/main/assets/sources_catalog.json")
COLS=["id","municipality_code","municipality","province","region","indicator","patterns","scope","score","validation_status","period","summary","annual","rolling12","benchmark_local","benchmark_rest","analysis","source_family","source_url"]

TABLES=[
 {"book":"5 – Lavoro","sheet":"Tav. 1.1 Comuni","area":"Lavoro","indicator":"Tasso di occupazione","unit":"%"},
 {"book":"5 – Lavoro","sheet":"Tav. 2.1 Comuni","area":"Lavoro","indicator":"Tasso di disoccupazione","unit":"%"},
 {"book":"6 – Benessere economico","sheet":"Tav. 1.1 Comuni","area":"Redditi","indicator":"Contribuenti con reddito complessivo inferiore a 10.000 euro","unit":"%"},
 {"book":"6 – Benessere economico","sheet":"Tav. 2.1 Comuni","area":"Redditi","indicator":"Reddito imponibile per contribuente","unit":"euro"},
 {"book":"11 – Territorio e ambiente","sheet":"Tav. 6.1 Comuni","area":"Ambiente","indicator":"Raccolta differenziata dei rifiuti urbani","unit":"%"},
 {"book":"11 – Territorio e ambiente","sheet":"Tav. 8.1 Comuni","area":"Mobilità sostenibile","indicator":"Autovetture con standard di emissioni inferiore a Euro 4","unit":"%"},
]

def download(url):
    req=urllib.request.Request(url,headers={"User-Agent":"ISTAT-PULSE/1.1"})
    with urllib.request.urlopen(req,timeout=180) as r:
        raw=r.read()
        if r.status!=200: raise RuntimeError(f"HTTP {r.status}: {url}")
        return raw

def official_urls():
    soup=BeautifulSoup(download(PAGE),"html.parser")
    out={}
    for a in soup.select("a[href]"):
        label=a.get_text(" ",strip=True)
        url=urljoin(PAGE,a.get("href",""))
        if urlparse(url).netloc in {"www.istat.it","istat.it"} and url.lower().split("?")[0].endswith(".xlsx"):
            out[label]=url
    if len(out)<20: raise RuntimeError(f"Too few official XLSX links: {len(out)}")
    return out

def num(x):
    if x is None or pd.isna(x): return None
    s=str(x).strip()
    if s in {"","-","..","....","nan","NaN",".","n.d.","nd"}: return None
    try:
        v=float(s); return v if math.isfinite(v) else None
    except Exception: pass
    if "," in s and "." in s:
        s=s.replace(".","").replace(",",".") if s.rfind(",")>s.rfind(".") else s.replace(",","")
    elif "," in s: s=s.replace(",",".")
    s=re.sub(r"[^0-9+\-.eE]","",s)
    try:
        v=float(s); return v if math.isfinite(v) else None
    except Exception: return None

def robust_scale(values):
    a=np.asarray([v for v in values if v is not None and np.isfinite(v)],dtype=float)
    if len(a)<3:return 0.0
    med=np.median(a); mad=np.median(np.abs(a-med))*1.4826
    if mad>1e-9:return float(mad)
    sd=float(np.std(a)); return sd if sd>1e-9 else 0.0

def detect(values):
    if len(values)<6:return [],[],0.0
    vals=np.asarray(values[-8:],dtype=float)
    d=np.diff(vals); latest=float(d[-1]); prev=float(d[-2])
    scale=robust_scale(d[:-1]) or max(abs(float(np.median(vals)))*0.005,1e-6)
    z=abs(latest)/scale
    pats=[]; notes=[]
    prior=vals[:-1]
    if vals[-1]>np.max(prior) and z>=0.65:
        pats.append("RECORD_MAX"); notes.append("Record: ultimo valore sopra i valori recenti precedenti.")
    elif vals[-1]<np.min(prior) and z>=0.65:
        pats.append("RECORD_MIN"); notes.append("Record: ultimo valore sotto i valori recenti precedenti.")
    if latest*prev<0 and z>=0.8:
        pats.append("INVERSIONE"); notes.append("Inversione: l'ultima variazione cambia segno.")
    elif latest*prev>0 and abs(prev)>1e-9:
        ratio=abs(latest)/abs(prev)
        if ratio>=1.7 and z>=0.9:
            pats.append("ACCELERAZIONE"); notes.append("Accelerazione: ultimo cambiamento più intenso del precedente.")
        elif ratio<=0.5 and abs(prev)>=0.7*scale:
            pats.append("RALLENTAMENTO"); notes.append("Rallentamento: ultimo cambiamento più contenuto del precedente.")
    lscale=robust_scale(prior)
    zlevel=abs(vals[-1]-np.median(prior))/lscale if lscale>1e-9 else 0.0
    if zlevel>=2.5 or z>=2.75:
        pats.append("ANOMALIA"); notes.append("Anomalia: livello o variazione insoliti rispetto alla storia recente.")
    pats=list(dict.fromkeys(pats))
    score=48+min(22,z*4)+min(12,zlevel*2)
    if any(p.startswith("RECORD") for p in pats): score+=8
    if "INVERSIONE" in pats: score+=7
    if "ANOMALIA" in pats: score+=7
    if "ACCELERAZIONE" in pats or "RALLENTAMENTO" in pats: score+=4
    return pats,notes,min(99.0,float(score))

def fmt(v):
    if abs(v)>=1000:return f"{v:,.0f}".replace(",",".")
    return f"{v:.2f}".rstrip("0").rstrip(".").replace(".",",")

def main():
    urls=official_urls(); books={}; candidates=[]
    for spec in TABLES:
        url=urls.get(spec["book"])
        if not url: raise RuntimeError(f"Missing official workbook {spec['book']}")
        if spec["book"] not in books:
            raw=download(url)
            if raw[:2]!=b"PK": raise RuntimeError(f"Invalid XLSX payload {url}")
            books[spec["book"]]=raw
        raw=books[spec["book"]]
        frame=pd.read_excel(io.BytesIO(raw),sheet_name=spec["sheet"],header=3,dtype=str)
        frame.columns=[str(c).strip() for c in frame.columns]
        needed={"Denominazione comune","Codice comune Istat","Denominazione regione"}
        if not needed.issubset(frame.columns): raise RuntimeError(f"Missing keys in {spec['book']}/{spec['sheet']}")
        years=sorted((int(str(c)),c) for c in frame.columns if re.fullmatch(r"20\d{2}",str(c).strip()))
        if len(years)<6: continue
        for _,row in frame.iterrows():
            code=re.sub(r"\D","",str(row.get("Codice comune Istat","")).replace(".0","")).zfill(6)
            comune=str(row.get("Denominazione comune","")).strip()
            region=str(row.get("Denominazione regione","")).strip()
            province=str(row.get("Denominazione provincia","")).strip() if "Denominazione provincia" in frame.columns else ""
            if not re.fullmatch(r"\d{6}",code) or not comune or comune.casefold()=="nan" or not region: continue
            series=[(y,num(row.get(c))) for y,c in years]
            series=[x for x in series if x[1] is not None]
            if len(series)<6: continue
            contiguous=[series[-1]]
            for pair in reversed(series[:-1]):
                if pair[0]!=contiguous[-1][0]-1: break
                contiguous.append(pair)
            contiguous=list(reversed(contiguous))
            if len(contiguous)<6: continue
            periods=[y for y,_ in contiguous]; values=[v for _,v in contiguous]
            pats,analysis,score=detect(values)
            if not pats or score<67: continue
            cur,prev=values[-1],values[-2]; period=periods[-1]
            movement="sale" if cur>prev else "scende" if cur<prev else "resta stabile"
            eid=hashlib.sha256(f"AMC|{spec['indicator']}|{code}|{period}".encode()).hexdigest()[:16]
            candidates.append({
              "id":eid,"municipality_code":code,"municipality":comune,"province":province,"region":region,
              "indicator":f"{spec['area']} · {spec['indicator']}","patterns":"|".join(pats),"scope":"TERRITORIALE",
              "score":round(score,1),"validation_status":"SEGNALE PULSE — A MISURA DI COMUNE",
              "period":str(period),"summary":f"{comune}: {spec['indicator']} {movement} da {fmt(prev)} a {fmt(cur)} nel {period}.",
              "annual":"|".join(format(v,".8g") for v in values[-8:]),"rolling12":"","benchmark_local":"","benchmark_rest":"",
              "analysis":"¦".join(analysis+[f"Unità di misura: {spec['unit']}.","Serie storica ufficiale ISTAT A misura di Comune.","ANNUAL_PERIODS:"+"|".join(str(y) for y in periods[-8:]),"Il periodo della notizia è l'anno statistico reale, non la data di pubblicazione 2026."]),
              "source_family":SOURCE,"source_url":PAGE,"_indicator":spec["indicator"]
            })
    if not candidates: raise RuntimeError("No A misura di Comune PULSE signals generated")
    df=pd.DataFrame(candidates)
    # Keep a broad but bounded territorial archive: strongest signals per region and indicator.
    df=(df.sort_values(["region","_indicator","score"],ascending=[True,True,False])
          .groupby(["region","_indicator"],group_keys=False).head(5)
          .sort_values("score",ascending=False).head(650).drop(columns=["_indicator"]))
    OUT.parent.mkdir(parents=True,exist_ok=True)
    df[COLS].to_csv(OUT,sep="\t",index=False)

    catalog=json.loads(CATALOG.read_text(encoding="utf-8"))
    for source in catalog.get("sources",[]):
        if source.get("name")==SOURCE:
            source["integration_status"]="feed"
            source["feed_status"]=f"Feed territoriale storico attivo · {len(df)} segnali PULSE verificati + osservazioni comunali ufficiali."
            source["frequency"]="Periodico; ultimo aggiornamento pagina 26/05/2026"
            source["latest_period"]=str(max(int(x) for x in df["period"]))
            source["publication_period"]="2026-05-26"
            source["notes"]=(
              "A misura di Comune collegato alle tavole XLSX ufficiali ISTAT. "
              "Le osservazioni comunali alimentano il catalogo dati; un archivio PULSE separato "
              "genera segnali storici territoriali mantenendo sempre l'anno statistico reale. "
              "Non viene presentato come notizia corrente 2026 quando il dato si riferisce al 2023/2024."
            )
    CATALOG.write_text(json.dumps(catalog,ensure_ascii=False,indent=2),encoding="utf-8")
    print("A MISURA DI COMUNE PULSE EVENTS",len(df))
    print("REGIONS",df["region"].nunique())
    print("PERIODS",sorted(df["period"].unique()))

if __name__=="__main__":
    main()
