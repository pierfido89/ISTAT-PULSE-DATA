#!/usr/bin/env python3
"""
Generate the PULSE territory registry from ISTAT's permanent XLSX permalink.

No third-party spreadsheet library is used: XLSX is read as its underlying
Open XML ZIP package. The output is a compact TSV bundled in the Android APK.
"""
from __future__ import annotations

import io
import os
import re
import sys
import urllib.request
import zipfile
import xml.etree.ElementTree as ET

SOURCE_URL = "https://www.istat.it/storage/codici-unita-amministrative/Elenco-comuni-italiani.xlsx"
OUTPUT = "app/src/main/assets/territories.tsv"

NS_MAIN = {"a": "http://schemas.openxmlformats.org/spreadsheetml/2006/main"}
NS_REL = {"r": "http://schemas.openxmlformats.org/package/2006/relationships"}
NS_DOC_REL = {"r": "http://schemas.openxmlformats.org/officeDocument/2006/relationships"}

def clean(value: str) -> str:
    return re.sub(r"\s+", " ", (value or "").replace("\t", " ").replace("\n", " ")).strip()

def norm(value: str) -> str:
    value = clean(value).lower()
    value = (
        value.replace("à", "a").replace("è", "e").replace("é", "e")
        .replace("ì", "i").replace("ò", "o").replace("ù", "u")
    )
    return value

def col_index(ref: str) -> int:
    letters = re.match(r"([A-Z]+)", ref)
    if not letters:
        return 0
    n = 0
    for ch in letters.group(1):
        n = n * 26 + (ord(ch) - 64)
    return n - 1

def shared_strings(zf: zipfile.ZipFile) -> list[str]:
    try:
        root = ET.fromstring(zf.read("xl/sharedStrings.xml"))
    except KeyError:
        return []
    values = []
    for si in root.findall("a:si", NS_MAIN):
        values.append("".join(t.text or "" for t in si.findall(".//a:t", NS_MAIN)))
    return values

def first_sheet_path(zf: zipfile.ZipFile) -> str:
    workbook = ET.fromstring(zf.read("xl/workbook.xml"))
    first = workbook.find("a:sheets/a:sheet", NS_MAIN)
    if first is None:
        raise RuntimeError("No worksheet found in ISTAT XLSX")
    rel_id = first.attrib.get("{http://schemas.openxmlformats.org/officeDocument/2006/relationships}id")
    rels = ET.fromstring(zf.read("xl/_rels/workbook.xml.rels"))
    for rel in rels:
        if rel.attrib.get("Id") == rel_id:
            target = rel.attrib["Target"].lstrip("/")
            if not target.startswith("xl/"):
                target = "xl/" + target
            return target
    raise RuntimeError("Worksheet relationship not found")

def read_rows(zf: zipfile.ZipFile) -> list[list[str]]:
    strings = shared_strings(zf)
    root = ET.fromstring(zf.read(first_sheet_path(zf)))
    out = []
    for row in root.findall(".//a:sheetData/a:row", NS_MAIN):
        values = {}
        max_col = -1
        for c in row.findall("a:c", NS_MAIN):
            idx = col_index(c.attrib.get("r", "A1"))
            max_col = max(max_col, idx)
            typ = c.attrib.get("t", "")
            if typ == "inlineStr":
                value = "".join(t.text or "" for t in c.findall(".//a:t", NS_MAIN))
            else:
                v = c.find("a:v", NS_MAIN)
                raw = "" if v is None else (v.text or "")
                if typ == "s" and raw:
                    try:
                        value = strings[int(raw)]
                    except (ValueError, IndexError):
                        value = raw
                else:
                    value = raw
            values[idx] = clean(value)
        if max_col >= 0:
            out.append([values.get(i, "") for i in range(max_col + 1)])
    return out

