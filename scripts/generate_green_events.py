#!/usr/bin/env python3
from __future__ import annotations

import io
import json
import os
import re
import tempfile
import urllib.request
import zipfile
from collections import defaultdict
from pathlib import Path
from urllib.parse import urljoin

import numpy as np
import pandas as pd
from bs4 import BeautifulSoup

from green_common import (
    Observation, AdapterResult, observations_frame, events_frame,
    events_from_observations, clean_text, to_float
)

OUT_OBS=Path("data/pulse_green_observations.tsv")
OUT_EVENTS=Path("data/pulse_events_green.tsv")
OUT_MANIFEST=Path("data/pulse_green_manifest.json")
OUT_STATUS=Path("data/green_source_status.json")

UA={
    "User-Agent":"ISTAT-PULSE-GREEN/1.0 (+https://github.com/pierfido89/ISTAT-PULSE-DATA)",
    "Accept":"*/*",
}
SDG_URL="https://www.istat.it/wp-content/uploads/2026/07/Misure-statistiche-2004-2026.xlsx"

PILLAR_CLIMATE="Crisi climatica e decarbonizzazione"
PILLAR_ENERGY="Transizione energetica"
PILLAR_CIRCULAR="Economia circolare"
PILLAR_BIODIV="Tutela della biodiversità"
PILLAR_WATER_SOIL="Gestione delle risorse idriche e del suolo"
PILLAR_MOBILITY="Mobilità sostenibile"

REGION_NORMALIZE={
    "Valle d'Aosta/Vallée d'Aoste":"Valle d'Aosta",
    "Trentino-Alto Adige/Südtirol":"Trentino-Alto Adige",
    "Friuli-Venezia Giulia":"Friuli Venezia Giulia",
    "Emilia Romagna":"Emilia-Romagna",
}

def norm_region(v):
    s=clean_text(v)
    return REGION_NORMALIZE.get(s,s)

def fetch(url,headers=None,timeout=180):
    h=dict(UA); h.update(headers or {})
    req=urllib.request.Request(url,headers=h)
    with urllib.request.urlopen(req,timeout=timeout) as r:
        return r.read(),r.geturl(),dict(r.headers)

def excel(raw, sheet_name=0, **kwargs):
    return pd.read_excel(io.BytesIO(raw),sheet_name=sheet_name,engine="openpyxl",**kwargs)

def ods_from_bytes(raw, sheet_name=0, **kwargs):
    with tempfile.NamedTemporaryFile(suffix=".ods") as tmp:
        tmp.write(raw); tmp.flush()
        return pd.read_excel(tmp.name,sheet_name=sheet_name,engine="odf",**kwargs)

def result(name,status,obs,detail="",mode="direct",url=""):
    return AdapterResult(name,status,obs,detail,mode,url)

def safe_adapter(name, fn):
    try:
        r=fn()
        if not isinstance(r,AdapterResult):
            raise TypeError("adapter did not return AdapterResult")
        print(f"[GREEN] {name}: {r.status} · {len(r.observations)} observations · {r.detail}")
        return r
    except Exception as exc:
        print(f"[GREEN] {name}: ERROR {exc!r}")
        return result(name,"error",[],repr(exc),"error","")

def find_col(columns,*parts):
    for c in columns:
        s=clean_text(c).lower()
        if all(p.lower() in s for p in parts):
            return c
    return None

def first_year_columns(columns):
    out=[]
    for c in columns:
        m=re.search(r"((?:19|20)\d{2})",str(c))
        if m: out.append((c,m.group(1)))
    return out

def iter_year_values(row, columns):
    for c,year in first_year_columns(columns):
        v=to_float(row.get(c))
        if v is not None:
            yield year,v

def year_string(value):
    if isinstance(value,(int,np.integer)):
        y=int(value); return str(y) if 1900<=y<=2100 else ""
    if isinstance(value,(float,np.floating)) and np.isfinite(value):
        y=int(round(float(value))); return str(y) if 1900<=y<=2100 else ""
    s=clean_text(value)
    m=re.search(r"(?:19|20)\d{2}",s)
    return m.group(0) if m else ""

def observations_from_sdg_source(source_keyword,source_name,pillar,measure_regex=None):
    raw,final,_=fetch(SDG_URL)
    df=excel(raw,"Goal 1-17")
    cols={str(c).strip():c for c in df.columns}
    source_col=cols.get("FONTE")
    measure_col=cols.get("MISURA STATISTICA")
    dim_col=cols.get("DIMENSIONE")
    level_col=cols.get("LIVELLO TERRITORIALE")
    unit_col=cols.get("UNITÀ")
    if source_col is None or measure_col is None:
        raise RuntimeError("unexpected ISTAT SDG schema")
    mask=df[source_col].astype(str).str.contains(source_keyword,case=False,na=False)
    if dim_col is not None:
        mask &= df[dim_col].astype(str).str.contains("Territorio",case=False,na=False)
    if level_col is not None:
        mask &= df[level_col].astype(str).str.contains("Italia",case=False,na=False)
    if measure_regex:
        mask &= df[measure_col].astype(str).str.contains(measure_regex,case=False,na=False,regex=True)
    obs=[]
    for _,row in df[mask].iterrows():
        indicator=clean_text(row[measure_col])
        if not indicator: continue
        unit=clean_text(row[unit_col]) if unit_col is not None else ""
        for year,value in iter_year_values(row,df.columns):
            obs.append(Observation(
                pillar,source_name,SDG_URL,"ITALIA","Italia",indicator,unit,year,value,
                region="Italia",
                note=f"Fonte originale {source_keyword}; serie distribuita nel file ufficiale ISTAT SDGs.",
                series_key=clean_text(row.get(cols.get("COD_MISURA",""),""))
            ))
    return obs

