#!/usr/bin/env python3
"""
Generate annual PULSE signals from the official ISTAT BES dei territori 2025
package. The output uses the same 19-column schema consumed by the Android app.

No causal interpretation is produced: signals describe changes, records,
inversions, anomalies, acceleration/rallentamento and territorial divergence.
"""
from __future__ import annotations

import hashlib
import io
import math
import re
import urllib.request
import zipfile
from pathlib import Path

import numpy as np
import pandas as pd

SOURCE_URL = "https://www.istat.it/wp-content/uploads/2025/06/Bes_dei_territori_edizione_2025.zip"
SOURCE_PAGE = "https://www.istat.it/statistiche-per-temi/focus/benessere-e-sostenibilita/la-misurazione-del-benessere-bes/il-bes-dei-territori/"
WORKBOOK = "Indicatori_per_provincia_sesso_ed.2025.xlsx"
OUT = Path("app/src/main/assets/pulse_events_bes.tsv")
META = Path("app/src/main/assets/pulse_bes_meta.json")
CACHE = Path(".pulse_cache/bes_territori_2025.zip")

COLUMNS = [
    "id","municipality_code","municipality","province","region","indicator",
    "patterns","scope","score","validation_status","period","summary","annual",
    "rolling12","benchmark_local","benchmark_rest","analysis","source_family","source_url",
]

REGIONS = {
    "01": "Piemonte",
    "02": "Valle d'Aosta/Vallée d'Aoste",
    "03": "Lombardia",
    "04": "Trentino-Alto Adige/Südtirol",
    "05": "Veneto",
    "06": "Friuli-Venezia Giulia",
    "07": "Liguria",
    "08": "Emilia-Romagna",
    "09": "Toscana",
    "10": "Umbria",
    "11": "Marche",
    "12": "Lazio",
    "13": "Abruzzo",
    "14": "Molise",
    "15": "Campania",
    "16": "Puglia",
    "17": "Basilicata",
    "18": "Calabria",
    "19": "Sicilia",
    "20": "Sardegna",
}

def clean(value) -> str:
    return re.sub(r"\s+", " ", str(value if value is not None else "")).strip().replace("\t"," ")

def number(value):
    if value is None or (isinstance(value, float) and math.isnan(value)):
        return np.nan
    raw = str(value).strip().replace(".", "").replace(",", ".") if isinstance(value, str) else value
    try:
        return float(raw)
    except (TypeError, ValueError):
        return np.nan

def download() -> bytes:
    if CACHE.exists():
        return CACHE.read_bytes()
    CACHE.parent.mkdir(parents=True, exist_ok=True)
    req = urllib.request.Request(SOURCE_URL, headers={"User-Agent":"ISTAT-PULSE/0.6"})
    with urllib.request.urlopen(req, timeout=120) as response:
        raw = response.read()
    CACHE.write_bytes(raw)
    return raw

def robust_scale(values: np.ndarray) -> float:
    values = np.asarray(values, dtype=float)
    values = values[np.isfinite(values)]
    if len(values) < 3:
        return 0.0
    med = np.median(values)
    mad = np.median(np.abs(values - med)) * 1.4826
    if mad > 1e-12:
        return float(mad)
    sd = float(np.std(values))
    return sd if sd > 1e-12 else 0.0

def fmt(value: float) -> str:
    if abs(value) >= 1000:
        return f"{value:,.0f}".replace(",", ".")
    if abs(value) >= 100:
        return f"{value:.1f}".replace(".", ",")
    return f"{value:.2f}".rstrip("0").rstrip(".").replace(".", ",")

