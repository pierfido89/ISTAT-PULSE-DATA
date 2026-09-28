#!/usr/bin/env python3
from __future__ import annotations
import io, json, re, tempfile, urllib.request, zipfile
from pathlib import Path
from urllib.parse import urljoin
import pandas as pd
from bs4 import BeautifulSoup

UA={"User-Agent":"Mozilla/5.0 ISTAT-PULSE-GREEN/0.3","Accept":"*/*"}

def get(url, headers=None):
    h=dict(UA); h.update(headers or {})
    req=urllib.request.Request(url,headers=h)
    with urllib.request.urlopen(req,timeout=120) as r:
        return r.read(),r.geturl(),dict(r.headers)

def post(url,payload):
    b=json.dumps(payload).encode()
    req=urllib.request.Request(url,data=b,headers={**UA,"Content-Type":"application/json; charset=utf-8"})
    with urllib.request.urlopen(req,timeout=60) as r:return r.read(),dict(r.headers)

def aci():
    print("\n### ACI DETAIL")
    raw,_,_=get("https://aci.gov.it//app/uploads/2026/05/Annuario-statistico-2026-OD.zip")
    z=zipfile.ZipFile(io.BytesIO(raw))
    for n in z.namelist():
        if not n.lower().endswith(".ods"):continue
        b=z.read(n)
        with tempfile.NamedTemporaryFile(suffix=".ods") as tmp:
            tmp.write(b);tmp.flush()
            try:
                x=pd.ExcelFile(tmp.name,engine="odf")
                print("FILE",n,"SHEETS",x.sheet_names)
                for sh in x.sheet_names:
                    df=pd.read_excel(tmp.name,sheet_name=sh,header=None,engine="odf")
                    # only lines around relevant mobility-energy terms
                    for i,row in df.iterrows():
                        txt=" | ".join(str(v) for v in row.tolist() if pd.notna(v))
                        if re.search(r"elettric|ibrid|alimentaz|carbur|autovett|parco veicol|consistenza",txt,re.I):
                            print("MATCH",n,sh,i,txt[:1800])
            except Exception as e: print("ERR",n,repr(e))

def eea():
    print("\n### EEA RAW")
    url="https://www.eea.europa.eu/en/europe-environment-2025/countries/data-download/ee25-total-greenhouse-gas-emissions-all-eea38-countries.csv/@@download/file"
    raw,final,h=get(url)
    print(len(raw),final,h.get("Content-Type"),raw[:150])
    df=pd.read_csv(io.BytesIO(raw),sep=None,engine="python")
    print("COLS",list(df.columns));print(df[df.astype(str).apply(lambda r:r.str.contains("Italy",case=False).any(),axis=1)].head(12).to_string(index=False))

def rifiuti():
    print("\n### RIFIUTI CSV")
    for y in [2024,2023]:
        url=f"https://www.catasto-rifiuti.isprambiente.it/get/getDettaglioComunale.csv.php?&aa={y}"
        raw,final,h=get(url)
        print("YEAR",y,len(raw),h.get("Content-Type"),raw[:120])
        for enc in ["utf-8-sig","latin1"]:
            try:
                text=raw.decode(enc); break
            except: pass
        for sep in [";","	",","]:
            try:
                df=pd.read_csv(io.StringIO(text),sep=sep,nrows=6)
                if len(df.columns)>3:
                    print("SEP",repr(sep),"COLS",list(df.columns));print(df.head(3).to_string(index=False,max_cols=40));break
            except Exception:pass

def idrogeo():
    print("\n### IDROGEO DETAIL")
    for url in [
      "https://idrogeo.isprambiente.it/api/pir/regioni/12",
      "https://idrogeo.isprambiente.it/api/pir/province/58",
      "https://idrogeo.isprambiente.it/api/pir/comuni/58091",
      "https://idrogeo.isprambiente.it/api/iffi/regioni/12",
    ]:
        try:
            raw,final,h=get(url)
            print("URL",url,"LEN",len(raw),h.get("Content-Type"))
            print(raw[:5000].decode("utf-8","ignore"))
        except Exception as e:print("ERR",url,repr(e))

