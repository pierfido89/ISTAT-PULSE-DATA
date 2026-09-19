#!/usr/bin/env python3
"""Copia di lettura degli ultimi valori regionali BesT ufficiali, NON notizie PULSE.

Il periodo e il livello territoriale provengono dal file sorgente. Non
convertire la data di pubblicazione (2025) in data del fenomeno (2024).
Non assegnare a province nomi di regioni: qui si importano solo righe regionali
con codice territoriale xx-rr-000 verificato sul registro ufficiale.
"""
from __future__ import annotations

import io
import re
import zipfile
from pathlib import Path
import pandas as pd
import numpy as np
from generate_bes_events import download, clean, number, WORKBOOK, REGIONS, SOURCE_PAGE

OUT = Path("app/src/main/assets/pulse_observations_bes.tsv")
COLUMNS = ["area","indicator","territory","period","value","unit","source","url","note","status"]

def norm(text):
    return re.sub(r"[\s\W]+", "", str(text).casefold(), flags=re.UNICODE)

def categorise(domain, indicator):
    d = domain.casefold()
    k = indicator.casefold()
    if "salute" in d:
        return "Sanità" if any(x in k for x in ("ospedal", "medic", "servizi sanitari", "rinuncia", "spesa sanitaria", "infermier")) else "Salute"
    if "istruzione" in d: return "Istruzione"
    if "economico" in d:
        if any(x in k for x in ("povert", "deprivazione", "disagio economic")): return "Povertà"
        if any(x in k for x in ("disuguaglianza", "gini", "s80", "dispersione del reddito")): return "Disuguaglianza"
        if any(x in k for x in ("reddito", "retribuzione")): return "Redditi"
        return "Potere d'acquisto e consumi"
    if "ambiente" in d: return "Ambiente"
    if "servizi" in d: return "Servizi e qualità locale"
    if "lavoro" in d: return "Lavoro e mercato del lavoro"
    if "sicurezza" in d: return "Territorio e mobilità"
    if "paesaggio" in d or "cultura" in d or "sociali" in d: return "Società e cultura"
    if "innovazione" in d: return "Imprese e industria"
    return domain

def main():
    raw = download()
    with zipfile.ZipFile(io.BytesIO(raw)) as archive:
        workbook = archive.read(WORKBOOK)
    frame = pd.read_excel(io.BytesIO(workbook), sheet_name="Indicatori_per_provincia_sesso", dtype=object)
    frame.columns = [clean(c) for c in frame.columns]
    required = {"W_GEO", "TERRITORIO", "SESSO", "DOMINIO", "INDICATORE", "UNITA_MISURA"}
    missing = required - set(frame.columns)
    if missing: raise RuntimeError(f"BesT schema changed: {sorted(missing)}")
    years = sorted(int(c[1:]) for c in frame.columns if re.fullmatch(r"V\d{4}", c))
    if not years: raise RuntimeError("BesT has no year columns")

    rows = []
    region_codes = set()
    seen = set()
    for _, item in frame.iterrows():
        if clean(item["SESSO"]).casefold() not in {"totale", "totali", "total", "t"}:
            continue
        code = clean(item["W_GEO"])
        matched = re.fullmatch(r"\d{2}-(\d{2})-000", code)
        if matched is None or matched.group(1) == "00":
            # 20-00-000 / Centro etc. are macro-geographic totals, NOT regions.
            continue
        # W_GEO's second field is a source grouping code, NOT the Italian
        # administrative region code (e.g. 01-03-000 denotes Liguria here).
        # Resolve only verified region labels from the source. Never guess.
        territory = clean(item["TERRITORIO"])
        region_lookup = {norm(name): name for name in REGIONS.values()}
        canonical = region_lookup.get(norm(territory))
        if canonical is None:
            raise RuntimeError(f"Unknown regional total in official BesT: W_GEO={code}, {territory!r}")
        indicator = clean(item["INDICATORE"])
        if not indicator: continue
        recent = [(year, number(item.get(f"V{year}"))) for year in years]
        recent = [(year, value) for year, value in recent if np.isfinite(value)]
        if not recent: continue
        year, value = recent[-1]
        if year > 2026: raise RuntimeError(f"Future BES value? {year} {indicator}")
        key = (canonical, indicator)
        if key in seen: continue
        seen.add(key)
        region_codes.add(canonical)
        detail = clean(item.get("NOTA", ""))
        rows.append({
            "area": categorise(clean(item["DOMINIO"]), indicator),
            "indicator": indicator,
            "territory": territory,
            "period": str(year),
            "value": format(float(value), ".10g"),
            "unit": clean(item["UNITA_MISURA"]),
            "source": "Bes dei territori — ISTAT",
            "url": SOURCE_PAGE,
            "note": (detail + " · " if detail else "") + "Dato regionale annuale; non costituisce una notizia del 2026.",
            "status": "ultimo dato osservato, non nuovo segnale PULSE"
        })
    if len(region_codes) != 20:
        raise RuntimeError(f"BesT import covers {len(region_codes)} regions, expected 20")
    if len(rows) < 300:
        raise RuntimeError(f"BesT import unexpectedly small: {len(rows)} observations")
    OUT.parent.mkdir(parents=True, exist_ok=True)
    pd.DataFrame(rows, columns=COLUMNS).to_csv(OUT, sep="\t", index=False)
    print(f"BesT observed regional values: {len(rows)} across {len(region_codes)} verified regions; output {OUT}")
    print("Year distribution:", pd.Series([x["period"] for x in rows]).value_counts().to_dict())

if __name__ == "__main__":
    main()