# 1 — ACI --------------------------------------------------------------------
def adapter_aci():
    name="ACI - Open data mobilità e parco veicoli"
    url="https://aci.gov.it/app/uploads/2026/05/Annuario-statistico-2026-OD.zip"
    raw,final,_=fetch(url)
    z=zipfile.ZipFile(io.BytesIO(raw))
    member=next(n for n in z.namelist() if n.endswith("Capitolo 2 2026.ods"))
    ods=z.read(member)
    df=ods_from_bytes(ods,"TABII03",header=None)
    header_idx=None
    for i,row in df.iterrows():
        if any(clean_text(x).upper()=="ANNI" for x in row if pd.notna(x)):
            header_idx=i; break
    if header_idx is None: raise RuntimeError("ACI TABII03 header not found")
    header=[clean_text(x) for x in df.iloc[header_idx].tolist()]
    body=df.iloc[header_idx+1:].copy()
    body.columns=header
    year_col=find_col(body.columns,"ANNI") or body.columns[0]
    electric=find_col(body.columns,"Elettrico")
    hybrid=find_col(body.columns,"Ibrido")
    total=find_col(body.columns,"TOTALE")
    obs=[]
    for _,r in body.iterrows():
        year=re.search(r"(?:19|20)\d{2}",clean_text(r.get(year_col)))
        if not year: continue
        y=year.group(0)
        vals=[
            ("Prime iscrizioni autovetture elettriche",electric,"veicoli"),
            ("Prime iscrizioni autovetture ibride",hybrid,"veicoli"),
        ]
        for ind,c,u in vals:
            v=to_float(r.get(c)) if c else None
            if v is not None:
                obs.append(Observation(PILLAR_MOBILITY,name,final,"ITALIA","Italia",ind,u,y,v,region="Italia",
                    note="Prime iscrizioni di autovetture nuove di fabbrica secondo alimentazione."))
        if electric and total:
            ev,tv=to_float(r.get(electric)),to_float(r.get(total))
            if ev is not None and tv and tv>0:
                obs.append(Observation(PILLAR_MOBILITY,name,final,"ITALIA","Italia",
                    "Quota autovetture elettriche sulle prime iscrizioni","%",y,100*ev/tv,region="Italia",
                    note="Calcolo PULSE su dati ACI: elettriche / totale prime iscrizioni."))
    return result(name,"live",obs,f"Annuario ACI 2026: {len(obs)} osservazioni","direct",final)

# 2 — ARERA ------------------------------------------------------------------
def adapter_arera():
    name="ARERA - Statistiche del servizio idrico"
    urls={
        2017:"https://www.arera.it/fileadmin/allegati/dati/idr/RQSII_17.xlsx",
        2018:"https://www.arera.it/fileadmin/allegati/dati/idr/RQSII_18.xlsx",
        2019:"https://www.arera.it/fileadmin/allegati/dati/idr/RQSII_19.xlsx",
        2020:"https://www.arera.it/allegati/dati/idr/RQSII_2020.xlsx",
        2021:"https://www.arera.it/fileadmin/allegati/dati/idr/RQSII_2021.xlsx",
    }
    obs=[]
    for year,url in urls.items():
        try:
            raw,final,_=fetch(url)
            df=excel(raw,"Totali Gestioni e Indicatori")
            c_ent=find_col(df.columns,"Entro","standard")
            c_out=find_col(df.columns,"Fuori","Standard")
            if not c_ent or not c_out: continue
            ent=pd.to_numeric(df[c_ent],errors="coerce").sum()
            out=pd.to_numeric(df[c_out],errors="coerce").sum()
            if ent+out>0:
                obs.append(Observation(PILLAR_WATER_SOIL,name,final,"ITALIA","Italia",
                    "Prestazioni servizio idrico entro standard","%",str(year),100*ent/(ent+out),region="Italia",
                    note="Indicatore PULSE ricavato dalle prestazioni riportate da ARERA; misura qualità del servizio, non disponibilità idrica."))
        except Exception as exc:
            print("  ARERA",year,repr(exc))
    return result(name,"live" if len(obs)>=3 else "partial",obs,"Serie 2017-2021 qualità servizio","direct",urls[2021])

# 3 — Copernicus --------------------------------------------------------------
def adapter_copernicus():
    name="Copernicus - Climate Data Store"
    url="https://climate.copernicus.eu/sites/default/files/custom-uploads/indicators-2025/temperature/fig4/fig4b_data.csv"
    raw,final,_=fetch(url)
    df=pd.read_csv(io.BytesIO(raw),skiprows=3)
    year=find_col(df.columns,"Year")
    era=find_col(df.columns,"ERA5")
    obs=[]
    for _,r in df.iterrows():
        y=year_string(r.get(year)); v=to_float(r.get(era))
        if y and v is not None:
            obs.append(Observation(PILLAR_CLIMATE,name,final,"EUROPA","Europa",
                "Anomalia temperatura media annua europea (ERA5, base 1991-2020)","°C",y,v,
                region="Europa",note="Indicatore climatico europeo pubblicato da Copernicus Climate Change Service; non è un valore specifico dell'Italia."))
    return result(name,"live",obs,"Serie ERA5 europea pubblica senza credenziali CDS","direct_static",final)

# 4 — EEA ---------------------------------------------------------------------
def _eea_one(slug,indicator,unit,pillar):
    page=f"https://www.eea.europa.eu/en/europe-environment-2025/countries/data-download/{slug}.csv/@@download/file"
    raw,final,_=fetch(page)
    df=pd.read_csv(io.BytesIO(raw))
    year=df.columns[0]
    italy=next((c for c in df.columns if c.lower().startswith("italy_")),None)
    if italy is None:return []
    obs=[]
    for _,r in df.iterrows():
        y=year_string(r[year]);v=to_float(r[italy])
        if y and v is not None:
            obs.append(Observation(pillar,"EEA - Dati ambientali europei",final,"ITALIA","Italia",indicator,unit,y,v,region="Italia",
                note="Serie armonizzata EEA per l'Italia."))
    return obs

