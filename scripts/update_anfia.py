#!/usr/bin/env python3
"""Acquire the latest public ANFIA passenger-car market release.

This connector intentionally uses only ANFIA's public statistical pages.
It does not scrape newspapers and does not use ANFIA's subscription portals.

Outputs:
- data/anfia_latest.json: normalized latest-publication snapshot
- data/sources_catalog.json: ANFIA source freshness/integration metadata
"""
from __future__ import annotations

import hashlib
import io
import json
import re
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

from bs4 import BeautifulSoup
from pypdf import PdfReader

LANDING = "https://www.anfia.it/it/attivita/studi-e-statistiche/dati-statistici/immatricolazioni/italia"
OUT = Path("data/anfia_latest.json")
CATALOG = Path("data/sources_catalog.json")
UA = "ISTAT-PULSE/ANFIA-connector (+https://github.com/pierfido89/ISTAT-PULSE-DATA)"

MONTHS = {
    "gennaio": 1, "febbraio": 2, "marzo": 3, "aprile": 4, "maggio": 5, "giugno": 6,
    "luglio": 7, "agosto": 8, "settembre": 9, "ottobre": 10, "novembre": 11, "dicembre": 12,
}


def get(url: str, timeout: int = 120) -> tuple[bytes, str, str]:
    req = urllib.request.Request(
        url,
        headers={
            "User-Agent": UA,
            "Accept": "*/*",
            "Accept-Language": "it-IT,it;q=0.9,en;q=0.7",
        },
    )
    with urllib.request.urlopen(req, timeout=timeout) as response:
        return response.read(), response.geturl(), response.headers.get("Content-Type", "")


def clean(text: str) -> str:
    return re.sub(r"\s+", " ", text or "").strip()


def iso_date(text: str) -> str:
    m = re.search(r"(\d{1,2})\s+([A-Za-zÀ-ÿ]+)\s+(20\d{2})", text, re.I)
    if not m:
        return ""
    month = MONTHS.get(m.group(2).lower())
    if not month:
        return ""
    return f"{int(m.group(3)):04d}-{month:02d}-{int(m.group(1)):02d}"


def parse_number_it(value: str) -> int | None:
    value = value.strip().replace(".", "").replace("\u00a0", "")
    if not re.fullmatch(r"[+-]?\d+", value):
        return None
    return int(value)


def publication_period(pdf_text: str, publication_date: str) -> str:
    month_pattern = "|".join(MONTHS)
    m = re.search(rf"\b({month_pattern})\b\s*(?:-|–)?\s*(?:[A-Za-z]+)?\s*(20\d{{2}})", pdf_text, re.I)
    if m:
        return f"{int(m.group(2)):04d}-{MONTHS[m.group(1).lower()]:02d}"
    # The ANFIA monthly release published in early month M normally refers to M-1.
    if publication_date:
        year, month, _ = map(int, publication_date.split("-"))
        month -= 1
        if month == 0:
            year -= 1
            month = 12
        return f"{year:04d}-{month:02d}"
    return ""


def extract_market(pdf_bytes: bytes, publication_date: str) -> dict:
    reader = PdfReader(io.BytesIO(pdf_bytes))
    text = "\n".join((page.extract_text() or "") for page in reader.pages[:8])
    flat = clean(text)

    # Current-month table: TOTALE MERCATO 139.356 100,0% 126.781 100,0% +9,9% ...
    total = re.search(
        r"TOTALE\s+MERCATO\s+([\d.]+)\s+100,0%\s+([\d.]+)\s+100,0%\s+([+\-]?\d+,\d+)%",
        flat,
        re.I,
    )

    latest = previous = None
    yoy = None
    if total:
        latest = parse_number_it(total.group(1))
        previous = parse_number_it(total.group(2))
        yoy = float(total.group(3).replace(",", "."))

    return {
        "period": publication_period(flat, publication_date),
        "passenger_cars_registered": latest,
        "passenger_cars_registered_previous_year": previous,
        "yoy_percent": yoy,
        "pdf_pages": len(reader.pages),
        "text_sha256": hashlib.sha256(text.encode("utf-8")).hexdigest(),
    }


