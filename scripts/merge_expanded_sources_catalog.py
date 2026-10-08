#!/usr/bin/env python3
"""Merge permanent expanded connectors into the generated technical source catalog."""
from __future__ import annotations

import json
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
GENERATED=ROOT/"app/src/main/assets/sources_catalog.json"
EXPANDED=ROOT/"data/expanded_source_catalog.json"

def key(name:str)->str:
    return " ".join(str(name or "").strip().lower().split())

def main():
    generated=json.loads(GENERATED.read_text(encoding="utf-8"))
    expanded=json.loads(EXPANDED.read_text(encoding="utf-8"))
    base=generated.get("sources",[])
    extra=expanded.get("sources",[])
    merged={key(row.get("name","")):row for row in base if row.get("name")}
    for row in extra:
        name=row.get("name","").strip()
        if not name:
            continue
        merged[key(name)]=row
    generated["sources"]=list(merged.values())
    generated["expanded_connector_count"]=len(extra)
    GENERATED.write_text(json.dumps(generated,ensure_ascii=False,indent=2),encoding="utf-8")
    print(f"Technical source catalog: {len(base)} generated + {len(extra)} expanded => {len(generated['sources'])} unique")

if __name__=="__main__":
    main()