def adapter_eea():
    name="EEA - Dati ambientali europei"
    specs=[
      ("ee25-total-greenhouse-gas-emissions-all-eea38-countries","Emissioni totali di gas serra (indice EEA)","%",PILLAR_CLIMATE),
      ("ee25-renewable-energy-sources-all-eea38-countries","Quota energia da fonti rinnovabili (EEA)","%",PILLAR_ENERGY),
      ("ee25-circular-material-use-rate-all-eea38-countries","Tasso di uso circolare dei materiali (EEA)","%",PILLAR_CIRCULAR),
      ("ee25-terrestrial-protected-areas-all-eea38-countries","Aree terrestri protette (EEA)","%",PILLAR_BIODIV),
      ("ee25-health-impacts-of-air-pollution-all-eea38-countries","Impatto sanitario dell'inquinamento atmosferico (EEA)","",PILLAR_CLIMATE),
      ("ee25-waste-generation-all-eea38-countries","Produzione di rifiuti (EEA)","",PILLAR_CIRCULAR),
    ]
    obs=[]
    ok=0
    for spec in specs:
        try:
            got=_eea_one(*spec); obs.extend(got); ok+=bool(got)
        except Exception as exc: print("  EEA",spec[0],repr(exc))
    return result(name,"live" if ok>=3 else "partial",obs,f"{ok}/{len(specs)} serie EEA connesse","direct",
        "https://www.eea.europa.eu/en/europe-environment-2025/countries/data-download")

# 5 — ENEA --------------------------------------------------------------------
def adapter_enea():
    name="ENEA - Rapporto annuale efficienza energetica"
    regions=[
      ("Abruzzo",798),("Basilicata",799),("Calabria",800),("Campania",801),
      ("Emilia-Romagna",802),("Friuli Venezia Giulia",803),("Lazio",804),("Liguria",805),
      ("Lombardia",806),("Marche",807),("Molise",808),("Piemonte",809),("Puglia",810),
      ("Sardegna",811),("Sicilia",812),("Toscana",813),("Trentino-Alto Adige",814),
      ("Umbria",815),("Valle d'Aosta",816),("Veneto",817)
    ]
    obs=[]
    for region,id_ in regions:
        url=f"https://www.efficienzaenergetica.enea.it/component/jdownloads/?task=download.send&id={id_}&catid=40&Itemid=101"
        try:
            raw,final,_=fetch(url)
            df=excel(raw,"BER sintesi",header=None)
            # Header row with energy carriers.
            hidx=next((i for i,row in df.iterrows() if any("Energie rinnovabili" in clean_text(x) for x in row)),None)
            ridx=next((i for i,row in df.iterrows() if clean_text(row.iloc[0]).lower()=="produzione"),None)
            if hidx is None or ridx is None: continue
            headers=[clean_text(x) for x in df.iloc[hidx].tolist()]
            renewable_idx=next((i for i,h in enumerate(headers) if "Energie rinnovabili" in h),None)
            total_idx=next((i for i,h in enumerate(headers) if h=="Totale"),None)
            rv=to_float(df.iloc[ridx,renewable_idx]) if renewable_idx is not None else None
            tv=to_float(df.iloc[ridx,total_idx]) if total_idx is not None else None
            if rv is not None:
                obs.append(Observation(PILLAR_ENERGY,name,final,"REGIONE",region,
                    "Produzione energetica da fonti rinnovabili","ktep","2024",rv,region=region,
                    note="Bilancio energetico regionale di sintesi ENEA 2024."))
            if rv is not None and tv and tv>0:
                obs.append(Observation(PILLAR_ENERGY,name,final,"REGIONE",region,
                    "Quota rinnovabili sulla produzione energetica regionale","%","2024",100*rv/tv,region=region,
                    note="Rapporto tra produzione rinnovabile e produzione energetica totale nel BER ENEA."))
        except Exception as exc: print("  ENEA",region,repr(exc))
    return result(name,"live" if len(obs)>=15 else "partial",obs,f"{len(obs)} indicatori regionali 2024","direct",
        "https://www.efficienzaenergetica.enea.it/vi-segnaliamo/rapporto-annuale-sullefficienza-energetica-2026-schede-regionali.html")

# 6 — Eurostat ----------------------------------------------------------------
def _eurostat_series(code,indicator,unit,pillar,extra=""):
    url=f"https://ec.europa.eu/eurostat/api/dissemination/statistics/1.0/data/{code}?geo=IT&lang=en{extra}"
    raw,final,_=fetch(url); obj=json.loads(raw)
    time_idx=obj["dimension"]["time"]["category"]["index"]
    time_by_pos={v:k for k,v in time_idx.items()}
    vals=obj.get("value",{})
    obs=[]
    # With all non-time dimensions filtered to one value, flat positions equal time positions.
    for k,v in vals.items():
        pos=int(k)
        if pos not in time_by_pos: continue
        year=time_by_pos[pos]
        fv=to_float(v)
        if fv is not None:
            obs.append(Observation(pillar,"Eurostat - Statistiche ambientali ed energia",final,"ITALIA","Italia",indicator,unit,year,fv,
                region="Italia",note=f"Eurostat dataset {code}."))
    return obs

def adapter_eurostat():
    name="Eurostat - Statistiche ambientali ed energia"
    obs=[]
    obs += _eurostat_series("sdg_12_41","Tasso di uso circolare dei materiali","%",PILLAR_CIRCULAR)
    obs += _eurostat_series("sdg_07_40","Quota complessiva di energia rinnovabile","%",PILLAR_ENERGY,"&nrg_bal=REN")
    return result(name,"live",obs,"API Eurostat: economia circolare + rinnovabili","direct",
        "https://ec.europa.eu/eurostat/web/environment")