def links(name,url):
    print("\n### LINKS",name)
    try:
        raw,final,h=get(url);s=BeautifulSoup(raw.decode("utf-8","ignore"),"html.parser")
        print("OK",len(raw),final)
        for a in s.find_all("a",href=True):
            href=urljoin(final,a["href"]);lab=" ".join(a.get_text(" ",strip=True).split())
            if re.search(r"\.(xlsx?|xls|csv|zip)(\?|$)",href,re.I) or "download" in lab.lower():
                print("LINK",lab[:160],href)
    except Exception as e:print("ERR",repr(e))

def copernicus():
    print("\n### COPERNICUS STATIC")
    for url in [
      "https://climate.copernicus.eu/sites/default/files/custom-uploads/indicators-2025/temperature/fig4/fig4b_data.csv",
      "https://climate.copernicus.eu/sites/default/files/custom-uploads/indicators-2025/temperature/fig1/fig1b_data.csv",
    ]:
      try:
        raw,final,h=get(url)
        print("URL",url,len(raw),h.get("Content-Type"),raw[:200])
        df=pd.read_csv(io.BytesIO(raw));print("COLS",list(df.columns));print(df.tail(8).to_string(index=False))
      except Exception as e:print("ERR",repr(e))

def eurostat():
    print("\n### EUROSTAT")
    for code in ["sdg_12_41","sdg_07_40"]:
      url=f"https://ec.europa.eu/eurostat/api/dissemination/statistics/1.0/data/{code}?geo=IT&lang=en"
      try:
        raw,final,h=get(url);obj=json.loads(raw)
        print("CODE",code,"SIZE",obj.get("size"),"IDS",obj.get("id"))
        print("DIM",json.dumps(obj.get("dimension",{}),ensure_ascii=False)[:5000])
        print("VALUES",list((obj.get("value") or {}).items())[-15:])
      except Exception as e:print("ERR",code,repr(e))

def risks():
    print("\n### ISTAT RISKS API")
    base="https://www.istat.it/wp-content/themes/EGPbs5-child/inc/mappa-rischi/"
    raw,_,_=get(base+"?lang=it")
    html=raw.decode("utf-8","ignore")
    # hidden token
    for m in re.finditer(r'name=["\']paramsSelected\[token\]["\'][^>]*',html,re.I):
        print("TOKEN_TAG",m.group(0)[:1000])
    # print config lines around token and date
    for pat in ["token","dateFrom","Controller.php"]:
        for m in list(re.finditer(pat,html,re.I))[:6]:
            print("HTML",html[max(0,m.start()-250):m.start()+500].replace("\n"," ")[:800])

def terna():
    print("\n### TERNA HIDDEN")
    raw,final,h=get("https://dati.terna.it/download-center")
    text=raw.decode("utf-8","ignore")
    for pat in [r"https://api\.terna\.it[^\"' <]+",r"[^\"']+\.xlsx[^\"']*",r"[^\"']+\.csv[^\"']*",r"/-/media/[^\"']+"]:
      vals=[]
      for m in re.finditer(pat,text,re.I):
        v=m.group(0)
        if v not in vals:vals.append(v)
      print("PAT",pat,"COUNT",len(vals))
      for v in vals[:30]:print(v[:1000])

def main():
    aci();eea();rifiuti();idrogeo()
    links("ISPRA_GHG","https://emissioni.sina.isprambiente.it/serie-storiche-emissioni-di-gas-serra-sintesi/")
    links("ISPRA_AIR_NO2","https://indicatoriambientali.isprambiente.it/it/qualita-dellaria/qualita-dellaria-ambiente-biossido-di-azoto-no2")
    links("ISPRA_AIR_PM25","https://indicatoriambientali.isprambiente.it/it/qualita-dellaria/qualita-dellaria-ambiente-particolato-pm25")
    copernicus();eurostat();risks();terna()

if __name__=="__main__":main()