def discover_publications(html: str) -> list[dict]:
    soup = BeautifulSoup(html, "html.parser")
    found: list[dict] = []
    seen: set[str] = set()

    for heading in soup.find_all(["h3", "h4", "h5"]):
        title = clean(heading.get_text(" ", strip=True))
        if not title:
            continue
        container = heading.parent
        if container is None:
            continue
        text = clean(container.get_text(" ", strip=True))
        date_match = re.search(r"Pubblicato\s+il\s+(\d{1,2}\s+[A-Za-zÀ-ÿ]+\s+20\d{2})", text, re.I)
        link = container.find("a", href=True)
        href = urllib.parse.urljoin(LANDING, link["href"]) if link else ""
        if not href or href in seen or "/file" not in href:
            continue
        seen.add(href)
        found.append({
            "title": title,
            "publication_date": iso_date(date_match.group(1)) if date_match else "",
            "download_url": href,
        })

    # Fallback for ANFIA markup where heading and download link do not share an immediate parent.
    if not found:
        for link in soup.find_all("a", href=True):
            href = urllib.parse.urljoin(LANDING, link["href"])
            if "/file" not in href or href in seen:
                continue
            seen.add(href)
            parent_text = clean(link.parent.get_text(" ", strip=True) if link.parent else link.get_text(" ", strip=True))
            found.append({"title": parent_text[:180], "publication_date": iso_date(parent_text), "download_url": href})

    return found


def update_catalog(snapshot: dict) -> None:
    root = json.loads(CATALOG.read_text(encoding="utf-8")) if CATALOG.exists() else {"sources": []}
    sources = root.setdefault("sources", [])
    name = "ANFIA - Immatricolazioni e mercato auto"
    entry = next((x for x in sources if x.get("name") == name), None)
    if entry is None:
        entry = {}
        sources.append(entry)

    entry.update({
        "name": name,
        "category": "MOBILITA_IT",
        "topics": ["MOBILITA", "AUTO", "IMMATRICOLAZIONI"],
        "official": True,
        "url": LANDING,
        "access_cost": "free",
        "access_note": "Dati statistici pubblici ANFIA; esclusi i portali statistici in abbonamento.",
        "integration_status": "feed",
        "feed_status": "Attiva · acquisizione automatica dell'ultima pubblicazione ufficiale ANFIA",
        "notes": "Connettore PULSE dedicato alla pagina pubblica ANFIA. Rileva nuove pubblicazioni, acquisisce il documento ufficiale e normalizza i principali dati del mercato autovetture.",
        "level": "Nazionale; ulteriori tavole provinciali disponibili dalla fonte",
        "frequency": "Mensile",
        "latest_period": snapshot.get("period", ""),
        "publication_date": snapshot.get("publication_date", ""),
        "checked_at": snapshot.get("checked_at", ""),
        "provides": [
            {
                "area": "Mobilità e trasporti",
                "series": "Immatricolazioni autovetture",
                "description": "Mercato mensile autovetture Italia da pubblicazione statistica ANFIA.",
                "latest_period": snapshot.get("period", ""),
                "status": "latest_public",
            }
        ],
    })
    CATALOG.write_text(json.dumps(root, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def main() -> None:
    landing_bytes, landing_final, landing_type = get(LANDING)
    html = landing_bytes.decode("utf-8", "ignore")
    publications = discover_publications(html)
    if not publications:
        raise RuntimeError("ANFIA: nessuna pubblicazione scaricabile individuata")

    # Prefer the monthly passenger-car press-release tables; then most recent dated artifact.
    candidates = [p for p in publications if "tabelle comunicato stampa" in p["title"].lower()]
    if not candidates:
        candidates = publications
    candidates.sort(key=lambda p: p.get("publication_date", ""), reverse=True)
    chosen = candidates[0]

    raw, final_url, content_type = get(chosen["download_url"])
    if not raw:
        raise RuntimeError("ANFIA: download vuoto")

    snapshot = {
        "source": "ANFIA",
        "source_family": "ANFIA - Immatricolazioni e mercato auto",
        "landing_url": landing_final,
        "landing_content_type": landing_type,
        "publication_title": chosen["title"],
        "publication_date": chosen["publication_date"],
        "download_url": final_url,
        "download_content_type": content_type,
        "download_bytes": len(raw),
        "download_sha256": hashlib.sha256(raw).hexdigest(),
        "checked_at": datetime.now(timezone.utc).isoformat(),
    }

    is_pdf = raw.startswith(b"%PDF") or "pdf" in content_type.lower()
    if is_pdf:
        snapshot.update(extract_market(raw, chosen["publication_date"]))
        snapshot["format"] = "pdf"
    elif raw.startswith(b"PK"):
        snapshot["format"] = "xlsx_or_zip"
        snapshot["period"] = chosen["publication_date"][:7] if chosen["publication_date"] else ""
    else:
        snapshot["format"] = content_type or "binary"
        snapshot["period"] = chosen["publication_date"][:7] if chosen["publication_date"] else ""

    if not snapshot.get("period"):
        raise RuntimeError("ANFIA: impossibile determinare il periodo statistico")

    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(snapshot, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    update_catalog(snapshot)
    print(json.dumps(snapshot, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
