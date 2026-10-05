#!/usr/bin/env python3
from __future__ import annotations
import csv, hashlib, io, json, re, urllib.request, zipfile
from datetime import datetime, timezone
from pathlib import Path

OUT=Path("data/bancaditalia_latest.json")
CATALOG=Path("data/sources_catalog.json")
UA="ISTAT-PULSE/BancaItalia-connector (+https://github.com/pierfido89/ISTAT-PULSE-DATA)"
A2A="https://a2a.bancaditalia.it/infostat/dataservices/export/IT/CSV/DATA/CUBE/BANKITALIA/DIFF"
CURRENT_YEAR=datetime.now(timezone.utc).year
CUBES={
 "banking_money":{"cube":"BSIB0400","label":"Banche e moneta / statistiche bancarie","topic":"MONETA_BANCHE"},
 "interest_rates":{"cube":"MIR0300","label":"Tassi di interesse bancari","topic":"TASSI_INTERESSE"},
 "gross_public_debt":{"cube":"TUEE0140","label":"Debito pubblico lordo","topic":"DEBITO_PUBBLICO"},
 "public_debt_by_sector":{"cube":"TCCE0200","label":"Debito delle amministrazioni pubbliche per settore","topic":"DEBITO_PUBBLICO"},
}
def get(url,timeout=180):
 req=urllib.request.Request(url,headers={"User-Agent":UA,"Accept":"application/zip,*/*"})
 with urllib.request.urlopen(req,timeout=timeout) as r:return r.read(),r.geturl(),r.headers.get("Content-Type","")
def clean(x):return re.sub(r"\s+"," ",str(x or "")).strip()
def parse_period_value(v):
 s=clean(v)
 m=re.fullmatch(r"(20\d{2})[-/](0?[1-9]|1[0-2])",s)
 if m and 1990<=int(m.group(1))<=CURRENT_YEAR:return (int(m.group(1))*100+int(m.group(2)),f"{int(m.group(1)):04d}-{int(m.group(2)):02d}")
 m=re.fullmatch(r"(20\d{2})[- ]?Q([1-4])",s,re.I)
 if m and 1990<=int(m.group(1))<=CURRENT_YEAR:return (int(m.group(1))*100+int(m.group(2))*3,f"{int(m.group(1)):04d}-Q{m.group(2)}")
 m=re.fullmatch(r"(20\d{2})",s)
 if m and 1990<=int(m.group(1))<=CURRENT_YEAR:return (int(m.group(1))*100+12,m.group(1))
 return None
def period_from_csv(text):
 sample=text[:600000]
 dialect=csv.excel
 try:dialect=csv.Sniffer().sniff(sample[:12000],delimiters=";,\t|")
 except:pass
 rows=list(csv.reader(io.StringIO(sample),dialect))
 if not rows:return ""
 header=[clean(x).upper() for x in rows[0]]
 idxs=[i for i,h in enumerate(header) if any(k in h for k in ("TIME_PERIOD","PERIODO","DATA_RIF","DATE","TIME"))]
 vals=[]
 for row in rows[1:]:
  candidates=[row[i] for i in idxs if i<len(row)] if idxs else []
  for v in candidates:
   p=parse_period_value(v)
   if p:vals.append(p)
 if vals:return max(vals,key=lambda x:x[0])[1]
 # Safe fallback: scan tokens, but never allow future years.
 for token in re.findall(r"20\d{2}(?:[-/](?:0?[1-9]|1[0-2])|[- ]?Q[1-4])?",sample,re.I):
  p=parse_period_value(token)
  if p:vals.append(p)
 return max(vals,key=lambda x:x[0])[1] if vals else ""
def inspect_zip(raw):
 if not raw.startswith(b"PK"):raise RuntimeError("A2A response is not ZIP")
 with zipfile.ZipFile(io.BytesIO(raw)) as zf:
  names=[n for n in zf.namelist() if not n.endswith("/")]
  if not names:raise RuntimeError("empty BDS archive")
  sample=b""; total=0; periods=[]
  for n in names[:20]:
   b=zf.read(n); total+=len(b)
   if len(sample)<600000:sample+=b[:300000]
   txt=b.decode("utf-8","ignore") or b.decode("latin-1","ignore")
   p=period_from_csv(txt)
   if p:periods.append(p)
  latest=max(periods,key=lambda p:(int(p[:4]), int(re.search(r"(\d{2})$",p).group(1)) if re.search(r"(\d{2})$",p) else 12)) if periods else ""
  return {"file_count":len(names),"files":names[:20],"uncompressed_bytes_sampled":total,
          "latest_period_detected":latest,"sample_sha256":hashlib.sha256(sample).hexdigest()}
def acquire(key,cfg):
 raw,final,ctype=get(f"{A2A}/{cfg['cube']}"); d=inspect_zip(raw)
 if not d["latest_period_detected"]:raise RuntimeError("period not detected safely")
 return {"key":key,"cube":cfg["cube"],"label":cfg["label"],"topic":cfg["topic"],"url":final,
 "content_type":ctype,"download_bytes":len(raw),"download_sha256":hashlib.sha256(raw).hexdigest(),"status":"ok",**d}
def main():
 datasets={};failures={}
 for k,c in CUBES.items():
  try:datasets[k]=acquire(k,c)
  except Exception as e:failures[k]=clean(e)
 if len(datasets)<3:raise RuntimeError(f"Only {len(datasets)} valid BDS cubes: {failures}")
 periods=[x["latest_period_detected"] for x in datasets.values()]
 latest=max(periods,key=lambda p:(int(p[:4]), int(re.search(r"(\d{2})$",p).group(1)) if re.search(r"(\d{2})$",p) else 12))
 snap={"source":"Banca d'Italia","source_family":"Banca d'Italia - Base Dati Statistica","a2a_base":A2A,
 "dataset_count":len(datasets),"datasets":datasets,"failures":failures,"latest_period":latest,
 "checked_at":datetime.now(timezone.utc).isoformat(),"status":"feed"}
 OUT.write_text(json.dumps(snap,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
 root=json.loads(CATALOG.read_text(encoding="utf-8")) if CATALOG.exists() else {"sources":[]};name="Banca d'Italia - Base Dati Statistica"
 src=next((x for x in root["sources"] if x.get("name")==name),None)
 if src is None:src={};root["sources"].append(src)
 src.update({"name":name,"category":"ECONOMIA_FINANZA_IT","topics":["MONETA","BANCHE","TASSI","CREDITO","DEBITO_PUBBLICO"],
 "official":True,"url":"https://www.bancaditalia.it/statistiche/basi-dati/bds/index.html","access_cost":"free",
 "integration_status":"feed","feed_status":"Attiva · BDS A2A validata con periodi reali","frequency":"Secondo calendario statistico",
 "latest_period":latest,"checked_at":snap["checked_at"]})
 CATALOG.write_text(json.dumps(root,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
 print(json.dumps({"dataset_count":len(datasets),"latest_period":latest,"failures":failures},ensure_ascii=False))
if __name__=="__main__":main()