# 7 — GSE via official ISTAT SDG ---------------------------------------------
def adapter_gse():
    name="GSE - Statistiche delle rinnovabili"
    obs=observations_from_sdg_source("GSE",name,PILLAR_ENERGY,r"rinnovabil|energia")
    return result(name,"live" if obs else "error",obs,
        "Dati GSE acquisiti dalla distribuzione ufficiale ISTAT SDGs (host GSE blocca il runner).",
        "official_via_istat_sdg",SDG_URL)

# 8 — ISPRA rifiuti -----------------------------------------------------------
def _read_rifiuti_year(year):
    url=f"https://www.catasto-rifiuti.isprambiente.it/get/getDettaglioComunale.csv.php?&aa={year}"
    raw,final,_=fetch(url)
    text=raw.decode("utf-8-sig","replace")
    # First line is a title; header follows.
    df=pd.read_csv(io.StringIO(text),sep=";",skiprows=1,dtype=str,low_memory=False)
    return df,final

def adapter_isprarifiuti():
    name="ISPRA - Catasto nazionale rifiuti"
    obs=[]
    for year in range(2018,2025):
        try:
            df,url=_read_rifiuti_year(year)
            cols=list(df.columns)
            c_code=find_col(cols,"IstatComune") or find_col(cols,"Istat","Comune")
            c_reg=find_col(cols,"Regione")
            c_prov=find_col(cols,"Provincia")
            c_com=find_col(cols,"Comune")
            c_rd=next((c for c in cols if "raccolta" in c.lower() and "differenziata" in c.lower() and ("%" in c or "percent" in c.lower())),None)
            if c_rd is None:
                # choose the shortest RD-looking column to avoid material subcomponents.
                cand=[c for c in cols if "rd" in c.lower() and ("%" in c or "percent" in c.lower())]
                c_rd=min(cand,key=len) if cand else None
            c_pc=next((c for c in cols if "pro capite" in c.lower() and ("ru" in c.lower() or "produzione" in c.lower())),None)
            if not c_com or not c_reg: continue
            for _,r in df.iterrows():
                reg=norm_region(r.get(c_reg)); com=clean_text(r.get(c_com)); prov=clean_text(r.get(c_prov))
                if not reg or not com: continue
                for ind,c,u in [
                    ("Raccolta differenziata dei rifiuti urbani",c_rd,"%"),
                    ("Produzione pro capite di rifiuti urbani",c_pc,"kg/ab"),
                ]:
                    v=to_float(r.get(c)) if c else None
                    if v is not None:
                        obs.append(Observation(PILLAR_CIRCULAR,name,url,"COMUNE",com,ind,u,str(year),v,
                            region=reg,province=prov,municipality_code=clean_text(r.get(c_code)) if c_code else "",
                            note="Catasto nazionale rifiuti ISPRA, download comunale annuale."))
        except Exception as exc: print("  RIFIUTI",year,repr(exc))
    return result(name,"live" if len(obs)>1000 else "partial",obs,f"{len(obs)} osservazioni comunali 2018-2024","direct",
        "https://www.catasto-rifiuti.isprambiente.it/index.php?advice=si&pg=downloadComune")

# 9 — ISPRA soil --------------------------------------------------------------
def adapter_isprasuolo():
    name="ISPRA - Consumo di suolo e indicatori territoriali"
    url="https://www.isprambiente.gov.it/it/attivita/suolo-e-territorio/suolo/il-consumo-di-suolo/consumo_di_suolo_estratto_dati_2025_anni_2006_2024.xlsx"
    raw,final,_=fetch(url)
    df=excel(raw,"Regioni_2006_2024")
    obs=[]
    c_reg=find_col(df.columns,"Nome_Regione")
    for _,r in df.iterrows():
        reg=norm_region(r.get(c_reg))
        if not reg:continue
        for c in df.columns:
            m=re.match(r"Incremento netto (\d{4})-(\d{4}) \[ettari\]",str(c))
            if m:
                v=to_float(r.get(c))
                if v is not None:
                    obs.append(Observation(PILLAR_WATER_SOIL,name,final,"REGIONE",reg,
                        "Incremento netto del consumo di suolo","ettari",m.group(2),v,region=reg,
                        note="ISPRA consumo di suolo: incremento netto nel periodo terminante nell'anno indicato."))
        c_pct=find_col(df.columns,"Suolo consumato 2024","%")
        if c_pct:
            v=to_float(r.get(c_pct))
            if v is not None:
                obs.append(Observation(PILLAR_WATER_SOIL,name,final,"REGIONE",reg,
                    "Suolo consumato","%","2024",v,region=reg,note="Quota di superficie artificiale complessiva rilevata da ISPRA."))
    return result(name,"live",obs,f"{len(obs)} osservazioni regionali 2006-2024","direct",final)

# 10 — IdroGEO ---------------------------------------------------------------
def adapter_idrogeo():
    name="ISPRA - IdroGEO"
    obs=[]
    for rid in range(1,21):
        url=f"https://idrogeo.isprambiente.it/api/pir/regioni/{rid}"
        try:
            raw,final,_=fetch(url); x=json.loads(raw)
            reg=norm_region(x.get("nome"))
            for ind,field,unit in [
                ("Popolazione esposta ad alluvioni - pericolosità elevata P3","popidp3_p","%"),
                ("Popolazione esposta ad alluvioni - pericolosità media P2","popidp2_p","%"),
                ("Popolazione esposta a frane P3-P4","popfrp3p4p","%"),
            ]:
                v=to_float(x.get(field))
                if v is not None:
                    obs.append(Observation(PILLAR_WATER_SOIL,name,final,"REGIONE",reg,ind,unit,"2021",v,region=reg,
                        note="IdroGEO ISPRA: percentuale calcolata sulla popolazione residente usata dalla piattaforma; la mappa rappresenta pericolosità/esposizione, non una previsione di eventi."))
        except Exception as exc: print("  IDROGEO",rid,repr(exc))
    return result(name,"live" if len(obs)>=50 else "partial",obs,f"{len(obs)} indicatori regionali di esposizione","direct",
        "https://idrogeo.isprambiente.it/api/")

