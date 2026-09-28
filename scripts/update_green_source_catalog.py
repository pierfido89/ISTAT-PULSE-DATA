#!/usr/bin/env python3
from __future__ import annotations
import json
from pathlib import Path

ASSETS=Path("app/src/main/assets")
CATALOG=ASSETS/"sources_catalog.json"
TEMPLATE=Path("data/green_sources_catalog_template.json")
STATUS=Path("data/green_source_status.json")

def canonical(value:str)->str:
    return str(value or "").strip().replace(" — "," - ")

def main():
    if not CATALOG.exists():
        raise RuntimeError(f"Base source catalogue missing: {CATALOG}")
    base=json.loads(CATALOG.read_text(encoding="utf-8"))
    template=json.loads(TEMPLATE.read_text(encoding="utf-8"))
    status=json.loads(STATUS.read_text(encoding="utf-8"))
    statuses={canonical(x["name"]):x for x in status.get("sources",[])}

    combined={canonical(x.get("name")):x for x in base.get("sources",[])}
    for item in template.get("sources",[]):
        key=canonical(item.get("name"))
        current=combined.get(key,{})
        merged=dict(item)
        # Preserve dynamically generated IstatData-style series if a same-name
        # source already has richer provides metadata.
        if current.get("provides"):
            merged["provides"]=current["provides"]
        st=statuses.get(key)
        if st:
            mode=st.get("integration_mode","direct")
            state=st.get("status","partial")
            observations=int(st.get("observations",0))
            latest=st.get("latest_period","")
            if state=="live":
                merged["integration_status"]="feed"
                merged["feed_status"]=(
                    f"Integrata in GREEN · {observations} osservazioni ufficiali"
                    + (f" · ultimo periodo {latest}" if latest else "")
                )
            elif state=="technical_live":
                merged["integration_status"]="partial"
                merged["feed_status"]="Integrazione tecnica attiva · portale ufficiale verificato"
            elif state=="partial":
                merged["integration_status"]="partial"
                merged["feed_status"]=(
                    f"Integrazione parziale GREEN · {observations} osservazioni verificate"
                )
            else:
                merged["integration_status"]="planned"
                merged["feed_status"]="Integrazione non disponibile nell'ultimo aggiornamento"
            detail=st.get("detail","").strip()
            mode_note={
                "direct":"Connessione diretta alla fonte ufficiale.",
                "direct_static":"File ufficiale pubblico pubblicato dalla fonte.",
                "official_via_istat_sdg":"Serie della fonte originale acquisita tramite la distribuzione ufficiale ISTAT SDGs.",
                "technical_live":"Portale ufficiale verificato; usato come fonte tecnica/metodologica.",
            }.get(mode,f"Modalità di integrazione: {mode}.")
            merged["notes"]=" ".join(x for x in [mode_note,detail,merged.get("notes","")] if x)
        combined[key]=merged

    # Stable order: keep existing catalogue first, then GREEN additions.
    existing_keys=[canonical(x.get("name")) for x in base.get("sources",[])]
    ordered=[]
    seen=set()
    for key in existing_keys + [canonical(x.get("name")) for x in template.get("sources",[])]:
        if key in seen: continue
        seen.add(key); ordered.append(combined[key])
    base["version"]=max(int(base.get("version",1)),4)
    base["title"]="Fonti ISTAT PULSE"
    base["sources"]=ordered
    CATALOG.parent.mkdir(parents=True,exist_ok=True)
    CATALOG.write_text(json.dumps(base,ensure_ascii=False,indent=2),encoding="utf-8")
    print("Source catalogue updated:",len(ordered),"sources")

if __name__=="__main__":
    main()
