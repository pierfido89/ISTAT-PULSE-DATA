#!/usr/bin/env python3
"""Acquire and fingerprint verified expanded PULSE feeds.

This stage intentionally stops before event generation. It creates durable,
auditable raw-source metadata and last-known-good snapshots for feeds that
have already passed structured-source verification.
"""
from __future__ import annotations

import hashlib
import json
import zipfile
from datetime import datetime, timezone
from io import BytesIO
from pathlib import Path
from urllib.parse import urljoin

import requests
from bs4 import BeautifulSoup

ROOT = Path(__file__).resolve().parents[1]
OUT_DIR = ROOT / "data" / "expanded_feeds"
STATUS = ROOT / "data" / "expanded_feed_acquisition.json"

UA = "ISTAT-PULSE-expanded-feed/1.0 (+https://github.com/pierfido89/ISTAT-PULSE)"
TIMEOUT = 45
session = requests.Session()
session.headers.update({"User-Agent": UA, "Accept": "*/*"})

SOURCES = [
    {
        "institution": "Banca d'Italia",
        "id": "banca_italia_bam",
        "url": "https://a2a.bancaditalia.it/infostat/dataservices/export/IT/CSV/DATA/PUBLICATION/BANKITALIA/DIFF/BAM",
        "kind": "zip_csv",
        "frequency": "monthly_or_source_update",
    },
    {
        "institution": "MIMIT",
        "id": "mimit_carburanti_prezzi",
        "url": "https://www.mimit.gov.it/images/exportCSV/prezzo_alle_8.csv",
        "kind": "csv",
        "frequency": "daily",
    },
    {
        "institution": "MIMIT",
        "id": "mimit_carburanti_impianti",
        "url": "https://www.mimit.gov.it/images/exportCSV/anagrafica_impianti_attivi.csv",
        "kind": "csv",
        "frequency": "daily",
    },
    {
        "institution": "Ministero dell'Università e della Ricerca",
        "id": "mur_personale_genere_qualifica",
        "url": "https://dati-ustat.mur.gov.it/dataset/1775dfd1-5408-4970-95c2-97373b7a0016/resource/85c1ab95-c8db-484b-8898-56478c521721/download/docricxgenerequalifica_serie.csv",
        "kind": "csv",
        "frequency": "annual",
    },
    {
        "institution": "Ministero dell'Università e della Ricerca",
        "id": "mur_personale_eta_qualifica",
        "url": "https://dati-ustat.mur.gov.it/dataset/1775dfd1-5408-4970-95c2-97373b7a0016/resource/a9cc23fc-785a-4969-af49-5e9378be582b/download/docricxclasseetaqualifica_serie.csv",
        "kind": "csv",
        "frequency": "annual",
    },
    {
        "institution": "ENAC",
        "id": "enac_traffico_tableau",
        "url": "https://www.enac.gov.it/views/EAE-DatiTraffico-VersioneGrafica/DATITRAFFICOHOMEPAGE.csv?:showVizHome=no",
        "kind": "csv",
        "frequency": "monthly",
    },
    {
        "institution": "AGCOM",
        "id": "agcom_osservatorio_comunicazioni",
        "url": "https://www.agcom.it/sites/default/files/media/allegato/2026/OPEN%20DATA%20Oss.%202-2026_start_0.xlsx",
        "kind": "xlsx",
        "frequency": "quarterly",
    },
    {
        "institution": "IVASS",
        "id": "ivass_relazione_annuale_tavole",
        "url": "https://www.ivass.it/pubblicazioni-e-statistiche/pubblicazioni/relazione-annuale/2026/Relazione_annuale_2025_Appendice.xlsx?force_download=1",
        "kind": "xlsx",
        "frequency": "annual",
    },
]

INAIL_PAGES = [
    {
        "id": "inail_malattie_mensili",
        "url": "https://dati.inail.it/portale/it/dataset/malattie-professionali/dati-con-cadenza-mensile/italia.html",
        "label": "Malattie professionali · mensile · Italia",
    },
]