# 11 — Biodiversity -----------------------------------------------------------
def adapter_biodiv():
    name="ISPRA - Indicatori ambientali e biodiversità"
    url="https://indicatoriambientali.isprambiente.it/sites/default/files/indicatori_ambientali/2026-06-12/TAB%201_specie%20DH.xlsx"
    raw,final,_=fetch(url);df=excel(raw,"tabella",header=None)
    obs=[]
    # The last column of the row "Specie" is the official total.
    for _,r in df.iterrows():
        if clean_text(r.iloc[0]).lower()=="specie":
            vals=[to_float(v) for v in r.iloc[1:].tolist()]
            vals=[v for v in vals if v is not None]
            if vals:
                obs.append(Observation(PILLAR_BIODIV,name,final,"ITALIA","Italia",
                    "Specie rendicontate ai sensi della Direttiva Habitat","specie","2026",vals[-1],region="Italia",
                    note="Snapshot nazionale ISPRA del reporting Direttiva Habitat; non è una serie temporale."))
    # Additional official table if available.
    url2="https://indicatoriambientali.isprambiente.it/sites/default/files/indicatori_ambientali/2026-06-12/TAB%202_specie%20DH.xlsx"
    try:
        b,u,_=fetch(url2); d=excel(b,"tabella",header=None)
        # Preserve meaningful totals from labelled rows without inventing semantics.
        for _,r in d.iterrows():
            label=clean_text(r.iloc[0])
            if label and re.search(r"favorevol|inadeguat|cattiv|sconosciut",label,re.I):
                vals=[to_float(v) for v in r.iloc[1:].tolist()]
                vals=[v for v in vals if v is not None]
                if vals:
                    obs.append(Observation(PILLAR_BIODIV,name,u,"ITALIA","Italia",
                        f"Stato di conservazione specie - {label}","n.","2026",vals[-1],region="Italia",
                        note="Tabella ufficiale ISPRA sulla Direttiva Habitat."))
    except Exception as exc: print("  BIODIV tab2",repr(exc))
    return result(name,"live",obs,f"{len(obs)} indicatori nazionali ufficiali","direct",final)

# 12 — ISPRA GHG --------------------------------------------------------------
def _find_excel_series(raw, label_regex, source_name, pillar, url, unit_hint=""):
    xls=pd.ExcelFile(io.BytesIO(raw),engine="openpyxl")
    obs=[]
    for sh in xls.sheet_names:
        try: df=pd.read_excel(io.BytesIO(raw),sheet_name=sh,header=None,engine="openpyxl")
        except Exception: continue
        # Search a row whose cells include our label, then detect years across same row/adjacent row.
        for i,row in df.iterrows():
            cells=[clean_text(v) for v in row.tolist()]
            if not any(re.search(label_regex,c,re.I) for c in cells if c): continue
            # If row itself has year-value pairs in alternating cells, collect them.
            for j,c in enumerate(cells):
                if re.fullmatch(r"(?:19|20)\d{2}",c):
                    for k in range(j+1,min(j+3,len(cells))):
                        v=to_float(row.iloc[k])
                        if v is not None:
                            obs.append(Observation(pillar,source_name,url,"ITALIA","Italia",
                                clean_text(next((x for x in cells if re.search(label_regex,x,re.I)),"Indicatore")),
                                unit_hint,c,v,region="Italia",note=f"Foglio {sh}."))
                            break
            if obs:return obs
    return obs

def adapter_emissions():
    name="ISPRA - Inventario nazionale delle emissioni"
    page="https://emissioni.sina.isprambiente.it/serie-storiche-emissioni-di-gas-serra-sintesi/"
    rawp,_,_=fetch(page); soup=BeautifulSoup(rawp.decode("utf-8","ignore"),"html.parser")
    link=next((urljoin(page,a["href"]) for a in soup.find_all("a",href=True)
               if re.search(r"Emissioni-GHG.*\.xlsx",a["href"],re.I)),None)
    if not link:raise RuntimeError("GHG workbook link not found")
    raw,final,_=fetch(link)
    xls=pd.ExcelFile(io.BytesIO(raw),engine="openpyxl")
    obs=[]
    # Generic structure-aware scan: years usually run across columns; identify total GHG row.
    for sh in xls.sheet_names:
        df=pd.read_excel(io.BytesIO(raw),sheet_name=sh,header=None,engine="openpyxl")
        year_row=None
        for i,row in df.head(30).iterrows():
            years=sum(bool(re.fullmatch(r"(?:19|20)\d{2}",clean_text(v))) for v in row)
            if years>=5: year_row=i;break
        if year_row is None:continue
        years=[clean_text(v) for v in df.iloc[year_row].tolist()]
        candidates=[]
        for i in range(year_row+1,len(df)):
            label=" ".join(clean_text(v) for v in df.iloc[i,:5].tolist() if clean_text(v))
            if re.search(r"total.*(?:greenhouse|ghg|gas serra)|(?:greenhouse|ghg|gas serra).*total",label,re.I):
                candidates.append((i,label))
        if not candidates:
            for i in range(year_row+1,len(df)):
                label=" ".join(clean_text(v) for v in df.iloc[i,:5].tolist() if clean_text(v))
                if re.search(r"totale|total",label,re.I): candidates.append((i,label))
        if candidates:
            i,label=candidates[0]
            for j,y in enumerate(years):
                if re.fullmatch(r"(?:19|20)\d{2}",y):
                    v=to_float(df.iloc[i,j])
                    if v is not None:
                        obs.append(Observation(PILLAR_CLIMATE,name,final,"ITALIA","Italia",
                            "Emissioni nazionali di gas serra", "kt CO2eq",y,v,region="Italia",
                            note=f"Inventario nazionale ISPRA; foglio {sh}."))
            if len(obs)>=10:break
    return result(name,"live" if len(obs)>=10 else "partial",obs,f"{len(obs)} osservazioni GHG","direct",final)

