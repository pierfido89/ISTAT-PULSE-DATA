#!/usr/bin/env python3
"""Discover the *official* complete Noi Italia database download without guessing URLs."""
from urllib.parse import urljoin,urlparse
import urllib.request
from bs4 import BeautifulSoup
HOME="https://noi-italia.istat.it/home.php"
req=urllib.request.Request(HOME,headers={"User-Agent":"ISTAT-PULSE/0.9"})
with urllib.request.urlopen(req,timeout=45) as r:
    html=r.read()
    print("HOME",r.status,len(html),"bytes",r.url)
soup=BeautifulSoup(html,"html.parser")
for item in soup.select("a[href]"):
    label=item.get_text(" ",strip=True)
    href=urljoin(HOME,item.get("href",""))
    if any(word in (label+" "+href).casefold() for word in ["download","scarica","banca dati","base dati",".csv",".zip",".xlsx",".xls","db","dati"]):
        print("LINK",label[:120],href[:200])
for tag in soup.select("[onclick]"):
    onclick=tag.get("onclick","")
    if any(x in onclick.casefold() for x in ["download","zip","excel","csv","db"]):
        print("ONCLICK",tag.get_text(" ",strip=True)[:80],onclick[:180])