def sha256(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def fetch(url: str, *, params: dict | None = None) -> tuple[bytes, requests.Response]:
    response = session.get(url, params=params, timeout=TIMEOUT, allow_redirects=True)
    response.raise_for_status()
    return response.content, response


def describe(source: dict, raw: bytes, response: requests.Response) -> dict:
    record = {
        "institution": source["institution"],
        "id": source["id"],
        "url": response.url,
        "kind": source["kind"],
        "frequency": source["frequency"],
        "http_status": response.status_code,
        "content_type": response.headers.get("content-type", "").split(";")[0],
        "bytes": len(raw),
        "sha256": sha256(raw),
        "checked_at": datetime.now(timezone.utc).isoformat(),
        "status": "ok",
    }
    if source["kind"] == "zip_csv":
        with zipfile.ZipFile(BytesIO(raw)) as archive:
            files = [
                x for x in archive.namelist()
                if x and not x.endswith("/")
            ]
            record["files"] = files[:500]
            record["file_count"] = len(files)
            record["extensions"] = sorted({
                Path(x).suffix.lower() or "(none)"
                for x in files
            })
            if not files:
                raise RuntimeError(f"{source['id']}: ZIP archive is empty")
    elif source["kind"] == "csv":
        head = raw[:5000].decode("utf-8", errors="replace").lstrip()
        if head.startswith("<"):
            raise RuntimeError(f"{source['id']}: server returned XML/HTML instead of CSV")
        lines = [line for line in head.splitlines() if line.strip()]
        if len(lines) < 2:
            raise RuntimeError(f"{source['id']}: CSV payload looks empty")
        record["header"] = lines[0][:1000]
        record["sample_lines"] = [line[:1500] for line in lines[:4]]
    elif source["kind"] == "xlsx":
        if not raw.startswith(b"PK"):
            raise RuntimeError(f"{source['id']}: response is not an XLSX/ZIP payload")
        with zipfile.ZipFile(BytesIO(raw)) as archive:
            names = archive.namelist()
            if "xl/workbook.xml" not in names:
                raise RuntimeError(f"{source['id']}: invalid XLSX workbook")
            worksheets = [x for x in names if x.startswith("xl/worksheets/") and x.endswith(".xml")]
            record["worksheet_count"] = len(worksheets)
            if not worksheets:
                raise RuntimeError(f"{source['id']}: workbook has no worksheets")
    elif source["kind"] == "xml_or_geojson":
        text = raw[:2000].decode("utf-8", errors="replace").lstrip()
        if not (text.startswith("{") or text.startswith("[") or text.startswith("<")):
            raise RuntimeError(f"{source['id']}: unexpected structured payload")
        record["format_detected"] = (
            "json" if text.startswith(("{","[")) else "xml"
        )
    return record


def acquire_file_source(source: dict) -> dict:
    raw, response = fetch(source["url"])
    record = describe(source, raw, response)
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    suffix = {
        "zip_csv": ".zip",
        "csv": ".csv",
        "xlsx": ".xlsx",
        "xml_or_geojson": ".dat",
    }[source["kind"]]
    target = OUT_DIR / f"{source['id']}{suffix}"
    target.write_bytes(raw)
    record["snapshot"] = str(target.relative_to(ROOT))
    return record


def discover_latest_inail_csv(page: dict) -> dict:
    raw, response = fetch(page["url"])
    soup = BeautifulSoup(raw, "html.parser")
    candidates = []
    for tag in soup.find_all("a", href=True):
        href = tag.get("href", "").strip()
        text = " ".join(tag.stripped_strings).strip().lower()
        absolute = urljoin(response.url, href)
        low = absolute.lower()
        if "csv" in text or ".csv" in low or (
            "opendata_files" in low and "csv" in low
        ):
            candidates.append(absolute)
    if not candidates:
        raise RuntimeError(f"{page['id']}: no official CSV link found")

    # Preserve page order: INAIL lists the current downloadable CSV resource first.
    data_url = candidates[0]
    data, data_response = fetch(data_url)
    if len(data) < 1000:
        raise RuntimeError(f"{page['id']}: CSV payload unexpectedly small")

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    suffix = ".zip" if zipfile.is_zipfile(BytesIO(data)) else ".csv"
    target = OUT_DIR / f"{page['id']}{suffix}"
    target.write_bytes(data)

    sample_text = data[:12000].decode("utf-8", errors="replace")
    sample_lines = [line for line in sample_text.splitlines() if line.strip()][:4]

    record = {
        "institution": "INAIL",
        "id": page["id"],
        "label": page["label"],
        "catalog_url": page["url"],
        "url": data_response.url,
        "kind": "zip_csv" if suffix == ".zip" else "csv",
        "frequency": "monthly",
        "http_status": data_response.status_code,
        "content_type": data_response.headers.get("content-type", "").split(";")[0],
        "bytes": len(data),
        "sha256": sha256(data),
        "snapshot": str(target.relative_to(ROOT)),
        "checked_at": datetime.now(timezone.utc).isoformat(),
        "status": "ok",
        "sample_lines": [line[:1500] for line in sample_lines],
    }
    if suffix == ".zip":
        with zipfile.ZipFile(BytesIO(data)) as archive:
            files = [x for x in archive.namelist() if x and not x.endswith("/")]
            record["files"] = files[:200]
            record["file_count"] = len(files)
            if not files:
                raise RuntimeError(f"{page['id']}: empty ZIP")
    return record


def acquire_inail() -> list[dict]:
    return [discover_latest_inail_csv(page) for page in INAIL_PAGES]


def main() -> None:
    results = []
    failures = []
    for source in SOURCES:
        try:
            result = acquire_file_source(source)
            results.append(result)
            print(f"OK {source['institution']} / {source['id']}: {result['bytes']:,} bytes")
        except Exception as exc:
            failures.append({
                "institution": source["institution"],
                "id": source["id"],
                "error": f"{type(exc).__name__}: {exc}",
            })
            print(f"FAIL {source['institution']} / {source['id']}: {exc}")

    try:
        inail_results = acquire_inail()
        results.extend(inail_results)
        for result in inail_results:
            print(f"OK INAIL / {result['id']}: {result['bytes']:,} bytes")
    except Exception as exc:
        failures.append({
            "institution": "INAIL",
            "id": "inail_monthly_open_data",
            "error": f"{type(exc).__name__}: {exc}",
        })
        print(f"FAIL INAIL: {exc}")

    payload = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "successful_connectors": len(results),
        "failed_connectors": len(failures),
        "results": results,
        "failures": failures,
    }
    STATUS.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    if not results:
        raise RuntimeError("No expanded feed connector succeeded")


if __name__ == "__main__":
    main()