# 13 — BIGBANG water resources ------------------------------------------------
def adapter_waterresources():
    name="ISPRA - Risorse idriche"
    url="https://groupware.sinanet.isprambiente.it/bigbang-data/library/bigbang100/excel_tables/bigbang100_tables_italy_01/download/en/1/BIGBANG100_TABLES_ITALY_01.xlsx"
    raw,final,_=fetch(url)
    df=excel(raw,"Annuale (Annual)",header=0,skiprows=[1])
    obs=[]
    c_year=df.columns[1]
    for _,r in df.iterrows():
        year=clean_text(r.get(c_year))
        if not re.fullmatch(r"\d{4}",year):continue
        for ind,c,u in [
            ("Precipitazione totale annua","TP","mm"),
            ("Risorsa idrica rinnovabile annua","RF","km3"),
            ("Water storage annuo","WS","km3"),
        ]:
            if c in df.columns:
                v=to_float(r.get(c))
                if v is not None:
                    obs.append(Observation(PILLAR_WATER_SOIL,name,final,"ITALIA","Italia",ind,u,year,v,region="Italia",
                        note="Bilancio idrologico nazionale BIGBANG ISPRA."))
    return result(name,"live",obs,f"{len(obs)} osservazioni idrologiche annuali","direct",final)

# 14 — Air quality -------------------------------------------------------------
def _air_trend(url,indicator,source_name):
    raw,final,_=fetch(url)
    xls=pd.ExcelFile(io.BytesIO(raw),engine="openpyxl")
    obs=[]
    for sh in xls.sheet_names:
        df=pd.read_excel(io.BytesIO(raw),sheet_name=sh,header=None,engine="openpyxl")
        # detect year columns
        best=None
        for i,row in df.head(30).iterrows():
            pairs=[(j,clean_text(v)) for j,v in enumerate(row) if re.fullmatch(r"20(?:1[5-9]|2[0-4])",clean_text(v))]
            if len(pairs)>=4:
                best=(i,pairs);break
        if not best:continue
        hi,pairs=best
        # Find a row label / station and aggregate national median for each year.
        for j,y in pairs:
            vals=[]
            for i in range(hi+1,len(df)):
                v=to_float(df.iloc[i,j])
                if v is not None: vals.append(v)
            if len(vals)>=5:
                obs.append(Observation(PILLAR_CLIMATE,source_name,final,"ITALIA","Italia",indicator,"µg/m³",y,float(np.median(vals)),region="Italia",
                    note="Mediana PULSE delle stazioni con serie valida nel file trend ISPRA; non è una media di esposizione della popolazione."))
        if obs:break
    return obs

def adapter_air():
    name="ISPRA/SNPA - Qualità dell'aria"
    obs=[]
    try: obs+=_air_trend(
      "https://indicatoriambientali.isprambiente.it/sites/default/files/indicatori_ambientali/2025-12-12/TABELLA_4_NO2_TREND%20%282015-2024%29.xlsx",
      "Concentrazione NO₂ - mediana stazioni con trend","ISPRA/SNPA - Qualità dell'aria")
    except Exception as exc:print("  NO2",repr(exc))
    try: obs+=_air_trend(
      "https://indicatoriambientali.isprambiente.it/sites/default/files/indicatori_ambientali/2025-12-10/TABELLA_3_PM25_TREND%20%282015-2024%29_rev.xlsx",
      "Concentrazione PM2.5 - mediana stazioni con trend","ISPRA/SNPA - Qualità dell'aria")
    except Exception as exc:print("  PM25",repr(exc))
    return result(name,"live" if len(obs)>=10 else "partial",obs,f"{len(obs)} osservazioni trend aria 2015-2024","direct",
        "https://indicatoriambientali.isprambiente.it/it/qualita-dellaria")

# 15 — ISTAT Ambiente urbano --------------------------------------------------
def _flatten_city_table(df):
    hidx=None
    for i,row in df.head(20).iterrows():
        if "COMUNI" in clean_text(row.iloc[0]).upper():
            hidx=i;break
    if hidx is None:return None,None
    # combine up to four header rows from hidx onward.
    hrows=df.iloc[hidx:min(hidx+5,len(df))]
    labels=[]
    for j in range(df.shape[1]):
        parts=[]
        for v in hrows.iloc[:,j]:
            s=clean_text(v)
            if s and s.lower()!="nan" and s not in parts:parts.append(s)
        labels.append(" | ".join(parts))
    body=df.iloc[hidx+1:].copy()
    body.columns=labels
    return body,labels

def _urban_extract(workbook_bytes,member,target_regex,indicator,unit):
    z=None
    # member bytes already supplied as xlsx
    xls=pd.ExcelFile(io.BytesIO(workbook_bytes),engine="openpyxl")
    obs=[]
    for sh in xls.sheet_names:
        if sh.lower().startswith(("indice","prosp")):continue
        rawdf=pd.read_excel(io.BytesIO(workbook_bytes),sheet_name=sh,header=None,engine="openpyxl")
        body,labels=_flatten_city_table(rawdf)
        if body is None:continue
        target=next((c for c in labels[1:] if re.search(target_regex,c,re.I)),None)
        if not target:continue
        first=labels[0]
        # period: latest year in label/title, default 2024.
        years=re.findall(r"20\d{2}"," ".join(labels))
        period=max(years) if years else "2024"
        for _,r in body.iterrows():
            city=clean_text(r.get(first))
            if not city or city.upper().startswith(("ITALIA","NORD","CENTRO","SUD","ISOLE","RIPARTIZ")):continue
            v=to_float(r.get(target))
            if v is not None:
                obs.append((city,period,v,sh,target))
        if len(obs)>=20:return obs
    return obs

