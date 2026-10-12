#!/usr/bin/env python3
"""PULSE CPI August-2026, independently verified expanded numerical evidence.

Extract REAL Prospetto 3 table rows (not prose invented by an LLM) from
ISTAT original PDF. Prospetto 1 index levels stay in the already-audited
research packet; this supplement provides energy, core, goods & services.
Never publish, never call a paid API.

The signed yearly rates and prior-month YEARLY rates come from distinct
columns of the official source table. Source version is pinned by SHA-256.
"""
from __future__ import annotations

import hashlib
import io
import json
import re
from decimal import Decimal
from pathlib import Path
from urllib.parse import urlsplit

from scripts.pulse_research_prices import SOURCE_URL

PINNED_SOURCE_SHA256 = "d3647dade0220cfe1525be8e69166d691b4b89c5c48303ff6624fd7d76bd7024"
PRICE_STORY_ID = "PRICES-01-" + PINNED_SOURCE_SHA256[:10]
PATTERN = re.compile(
    r"^(?P<label>.+?)\s+(?P<weight>\d{1,3}(?:\.\d{3})+)"
    r"(?P<numbers>(?:\s+[+-]?\d{1,3},\d){5})$",
)
FLOAT = re.compile(r"^[+-]?\d{1,3},\d$")
LABELS = {
    "Indice generale": ("NIC_GENERAL", "Indice generale NIC"),
    "Beni energetici, di cui:": ("ENERGY_TOTAL", "Beni energetici"),
    "Energetici regolamentati": ("ENERGY_REGULATED", "Energetici regolamentati"),
    "Energetici non regolamentati": ("ENERGY_UNREGULATED", "Energetici non regolamentati"),
    "Beni": ("GOODS", "Beni"),
    "Servizi": ("SERVICES", "Servizi"),
    "Indice generale al netto degli energetici e alimentari freschi (Componente di fondo)": (
        "CORE", "Inflazione di fondo (senza energia e alimentari freschi)"
    ),
    "Indice generale al netto degli energetici": ("EX_ENERGY", "Indice al netto dei soli energetici"),
    "Indice dei beni alimentari, per la cura della casa e della persona": (
        "BASKET", "Beni alimentari, cura della casa e della persona"
    ),
}
REQUIRED_BASELINE = {
    "NIC_GENERAL": (3.3, 2.9, 0.5),
    "ENERGY_TOTAL": (17.1, 11.6, 2.9),
    "ENERGY_REGULATED": (18.6, 14.8, 3.0),
    "ENERGY_UNREGULATED": (17.0, 11.4, 2.9),
    "GOODS": (4.1, 3.2, 0.7),
    "SERVICES": (2.4, 2.7, 0.2),
    "CORE": (1.5, 1.6, 0.2),
    "EX_ENERGY": (1.7, 1.8, 0.2),
    "BASKET": (0.9, 1.0, 0.1),
}


def norm(s: str) -> str:
    return re.sub(r"\s+", " ", s or "").strip()


def strict_decimal(s: str) -> float:
    if not FLOAT.fullmatch(s):
        raise ValueError("Unexpected percent token: " + s)
    return float(Decimal(s.replace(",", ".")))


