#!/usr/bin/env python3
from __future__ import annotations
import hashlib,json,re,urllib.parse,urllib.request
from datetime import datetime,timezone
from pathlib import Path

OUT=Path("data/anac_latest.json");CAT=Path("data/sources_catalog.json")
UA="Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 Chrome/154 Safari/537.36"
API="https://dati.anticorruzione.it/opendata/api/3/action"
CATALOG="https://dati.anticorruzione.it/opendata/dataset?groups=governo&q=cig-&tags=cig"

def get_json(url):
 req=urllib.request.Request(url,headers={"User-Agent":UA,"Accept":"application/json"})
 with urllib.request.urlopen(req,timeout=90) as r:return json.loads(r.read().decode("utf-8","ignore"))

def probe(url):
 req=urllib.request.Request(url,headers={"User-Agent":UA,"Accept":"*/*","Range":"bytes=0-131071"})
 with urllib.request.urlopen(req,timeout=90) as r:
  b=r.read(131072);return b,r.geturl(),r.headers.get("Content-Type","")

def api_try():
 out=[];seen=set()
 for q in ("CIG","contratti pubblici","aggiudicazioni"):
  try:d=get_json(API+"/package_search?"+urllib.parse.urlencode({"q":q,"rows":50}))
  except Exception:continue
  if not d.get("success"):continue
  for pkg in d["result"].get("results",[]):
   for r in pkg.get("resources",[]):
    url=r.get("url") or "";fmt=str(r.get("format") or "").upper()
    if not url or url in seen:continue
    if fmt not in ("CSV","JSON") and not re.search(r"\.(csv|json)(?:\?|$)",url,re.I):continue
    try:
     b,u,ct=probe(url)
     if len(b)>50 and "text/html" not in ct.lower():
      seen.add(url);out.append({"dataset":pkg.get("title",""),"resource":r.get("name",""),"format":fmt,"url":u,
       "content_type":ct,"bytes_sampled":len(b),"sha256":hashlib.sha256(b).hexdigest(),
       "last_modified":r.get("last_modified") or pkg.get("metadata_modified") or ""})
    except Exception:pass
    if len(out)>=8:return out
 return out

def browser_try():
 from playwright.sync_api import sync_playwright
 out=[];seen=set()
 with sync_playwright() as p:
  browser=p.chromium.launch(headless=True)
  ctx=browser.new_context(user_agent=UA,locale="it-IT")
  page=ctx.new_page();page.goto(CATALOG,wait_until="domcontentloaded",timeout=120000);page.wait_for_timeout(4000)
  hrefs=page.eval_on_selector_all("a[href]","els => els.map(e => e.href)")
  resource_pages=[h for h in hrefs if "/resource/" in h or "/dataset/" in h][:30]
  candidates=[]
  for rp in resource_pages:
   try:
    page.goto(rp,wait_until="domcontentloaded",timeout=60000);page.wait_for_timeout(1200)
    hs=page.eval_on_selector_all("a[href]","els => els.map(e => e.href)")
    for h in hs:
     if re.search(r"\.(csv|json)(?:\?|$)",h,re.I) or "download" in h.lower():
      candidates.append(h)
   except Exception:pass
  for h in candidates:
   if h in seen:continue
   try:
    resp=ctx.request.get(h,headers={"Range":"bytes=0-131071"},timeout=90000)
    ct=resp.headers.get("content-type","");b=resp.body()[:131072]
    if resp.ok and len(b)>50 and "text/html" not in ct.lower():
     seen.add(h);out.append({"dataset":"BDNCP","resource":"browser_discovered",
      "format":"CSV" if "csv" in ct.lower() or ".csv" in h.lower() else "JSON",
      "url":h,"content_type":ct,"bytes_sampled":len(b),"sha256":hashlib.sha256(b).hexdigest(),"last_modified":""})
   except Exception:pass
   if len(out)>=8:break
  browser.close()
 return out

def main():
 resources=api_try()
 if not resources:
  try:resources=browser_try()
  except Exception:resources=[]
 if not resources:raise RuntimeError("ANAC: WAF/catalogo non ha consentito validazione CSV/JSON neppure via browser headless")
 snap={"source":"ANAC","source_family":"ANAC - BDNCP Open Data","validated_resource_count":len(resources),
       "resources":resources,"checked_at":datetime.now(timezone.utc).isoformat(),"status":"feed"}
 OUT.write_text(json.dumps(snap,ensure_ascii=False,indent=2)+"\n")
 root=json.loads(CAT.read_text()) if CAT.exists() else {"sources":[]};name="ANAC - BDNCP Open Data"
 src=next((x for x in root["sources"] if x.get("name")==name),None)
 if src is None:src={};root["sources"].append(src)
 src.update({"name":name,"category":"CONTRATTI_PUBBLICI_IT","topics":["APPALTI","CONTRATTI_PUBBLICI","AGGIUDICAZIONI"],
   "official":True,"url":"https://dati.anticorruzione.it/opendata/","access_cost":"free","integration_status":"feed",
   "feed_status":"Attiva · BDNCP CSV/JSON validate","frequency":"Mensile","checked_at":snap["checked_at"]})
 CAT.write_text(json.dumps(root,ensure_ascii=False,indent=2)+"\n")
 print(json.dumps({"validated":len(resources)},ensure_ascii=False))
if __name__=="__main__":main()