def adapter_urban():
    name="ISTAT - Ambiente urbano"
    url="https://www.istat.it/wp-content/uploads/2026/09/TAVOLE_AMBURB_2024.zip"
    raw,final,_=fetch(url);z=zipfile.ZipFile(io.BytesIO(raw))
    specs=[
      ("VERDE_URBANO_2024.xlsx",r"disponibil.*verde|m2.*abit|verde.*pro capite","Disponibilità di verde urbano","m²/ab",PILLAR_BIODIV),
      ("MOBILITA_URBANA_2024.xlsx",r"trasporto pubblico|domanda.*tpl|passeggeri","Indicatore mobilità/trasporto pubblico urbano","",PILLAR_MOBILITY),
      ("RIFIUTI_URBANI_2024.xlsx",r"raccolta differenziata.*%|percent.*raccolta differenziata","Raccolta differenziata nei capoluoghi","%",PILLAR_CIRCULAR),
      ("ENERGIA_2024.xlsx",r"fotovolta|solare|rinnovabil","Indicatore energia rinnovabile urbana","",PILLAR_ENERGY),
      ("ACQUA_2024.xlsx",r"acqua fatturata.*pro capite|pro capite.*acqua","Acqua fatturata pro capite","",PILLAR_WATER_SOIL),
    ]
    obs=[]
    for member,regex,indicator,unit,pillar in specs:
        try:
            b=z.read(member); rows=_urban_extract(b,member,regex,indicator,unit)
            for city,period,v,sh,label in rows:
                obs.append(Observation(pillar,name,final,"COMUNE",city,indicator,unit,period,v,
                    note=f"ISTAT Ambiente urbano 2024, {member}, {sh}; colonna: {label[:180]}."))
        except Exception as exc:print("  URBAN",member,repr(exc))
    return result(name,"live" if len(obs)>=20 else "partial",obs,f"{len(obs)} osservazioni da tavole Ambiente urbano","direct",final)

# 16 — ISTAT SDGs -------------------------------------------------------------
def adapter_sdg():
    name="ISTAT - Indicatori SDGs"
    raw,final,_=fetch(SDG_URL);df=excel(raw,"Goal 1-17")
    obs=[]
    green_goals=("Goal 6","Goal 7","Goal 11","Goal 12","Goal 13","Goal 14","Goal 15")
    for _,r in df.iterrows():
        goal=clean_text(r.get("GOAL"))
        if not goal.startswith(green_goals):continue
        if "Territorio" not in clean_text(r.get("DIMENSIONE")):continue
        level=clean_text(r.get("LIVELLO TERRITORIALE"))
        if "Italia" not in level:continue
        ind=clean_text(r.get("MISURA STATISTICA")); unit=clean_text(r.get("UNITÀ"))
        if not ind:continue
        pillar=(
            PILLAR_WATER_SOIL if goal.startswith("Goal 6") else
            PILLAR_ENERGY if goal.startswith("Goal 7") else
            PILLAR_MOBILITY if goal.startswith("Goal 11") and re.search(r"trasport|mobil|autovett",ind,re.I) else
            PILLAR_CIRCULAR if goal.startswith("Goal 12") else
            PILLAR_CLIMATE if goal.startswith("Goal 13") else
            PILLAR_BIODIV if goal.startswith(("Goal 14","Goal 15")) else
            PILLAR_CLIMATE
        )
        for year,v in iter_year_values(r,df.columns):
            obs.append(Observation(pillar,name,final,"ITALIA","Italia",ind,unit,year,v,region="Italia",
                note=f"Indicatore SDG ISTAT; fonte originaria: {clean_text(r.get('FONTE'))}.",
                series_key=clean_text(r.get("COD_MISURA"))))
    return result(name,"live",obs,f"{len(obs)} osservazioni GREEN SDG nazionali","direct",final)

# 17 — ISTAT map of risks -----------------------------------------------------
def adapter_istat_risks():
    name="ISTAT - Mappa dei rischi dei comuni italiani"
    # The public app exposes report endpoints but is token/session based. We verify
    # the live official application and use the directly machine-readable IdroGEO
    # risk metrics in GREEN; here we expose the latest available report years as
    # technical observations rather than fabricating risk values.
    url="https://www.istat.it/wp-content/themes/EGPbs5-child/inc/mappa-rischi/?lang=it"
    raw,final,_=fetch(url)
    html=raw.decode("utf-8","ignore")
    token=re.search(r'name=["\']paramsSelected\[token\]["\'][^>]*value=["\']([^"\']+)',html,re.I)
    js_url="https://www.istat.it/wp-content/themes/EGPbs5-child/inc/mappa-rischi/js/atlrsk.js"
    js,_,_=fetch(js_url)
    live=bool(token and b"Controller.php" in js and b"getReport" in js)
    # No numerical observation emitted unless a report has been downloaded and parsed.
    return result(name,"technical_live" if live else "partial",[],
        "Portale/report ufficiale verificato; valori di rischio GREEN provengono da IdroGEO, per evitare duplicazioni o inferenze dal solo front-end.",
        "technical_live",final)