def table_rows(page_text: str, source_sha256: str, *, page_no=4) -> list[dict]:
    if source_sha256 != PINNED_SOURCE_SHA256:
        raise ValueError("Original ISTAT PDF changed SHA-256: requires human revalidation")
    if page_no != 4:
        raise ValueError("Official Prospetto 3 must be on page 4")
    lines = [norm(s) for s in page_text.splitlines() if norm(s)]
    if not any("PROSPETTO 3. INDICE DEI PREZZI AL CONSUMO NIC PER TIPOLOGIA DI PRODOTTO" in s.upper()
               for s in lines):
        raise ValueError("Official Prospetto 3 header absent")
    start=next(i for i,s in enumerate(lines)
               if "PROSPETTO 3." in s.upper())
    stop=next((i for i in range(start+1,len(lines))
               if lines[i].startswith("*") and "variazioni" in lines[i].lower()),len(lines))
    pool=[]
    for lineno in range(start+1,stop):
        line=lines[lineno]
        if line.startswith("Indice generale al netto degli energetici e alimentari freschi"):
            # ISTAT PDF: the long "Componente di fondo" label AND the
            # numeric columns may occupy three independent extracted lines.
            # Reconstruct only if the joined row matches the EXACT official
            # label + weight + five numeric columns; never guess a value.
            for width in (2, 3, 4):
                if lineno+width > stop:
                    break
                candidate=" ".join(lines[lineno:lineno+width])
                m=PATTERN.fullmatch(candidate)
                if m and m.group("label") in LABELS:
                    line=candidate
                    break
        match=PATTERN.fullmatch(line)
        if not match:
            continue
        label=match.group("label").strip()
        if label not in LABELS:
            continue
        values=[strict_decimal(v) for v in match.group("numbers").split()]
        # Prospetto 3: variation month; previous-month comparator; annual;
        # previous-month annual; acquired inflation.
        if len(values)!=5:
            raise ValueError("Malformed five official table columns")
        if label in [p["raw_label"] for p in pool]:
            raise ValueError("Duplicate indicator in source table")
        pool.append({
            "raw_label":label,
            "location":f"page:{page_no}:text:line:{lineno+1}",
            "values":values,
            "weight":match.group("weight")
        })
    if set(x["raw_label"] for x in pool)!=set(LABELS):
        raise ValueError("Missing official rows: "+
                         str(set(LABELS)-{x["raw_label"] for x in pool})+
                         " / relevant extracted table lines: "+repr([
                             (index+1,lines[index][:185],
                              lines[index+1][:185] if index+1 < stop else "",
                              lines[index+2][:185] if index+2 < stop else "")
                             for index in range(start,stop)
                             if "Componente" in lines[index] or "alimentari freschi" in lines[index]
                         ][:5]))
    result=[]
    for i,(label,(code,title)) in enumerate(LABELS.items(),start=4):
        row=next(x for x in pool if x["raw_label"]==label)
        monthly,prev_monthly,yoy,prev_yoy,acquired=row["values"]
        if tuple((yoy,prev_yoy,monthly))!=REQUIRED_BASELINE[code]:
            raise ValueError(f"Changed official baseline for {code}: {row['values']}")
        result.append({
            "evidence_id":f"E-{PRICE_STORY_ID}-{i:02d}",
            "source_url":SOURCE_URL,
            "source_sha256":source_sha256,
            "source_locations":[row["location"]],
            "verified_structured_data":{
                "indicator":title,
                "indicator_code":code,
                "territory":"Italia",
                "reference_period":"2026-08",
                "previous_comparison_period":"2026-07",
                "unit":"percent",
                "reported_yoy_change_pct":yoy,
                "previous_month_yoy_change_pct":prev_yoy,
                "reported_monthly_change_pct":monthly,
                "previous_month_reported_monthly_change_pct":prev_monthly,
                "inflation_acquired_pct":acquired,
                "official_source_table":"Prospetto 3",
                "source_pdf_page":page_no,
                "comparison_definition":"annual_rate_in_august_and_annual_rate_in_july",
            },
            "verification":"strict_original_prospetto3_row_verified_against_pinned_pdf"
        })
    # The differences between services and goods are mathematically determined,
    # not independent observation or a guessed new official series.
    goods=next(z for z in result if z["verified_structured_data"]["indicator_code"]=="GOODS")
    services=next(z for z in result if z["verified_structured_data"]["indicator_code"]=="SERVICES")
    s,g=services["verified_structured_data"],goods["verified_structured_data"]
    current=round(s["reported_yoy_change_pct"]-g["reported_yoy_change_pct"],1)
    previous=round(s["previous_month_yoy_change_pct"]-g["previous_month_yoy_change_pct"],1)
    if (current,previous)!=(-1.7,-0.5):
        raise ValueError("Derived goods-services difference differs from official narrative")
    result.append({
        "evidence_id":f"E-{PRICE_STORY_ID}-13",
        "source_url":SOURCE_URL,"source_sha256":source_sha256,
        "source_locations":goods["source_locations"]+services["source_locations"],
        "verified_structured_data":{
            "indicator":"Differenziale inflazione servizi meno beni",
            "indicator_code":"SERVICES_MINUS_GOODS",
            "territory":"Italia","reference_period":"2026-08",
            "previous_comparison_period":"2026-07","unit":"percentage_points",
            "difference_current_pp":current,"difference_previous_pp":previous,
            "derivation":"SERVICES_yoy_minus_GOODS_yoy",
        },
        "verification":"deterministic_difference_of_two_verified_official_rates"
    })
    if len(result)!=10 or len({x["evidence_id"] for x in result})!=10:
        raise ValueError("Unstable expanded evidence inventory")
    return result