def find_header(rows: list[list[str]]) -> int:
    for i, row in enumerate(rows[:30]):
        n = [norm(x) for x in row]
        has_region = any("denominazione regione" in x for x in n)
        has_municipality = any(("denominazione in italiano" in x) or ("denominazione" in x and "comune" in x) for x in n)
        has_super = any("territoriale sovracomunale" in x for x in n)
        if has_region and has_municipality and has_super:
            return i
    raise RuntimeError("Unable to detect ISTAT header row")

def find_col(headers: list[str], predicates) -> int:
    normalized = [norm(h) for h in headers]
    for pred in predicates:
        for i, h in enumerate(normalized):
            if pred(h):
                return i
    raise RuntimeError("Required column not found. Headers: " + " | ".join(headers))

METROPOLITAN_AREAS = {
    "torino", "milano", "venezia", "genova", "bologna", "firenze",
    "roma", "napoli", "bari", "reggio di calabria",
    "palermo", "catania", "messina", "cagliari", "sassari"
}

def classify_area_type(raw: str, area: str) -> str:
    n = norm(raw)
    if "metropolitana" in n or norm(area) in METROPOLITAN_AREAS:
        return "Città metropolitana"
    return "Provincia"

def main() -> int:
    req = urllib.request.Request(
        SOURCE_URL,
        headers={"User-Agent": "ISTAT-PULSE/0.3 (+https://github.com/pierfido89/ISTAT-PULSE)"}
    )
    print("Downloading official ISTAT territory registry…")
    with urllib.request.urlopen(req, timeout=60) as response:
        content = response.read()

    with zipfile.ZipFile(io.BytesIO(content)) as zf:
        rows = read_rows(zf)

    hi = find_header(rows)
    headers = rows[hi]

    c_region = find_col(headers, [
        lambda h: "denominazione regione" in h,
    ])
    c_area = find_col(headers, [
        lambda h: "denominazione" in h and "territoriale sovracomunale" in h,
    ])
    c_area_type = find_col(headers, [
        lambda h: "tipologia" in h and "territoriale sovracomunale" in h,
        lambda h: "tipo" in h and "territoriale sovracomunale" in h,
    ])
    c_municipality = find_col(headers, [
        lambda h: h == "denominazione in italiano",
        lambda h: "denominazione" in h and "italiano" in h and "regione" not in h,
        lambda h: "denominazione" in h and "comune" in h and "regione" not in h,
    ])
    c_code = find_col(headers, [
        lambda h: "codice comune formato alfanumerico" in h,
        lambda h: h.startswith("codice comune"),
    ])

    records = []
    for row in rows[hi + 1:]:
        def get(i: int) -> str:
            return clean(row[i]) if i < len(row) else ""

        municipality = get(c_municipality)
        region = get(c_region)
        area = get(c_area)
        code = get(c_code)
        raw_type = get(c_area_type)
        if not municipality or not region or not area:
            continue
        records.append((region, classify_area_type(raw_type, area), area, municipality, code))

    # Deduplicate while preserving deterministic alphabetical order.
    records = sorted(set(records), key=lambda x: (x[0].casefold(), x[1], x[2].casefold(), x[3].casefold()))
    if len(records) < 7800:
        raise RuntimeError(f"Registry unexpectedly small: {len(records)} municipalities")

    os.makedirs(os.path.dirname(OUTPUT), exist_ok=True)
    with open(OUTPUT, "w", encoding="utf-8", newline="") as f:
        f.write("region\tarea_type\tarea\tmunicipality\tmunicipality_code\n")
        for record in records:
            f.write("\t".join(clean(x) for x in record) + "\n")

    print(f"Generated {OUTPUT} with {len(records)} municipalities")
    # Guardrail explicitly requested during development.
    text = open(OUTPUT, encoding="utf-8").read()
    if "\tRoma\t" not in text and "\tRoma\n" not in text:
        # Roma may be municipality followed by code, so also inspect split records.
        if not any(r[3].casefold() == "roma" for r in records):
            raise RuntimeError("Roma municipality missing from generated registry")
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