# 18 — ISTAT water ------------------------------------------------------------
def adapter_istat_water():
    name="ISTAT - Statistiche sull'acqua"
    url="https://www.istat.it/wp-content/uploads/2026/03/Istat-GMA2026-Tavole-1.xlsx"
    raw,final,_=fetch(url);df=excel(raw,"Tavola 1",header=None)
    obs=[]
    # Header at row 2, regional data from row 4.
    headers=[clean_text(x) for x in df.iloc[2].tolist()]
    body=df.iloc[4:].copy(); body.columns=headers
    c_reg=headers[0]
    c_total=next((c for c in headers if c=="Totale"),None)
    c_pc=next((c for c in headers if "pro capite" in c.lower()),None)
    for _,r in body.iterrows():
        reg=norm_region(r.get(c_reg))
        if not reg or reg.upper() in {"ITALIA","NORD","CENTRO","SUD","ISOLE"}:continue
        for ind,c,u in [
            ("Acqua prelevata per uso potabile",c_total,"milioni m³"),
            ("Acqua prelevata pro capite",c_pc,"litri/ab/giorno"),
        ]:
            v=to_float(r.get(c)) if c else None
            if v is not None:
                obs.append(Observation(PILLAR_WATER_SOIL,name,final,"REGIONE",reg,ind,u,"2024",v,region=reg,
                    note="Le statistiche sull'acqua ISTAT, tavola regionale del rilascio 2026."))
    # Rationing days by capital, 2023/2024, Tavola 4.
    try:
        d=excel(raw,"Tavola 4",header=None)
        for i in range(8,len(d)):
            city=clean_text(d.iloc[i,0])
            if not city or city.upper().startswith(("ITALIA","NORD","CENTRO","SUD","ISOLE")):continue
            nums=[to_float(v) for v in d.iloc[i].tolist()]
            nums=[v for v in nums if v is not None]
            # table contains 3 metrics for 2023 then 3 for 2024; total is third of each block.
            if len(nums)>=6:
                obs.append(Observation(PILLAR_WATER_SOIL,name,final,"COMUNE",city,
                    "Giorni di razionamento dell'acqua","giorni","2023",nums[2],
                    note="Razionamento su tutto il territorio comunale, Tavola 4 ISTAT."))
                obs.append(Observation(PILLAR_WATER_SOIL,name,final,"COMUNE",city,
                    "Giorni di razionamento dell'acqua","giorni","2024",nums[5],
                    note="Razionamento su tutto il territorio comunale, Tavola 4 ISTAT."))
    except Exception as exc:print("  ISTAT WATER rationing",repr(exc))
    return result(name,"live",obs,f"{len(obs)} osservazioni acqua regionali/comunali","direct",final)

# 19 — Terna via ISTAT SDGs ---------------------------------------------------
def adapter_terna():
    name="Terna - Portale Dati del sistema elettrico"
    obs=observations_from_sdg_source("Terna",name,PILLAR_ENERGY,r"elettric|rinnovabil|energia")
    return result(name,"live" if obs else "credential_required",obs,
        "Serie Terna ufficiali acquisite tramite ISTAT SDGs; API Terna diretta richiede OAuth.",
        "official_via_istat_sdg",SDG_URL)

ADAPTERS=[
    adapter_aci,adapter_arera,adapter_copernicus,adapter_eea,adapter_enea,
    adapter_eurostat,adapter_gse,adapter_isprarifiuti,adapter_isprasuolo,
    adapter_idrogeo,adapter_biodiv,adapter_emissions,adapter_waterresources,
    adapter_air,adapter_urban,adapter_sdg,adapter_istat_risks,
    adapter_istat_water,adapter_terna,
]

def main():
    results=[safe_adapter(fn.__name__.replace("adapter_",""),fn) for fn in ADAPTERS]
    observations=[]
    for r in results: observations.extend(r.observations)

    # De-duplicate exact canonical observations.
    dedup={}
    for o in observations:
        key=(o.source_name,o.indicator,o.territory_level,o.territory,o.period,o.value)
        dedup[key]=o
    observations=list(dedup.values())
    events=events_from_observations(observations)

    OUT_OBS.parent.mkdir(parents=True,exist_ok=True)
    observations_frame(observations).to_csv(OUT_OBS,sep="\t",index=False)
    events_frame(events).to_csv(OUT_EVENTS,sep="\t",index=False)

    status=[]
    for r in results:
        pillars=sorted({o.pillar for o in r.observations})
        periods=sorted({str(o.period) for o in r.observations},key=lambda x:(re.search(r"\d{4}",x).group(0) if re.search(r"\d{4}",x) else x))
        status.append({
            "name":r.source_name,"status":r.status,"integration_mode":r.integration_mode,
            "observations":len(r.observations),"pillars":pillars,
            "latest_period":periods[-1] if periods else "",
            "detail":r.detail,"checked_url":r.checked_url,
        })
    OUT_STATUS.write_text(json.dumps({"version":1,"sources":status},ensure_ascii=False,indent=2),encoding="utf-8")

    pillar_counts=defaultdict(int)
    for o in observations:pillar_counts[o.pillar]+=1
    source_counts=defaultdict(int)
    for o in observations:source_counts[o.source_name]+=1
    manifest={
        "version":1,
        "green_sources_total":len(results),
        "green_sources_live":sum(r.status=="live" for r in results),
        "green_sources_technical":sum(r.status=="technical_live" for r in results),
        "green_sources_partial":sum(r.status=="partial" for r in results),
        "green_sources_error":sum(r.status=="error" for r in results),
        "observations":len(observations),
        "events":len(events),
        "pillars":dict(pillar_counts),
        "source_observations":dict(source_counts),
        "status_file":str(OUT_STATUS),
    }
    OUT_MANIFEST.write_text(json.dumps(manifest,ensure_ascii=False,indent=2),encoding="utf-8")
    print(json.dumps(manifest,ensure_ascii=False,indent=2))

if __name__=="__main__":
    main()