def main():
    raw = download()
    with zipfile.ZipFile(io.BytesIO(raw)) as zf:
        book = zf.read(WORKBOOK)

    df = pd.read_excel(io.BytesIO(book), sheet_name="Indicatori_per_provincia_sesso", dtype=object)
    df.columns = [clean(c) for c in df.columns]
    years = sorted(int(c[1:]) for c in df.columns if re.fullmatch(r"V\d{4}", str(c)))
    if not years or max(years) < 2024:
        raise RuntimeError("BES workbook year columns not recognised")

    # One signal per indicator/territory: use total population where available.
    sex = df["SESSO"].astype(str).str.strip().str.casefold()
    totals = df[sex.isin({"totale","totali","total","t"})].copy()
    if totals.empty:
        raise RuntimeError("BES workbook has no total-sex rows")

    # Region rows end with province component 000. Used as territorial benchmark.
    def geo_parts(raw_geo):
        parts = clean(raw_geo).split("-")
        if len(parts) != 3:
            return ("","","")
        return tuple(parts)

    totals[["_macro","_region_code","_province_code"]] = totals["W_GEO"].apply(
        lambda x: pd.Series(geo_parts(x))
    )
    region_rows = totals[totals["_province_code"].eq("000")].copy()
    region_lookup = {
        (clean(row["CODICE"]), clean(row["_region_code"])): row
        for _, row in region_rows.iterrows()
    }

    candidates = []
    for _, row in totals.iterrows():
        indicator_code = clean(row.get("CODICE"))
        indicator = clean(row.get("INDICATORE"))
        territory = clean(row.get("TERRITORIO"))
        domain = clean(row.get("DOMINIO"))
        unit = clean(row.get("UNITA_MISURA"))
        geo = clean(row.get("W_GEO"))
        region_code = clean(row.get("_region_code"))
        province_code = clean(row.get("_province_code"))
        is_region = province_code == "000"
        region = territory if is_region else REGIONS.get(region_code, "")
        if not indicator or not territory or not region:
            continue

        vals = {year: number(row.get(f"V{year}")) for year in years}
        available = [year for year in years if np.isfinite(vals[year])]
        if len(available) < 7:
            continue
        latest_year = max(available)
        # Require six consecutive recent annual observations for stable display.
        display_years = list(range(latest_year - 5, latest_year + 1))
        if not all(year in vals and np.isfinite(vals[year]) for year in display_years):
            continue
        series = np.array([vals[y] for y in display_years], dtype=float)
        deltas = np.diff(series)
        latest_delta = float(deltas[-1])
        prior_delta = float(deltas[-2])
        scale = robust_scale(deltas[:-1])
        if scale <= 1e-12:
            scale = max(abs(float(np.median(series))) * 0.01, 1e-6)
        z_change = abs(latest_delta) / scale

        patterns = []
        analysis = []

        history_before = series[:-1]
        if series[-1] > np.max(history_before) and z_change >= 0.75:
            patterns.append("RECORD_MAX")
            analysis.append(f"Record: il valore {latest_year} supera i valori dei cinque anni precedenti.")
        elif series[-1] < np.min(history_before) and z_change >= 0.75:
            patterns.append("RECORD_MIN")
            analysis.append(f"Record: il valore {latest_year} è inferiore ai valori dei cinque anni precedenti.")

        if latest_delta * prior_delta < 0 and z_change >= 0.9 and abs(prior_delta) >= 0.25 * scale:
            patterns.append("INVERSIONE")
            analysis.append(
                f"Inversione: la variazione cambia segno tra {latest_year-2}→{latest_year-1} "
                f"e {latest_year-1}→{latest_year}."
            )
        elif latest_delta * prior_delta > 0 and abs(prior_delta) > 1e-12:
            ratio = abs(latest_delta) / abs(prior_delta)
            if ratio >= 1.7 and z_change >= 1.0:
                patterns.append("ACCELERAZIONE")
                analysis.append("Accelerazione: il cambiamento più recente è nettamente più ampio del precedente.")
            elif ratio <= 0.5 and abs(prior_delta) >= 0.75 * scale:
                patterns.append("RALLENTAMENTO")
                analysis.append("Rallentamento: il cambiamento più recente è nettamente più contenuto del precedente.")

        hist_scale = robust_scale(history_before)
        if hist_scale > 1e-12:
            z_level = abs(series[-1] - np.median(history_before)) / hist_scale
        else:
            z_level = 0.0
        if z_level >= 2.5:
            patterns.append("ANOMALIA")
            analysis.append(
                "Anomalia: l'ultimo valore si discosta in modo robusto dal livello recente oltre la soglia PULSE."
            )

        region_series = None
        divergence_strength = 0.0
        if not is_region:
            benchmark = region_lookup.get((indicator_code, region_code))
            if benchmark is not None:
                bvals = np.array([number(benchmark.get(f"V{y}")) for y in display_years], dtype=float)
                if np.all(np.isfinite(bvals)):
                    region_series = bvals
                    local_d = series[-1] - series[-2]
                    reg_d = bvals[-1] - bvals[-2]
                    common_scale = max(robust_scale(np.diff(series)), robust_scale(np.diff(bvals)), 1e-6)
                    divergence_strength = abs(local_d - reg_d) / common_scale
                    opposite = local_d * reg_d < 0 and abs(local_d-reg_d) >= common_scale
                    if divergence_strength >= 2.0 or opposite:
                        patterns.append("DIVERGENZA")
                        analysis.append(
                            f"Divergenza territoriale: la variazione di {territory} "
                            f"si discosta da quella della regione {region}."
                        )

        patterns = list(dict.fromkeys(patterns))
        if not patterns:
            continue

        score = 42.0
        score += min(18.0, z_change * 4.5)
        score += min(10.0, z_level * 2.0)
        score += 10.0 if any(p.startswith("RECORD") for p in patterns) else 0.0
        score += 9.0 if "INVERSIONE" in patterns else 0.0
        score += 8.0 if "ANOMALIA" in patterns else 0.0
        score += min(10.0, divergence_strength * 2.5) if "DIVERGENZA" in patterns else 0.0
        score += 5.0 if ("ACCELERAZIONE" in patterns or "RALLENTAMENTO" in patterns) else 0.0
        score += 4.0 if is_region else 0.0
        score = min(99.0, score)
        if score < 67.0:
            continue

        previous = series[-2]
        current = series[-1]
        delta = current - previous
        pct = (delta / abs(previous) * 100.0) if abs(previous) > 1e-12 else np.nan
        movement = "sale" if delta > 0 else "scende" if delta < 0 else "resta stabile"
        if np.isfinite(pct):
            summary = (
                f"{territory}: {indicator} {movement} da {fmt(previous)} a {fmt(current)} "
                f"nel {latest_year} ({pct:+.1f}%)."
            )
        else:
            summary = f"{territory}: {indicator} {movement} da {fmt(previous)} a {fmt(current)} nel {latest_year}."

        analysis.append(f"PULSE Score: {score:.1f}/100. Fonte: BES dei territori, ISTAT.")
        if unit:
            analysis.append(f"Unità di misura: {unit}.")
        note = clean(row.get("NOTA"))
        if note:
            analysis.append(f"Nota fonte: {note}")

        event_id = hashlib.sha256(
            f"BES|{indicator_code}|{geo}|{latest_year}".encode("utf-8")
        ).hexdigest()[:16]

        candidates.append({
            "id": event_id,
            "municipality_code": f"BES-{geo}",
            "municipality": territory,
            "province": "" if is_region else territory,
            "region": region,
            "indicator": f"{domain} · {indicator}" if domain else indicator,
            "patterns": "|".join(patterns),
            "scope": "GENERAL" if is_region else "TERRITORIALE",
            "score": round(score, 1),
            "validation_status": "SEGNALE PULSE — BES TERRITORI",
            "period": f"{latest_year}-12",
            "summary": summary,
            "annual": "|".join(f"{v:.6g}" for v in series),
            "rolling12": "",
            "benchmark_local": "|".join(f"{v:.6g}" for v in series) if region_series is not None else "",
            "benchmark_rest": "|".join(f"{v:.6g}" for v in region_series) if region_series is not None else "",
            "analysis": "¦".join(clean(x) for x in analysis),
            "source_family": "BES dei territori — ISTAT",
            "source_url": SOURCE_PAGE,
            "_domain": domain or "Altro",
        })

    if not candidates:
        raise RuntimeError("No BES PULSE candidates generated")

    out = pd.DataFrame(candidates)
    # Keep the feed broad but finite: strongest signals within every BES domain.
    out = (
        out.sort_values(["_domain","score"], ascending=[True,False])
           .groupby("_domain", group_keys=False)
           .head(25)
           .sort_values("score", ascending=False)
           .head(240)
           .drop(columns=["_domain"])
    )
    OUT.parent.mkdir(parents=True, exist_ok=True)
    out[COLUMNS].to_csv(OUT, sep="\t", index=False)

    import json
    meta = {
        "source_family": "BES dei territori — ISTAT",
        "source_url": SOURCE_PAGE,
        "download_url": SOURCE_URL,
        "source_sha256": hashlib.sha256(raw).hexdigest(),
        "latest_year": int(max(int(x.split("-")[0]) for x in out["period"])),
        "events": int(len(out)),
        "domains": sorted(set(x.split(" · ",1)[0] for x in out["indicator"] if " · " in x)),
    }
    META.write_text(json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"BES PULSE events: {len(out)}")
    print(out["indicator"].str.split(" · ").str[0].value_counts().to_string())
    print(f"Asset: {OUT}")

if __name__ == "__main__":
    main()