def from_original_pdf(raw: bytes) -> dict:
    if not isinstance(raw,bytes) or not raw.startswith(b"%PDF-"):
        raise ValueError("Not PDF bytes")
    digest=hashlib.sha256(raw).hexdigest()
    if digest!=PINNED_SOURCE_SHA256:
        raise ValueError("Original PDF checksum mismatch; no acceptance")
    from pdfplumber import open as pdf_open
    with pdf_open(io.BytesIO(raw)) as pdf:
        if len(pdf.pages)!=22:
            raise ValueError("Original PDF page count differs from accepted source")
        text=pdf.pages[3].extract_text() or ""
    facts=table_rows(text,digest)
    return {
        "schema_version":"pulse-cpi-extended-evidence-v1",
        "story_id":PRICE_STORY_ID,
        "source_url":SOURCE_URL,
        "source_sha256":digest,
        "source_document":"ISTAT, Prezzi al consumo agosto 2026, dati definitivi",
        "source_published_at":"2026-09-16",
        "source_pdf_pages":22,
        "source_table":"Prospetto 3, page 4",
        "numeric_fact_count":len(facts),
        "facts":facts,
        "publication_allowed":False,
        "requires_independent_article_review":True
    }


def add_to_research_packet(packet: dict, supplement: dict) -> dict:
    """Pure, immutable extension: keep 16 old stories and add 10 facts to prices."""
    if packet.get("schema_version")!="pulse-research-to-chatgpt-v1":
        raise ValueError("Wrong source packet")
    if supplement.get("schema_version")!="pulse-cpi-extended-evidence-v1":
        raise ValueError("Wrong supplement")
    if supplement.get("publication_allowed") is not False:
        raise ValueError("Supplement is not a publication")
    base=json.loads(json.dumps(packet))  # no changes to original object
    stories=[s for s in base["stories"] if s.get("story_id")==PRICE_STORY_ID]
    if len(stories)!=1 or stories[0]["source_sha256"]!=supplement.get("source_sha256"):
        raise ValueError("Wrong official document")
    original=stories[0]["facts"]
    if len(original)!=3 or set(x["verified_structured_data"]["price_index_code"] for x in original)!={"NIC","IPCA","FOI"}:
        raise ValueError("Baseline three distinct indices not verified")
    add=supplement.get("facts")
    if not isinstance(add,list) or len(add)!=10:
        raise ValueError("Expected ten independent supplement evidence records")
    combined=original+add
    if len({f["evidence_id"] for f in combined})!=13:
        raise ValueError("Duplicate evidence IDs")
    stories[0]["facts"]=combined
    base["source_packet_extension"]="cpi-prospetto3-verified-v1"
    base["source_packet_extension_hash"]=supplement["source_sha256"]
    base["publication_allowed"]=False
    base["human_review_required"]=True
    return base


def main():
    import argparse
    from scripts.pulse_evidence import fetch_bounded
    p=argparse.ArgumentParser()
    p.add_argument("--output",type=Path,required=True)
    p.add_argument("--input-packet",type=Path,required=True)
    p.add_argument("--merged-output",type=Path,required=True)
    args=p.parse_args()
    raw, content_type, end_url=fetch_bounded(SOURCE_URL,timeout=35)
    if urlsplit(end_url).hostname not in ("istat.it","www.istat.it"):
        raise ValueError("Unexpected source redirect")
    supplement=from_original_pdf(raw)
    original=json.loads(args.input_packet.read_text(encoding="utf-8"))
    merged=add_to_research_packet(original,supplement)
    for dest,data in ((args.output,supplement),(args.merged_output,merged)):
        dest.parent.mkdir(parents=True,exist_ok=True)
        dest.write_text(json.dumps(data,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
    print(json.dumps({"verified_official_pdf_sha256":supplement["source_sha256"],
                      "new_facts":len(supplement["facts"]),
                      "story_fact_count":len(next(s for s in merged["stories"]
                                                if s["story_id"]==PRICE_STORY_ID)["facts"]),
                      "published":False}))


if __name__=="__main__":
    main()
