#!/usr/bin/env python3
"""
Build the current PULSE feed and the complete detail payload from official
DEMO ISTAT monthly demographic balance files (2019-2024).

Output:
- app/src/main/assets/pulse_events.tsv
- app/src/main/assets/pulse_manifest.json

The APK does not query ISTAT on launch. GitHub Actions downloads, validates,
analyses and packages the data before the Android build.
"""
from __future__ import annotations

import hashlib
import io
import json
import time
import unicodedata
import urllib.error
import urllib.parse
import urllib.request
import zipfile
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import date, datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd
from scipy.stats import rankdata

SOURCE_YEARS = list(range(2019, date.today().year + 1))
YEARS = []
COMPLETE_YEARS = []
LATEST_PERIOD = None
BASE_URL = "https://demo.istat.it/data/d7b/D7B{year}.csv.zip"
DEMO_RPC = "https://demo.istat.it/app/RPCCerca.php"
DEMO_APP = "https://demo.istat.it/app/?a={year}&i=D7B&l=it"
ASSET_DIR = Path("app/src/main/assets")
OUT_TSV = ASSET_DIR / "pulse_events.tsv"
OUT_MANIFEST = ASSET_DIR / "pulse_manifest.json"
TERRITORY_TSV = ASSET_DIR / "territories.tsv"
CACHE_DIR = Path(".pulse_cache")
EPS = 1e-9

COLS = [
    "Anno", "Mese", "Sesso", "Nati vivi", "Morti",
    "Immigrati da altro comune", "Emigrati per altro comune",
    "Immigrati dall'estero", "Emigrati per l'estero",
    "Unità in più/meno dovute a variazioni territoriali",
    "Popolazione inizio periodo", "Popolazione fine periodo",
    "Codice comune", "Comune", "Codice provincia", "Provincia",
    "Codice regione", "Regione",
]

INDICATOR_COLUMN = {
    "Nati vivi": "Nati vivi",
    "Morti": "Morti",
    "Immigrati da altro comune": "Immigrati da altro comune",
    "Emigrati per altro comune": "Emigrati per altro comune",
    "Immigrati dall'estero": "Immigrati dall'estero",
    "Emigrati per l'estero": "Emigrati per l'estero",
}

ANNUAL_KEY = {
    "Nati vivi": "births",
    "Morti": "deaths",
    "Immigrati da altro comune": "imm_internal",
    "Emigrati per altro comune": "emi_internal",
    "Immigrati dall'estero": "imm_foreign",
    "Emigrati per l'estero": "emi_foreign",
}


def download(url: str, path: Path) -> bytes:
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists():
        return path.read_bytes()
    request = urllib.request.Request(
        url,
        headers={"User-Agent": "ISTAT-PULSE/0.4 (+https://github.com/pierfido89/ISTAT-PULSE)"},
    )
    with urllib.request.urlopen(request, timeout=120) as response:
        raw = response.read()
    path.write_bytes(raw)
    return raw



REGION_CODES = {
    "Piemonte": "01",
    "Valle d'Aosta/Vallée d'Aoste": "02",
    "Valle d'Aosta": "02",
    "Lombardia": "03",
    "Trentino-Alto Adige/Südtirol": "04",
    "Trentino-Alto Adige": "04",
    "Veneto": "05",
    "Friuli-Venezia Giulia": "06",
    "Liguria": "07",
    "Emilia-Romagna": "08",
    "Toscana": "09",
    "Umbria": "10",
    "Marche": "11",
    "Lazio": "12",
    "Abruzzo": "13",
    "Molise": "14",
    "Campania": "15",
    "Puglia": "16",
    "Basilicata": "17",
    "Calabria": "18",
    "Sicilia": "19",
    "Sardegna": "20",
}


def _post_demo(payload: list[tuple[str, str]], timeout: int = 120) -> dict:
    body = urllib.parse.urlencode(payload).encode()
    request = urllib.request.Request(
        DEMO_RPC,
        data=body,
        method="POST",
        headers={
            "User-Agent": "ISTAT-PULSE/0.5 (+https://github.com/pierfido89/ISTAT-PULSE)",
            "Content-Type": "application/x-www-form-urlencoded",
            "Referer": DEMO_APP.format(year=dict(payload).get("hid-a", date.today().year)),
        },
    )
    last_error = None
    for attempt in range(3):
        try:
            with urllib.request.urlopen(request, timeout=timeout) as response:
                return json.loads(response.read().decode("utf-8"))
        except (urllib.error.URLError, TimeoutError, json.JSONDecodeError) as exc:
            last_error = exc
            time.sleep(1.5 * (attempt + 1))
    raise RuntimeError(f"DEMO RPC failed after retries: {last_error!r}")


def _latest_api_month(year: int) -> int | None:
    payload = [
        ("a", str(year)),
        ("ripartizione", "IT"),
        ("regione", ""),
        ("provincia", ""),
        ("comune", ""),
        ("hid-i", "D7B"),
        ("hid-a", str(year)),
        ("hid-l", "it"),
        ("hid-cat", "D7B"),
        ("hid-dati", "dati-form-0"),
        ("hid-tavola", "tavola-form-0"),
    ]
    result = _post_demo(payload)
    rows = result.get("datatable", {}).get("data", [])
    months = [int(row.get("mese", 0) or 0) for row in rows]
    months = [month for month in months if 1 <= month <= 12]
    return max(months) if months else None


def _territory_lookup():
    if not TERRITORY_TSV.exists():
        raise RuntimeError(
            f"{TERRITORY_TSV} missing. Run scripts/generate_territories.py first."
        )
    territory = pd.read_csv(TERRITORY_TSV, sep="\t", dtype=str).fillna("")
    territory["municipality_code"] = (
        territory["municipality_code"].astype(str).str.replace(r"\.0$", "", regex=True).str.zfill(6)
    )
    territory["province_code"] = territory["municipality_code"].str[:3]
    by_code = territory.set_index("municipality_code")
    province_codes = sorted(
        code for code in territory["province_code"].unique().tolist()
        if len(code) == 3 and code.isdigit()
    )
    return territory, by_code, province_codes


def _name_key(value: str) -> str:
    value = unicodedata.normalize("NFKD", str(value or ""))
    value = "".join(ch for ch in value if not unicodedata.combining(ch))
    return "".join(ch for ch in value.casefold() if ch.isalnum())


def _historical_lookup_2025(legacy_2024: pd.DataFrame, current_territory: pd.DataFrame) -> pd.DataFrame:
    """Map 2025's pre-reform municipality codes to current canonical codes by name/region."""
    current = current_territory.copy()
    current["_key"] = current.apply(
        lambda r: _name_key(r["municipality"]) + "|" + _name_key(r["region"]), axis=1
    )
    current_by_name = {
        key: row for key, row in current.set_index("_key").iterrows()
    }

    legacy = legacy_2024[
        ["Codice comune", "Comune", "Provincia", "Regione"]
    ].drop_duplicates("Codice comune").copy()
    records = []
    mapped = 0
    for _, row in legacy.iterrows():
        old_code = str(row["Codice comune"]).zfill(6)
        key = _name_key(row["Comune"]) + "|" + _name_key(row["Regione"])
        match = current_by_name.get(key)
        if match is not None:
            mapped += 1
            records.append({
                "municipality_code": old_code,
                "canonical_code": str(match["municipality_code"]).zfill(6),
                "municipality": str(match["municipality"]),
                "area": str(match["area"]),
                "region": str(match["region"]),
            })
        else:
            records.append({
                "municipality_code": old_code,
                "canonical_code": old_code,
                "municipality": str(row["Comune"]),
                "area": str(row["Provincia"]),
                "region": str(row["Regione"]),
            })
    print(f"2025 historical municipality crosswalk: {mapped}/{len(records)} names mapped to current codes.")
    return pd.DataFrame(records).set_index("municipality_code")


def _fetch_api_slice(
    year: int,
    month: int,
    province_code: str,
    by_code: pd.DataFrame,
) -> list[dict]:
    cache = CACHE_DIR / "demo_rpc" / str(year) / f"{month:02d}_{province_code}.json"
    if cache.exists():
        result = json.loads(cache.read_text(encoding="utf-8"))
    else:
        payload = [
            ("territorio", "procom"),
            ("province", province_code),
            ("mese", str(month)),
            ("hid-i", "D7B"),
            ("hid-a", str(year)),
            ("hid-l", "it"),
            ("hid-cat", "D7B"),
            ("hid-dati", "dati-form-1"),
            ("hid-tavola", "tavola-form-1"),
        ]
        result = _post_demo(payload)
        cache.parent.mkdir(parents=True, exist_ok=True)
        cache.write_text(json.dumps(result, ensure_ascii=False), encoding="utf-8")

    rows = result.get("datatable", {}).get("data", [])
    out = []
    for row in rows:
        try:
            sex = int(row.get("sesso", 0) or 0)
        except (TypeError, ValueError):
            sex = 0
        if sex != 9:
            continue

        raw_code = str(row.get("codistat", "")).strip().zfill(6)
        if raw_code not in by_code.index:
            continue

        t = by_code.loc[raw_code]
        if isinstance(t, pd.DataFrame):
            t = t.iloc[0]
        region = str(t["region"]).strip()
        canonical_code = str(t.get("canonical_code", raw_code)).strip().zfill(6)
        region_code = REGION_CODES.get(region)
        if region_code is None:
            raise RuntimeError(f"Unknown region mapping for {region!r}")

        out.append({
            "Anno": year,
            "Mese": month,
            "Sesso": "Totale",
            "Nati vivi": float(row.get("nati_vivi", 0) or 0),
            "Morti": float(row.get("morti", 0) or 0),
            "Immigrati da altro comune": float(row.get("imm_altrocomune", 0) or 0),
            "Emigrati per altro comune": float(row.get("emi_altrocomune", 0) or 0),
            "Immigrati dall'estero": float(row.get("imm_estero", 0) or 0),
            "Emigrati per l'estero": float(row.get("emi_estero", 0) or 0),
            "Unità in più/meno dovute a variazioni territoriali": float(row.get("var_terr", 0) or 0),
            "Popolazione inizio periodo": float(row.get("pop_iniziale", 0) or 0),
            "Popolazione fine periodo": float(row.get("pop_finale", 0) or 0),
            "Codice comune": canonical_code,
            "Comune": str(row.get("denominazione", "") or t["municipality"]).strip(),
            "Codice provincia": canonical_code[:3],
            "Provincia": str(t["area"]).strip(),
            "Codice regione": region_code,
            "Regione": region,
            "date": pd.Timestamp(year=year, month=month, day=1),
        })
    return out


def _load_demo_api_year(
    year: int,
    latest_month: int,
    by_code: pd.DataFrame,
    province_codes: list[str],
) -> pd.DataFrame:
    tasks = [
        (month, province_code)
        for month in range(1, latest_month + 1)
        for province_code in province_codes
    ]
    records: list[dict] = []
    print(
        f"Downloading DEMO ISTAT {year} via official query API "
        f"({latest_month} months × {len(province_codes)} provinces)…"
    )
    with ThreadPoolExecutor(max_workers=8) as pool:
        futures = {
            pool.submit(
                _fetch_api_slice, year, month, province_code, by_code
            ): (month, province_code)
            for month, province_code in tasks
        }
        for future in as_completed(futures):
            month, province_code = futures[future]
            try:
                records.extend(future.result())
            except Exception as exc:
                raise RuntimeError(
                    f"DEMO API failed for {year}-{month:02d}, "
                    f"province {province_code}: {exc}"
                ) from exc

    frame = pd.DataFrame(records)
    if frame.empty:
        raise RuntimeError(f"No municipality data returned by DEMO API for {year}")
    frame = frame.drop_duplicates(["Anno", "Mese", "Codice comune"]).copy()
    print(
        f"DEMO API {year}: {len(frame):,} municipality-month rows "
        f"through month {latest_month}."
    )
    return frame


def _load_legacy_zip(year: int) -> tuple[pd.DataFrame, dict]:
    url = BASE_URL.format(year=year)
    path = CACHE_DIR / f"D7B{year}.csv.zip"
    print(f"Downloading DEMO ISTAT {year} legacy ZIP…")
    raw = download(url, path)
    with zipfile.ZipFile(io.BytesIO(raw)) as zf:
        csv_name = zf.namelist()[0]
        data = pd.read_csv(
            zf.open(csv_name),
            sep=";",
            encoding="utf-8",
            usecols=COLS,
            dtype={
                "Codice comune": str,
                "Codice provincia": str,
                "Codice regione": str,
            },
        )
    data = data[
        data["Sesso"].eq("Totale")
        & data["Mese"].between(1, 12)
        & data["Codice comune"].notna()
    ].copy()
    data["Codice comune"] = data["Codice comune"].astype(str).str.zfill(6)
    data["Codice provincia"] = data["Codice provincia"].astype(str).str.zfill(3)
    data["Codice regione"] = data["Codice regione"].astype(str).str.zfill(2)
    data["date"] = pd.to_datetime(
        dict(year=data["Anno"], month=data["Mese"], day=1)
    )
    info = {
        "year": year,
        "url": url,
        "method": "legacy_zip",
        "sha256": hashlib.sha256(raw).hexdigest(),
        "bytes": len(raw),
        "months": 12,
    }
    return data, info


def load_sources():
    parts = []
    source_info = []

    for year in range(2019, 2025):
        data, info = _load_legacy_zip(year)
        parts.append(data)
        source_info.append(info)

    current_territory, by_code, current_province_codes = _territory_lookup()
    by_code_2025 = _historical_lookup_2025(parts[-1], current_territory)
    # 2025 predates the 2026 Sardinian supra-municipal reorganisation.
    # Query it with the province codes actually present in the official 2024
    # DEMO archive; using the current registry silently drops Sardinia.
    province_codes_2024 = sorted(
        parts[-1]["Codice provincia"].dropna().astype(str).str.zfill(3).unique().tolist()
    )
    for year in range(2025, date.today().year + 1):
        latest_month = _latest_api_month(year)
        if latest_month is None:
            if year == date.today().year:
                print(f"DEMO ISTAT {year}: no published month yet, skip.")
                continue
            raise RuntimeError(f"DEMO ISTAT {year}: no data returned by official API")

        fetch_province_codes = province_codes_2024 if year == 2025 else current_province_codes
        fetch_lookup = by_code_2025 if year == 2025 else by_code
        data = _load_demo_api_year(
            year, latest_month, fetch_lookup, fetch_province_codes
        )
        parts.append(data)
        source_info.append({
            "year": year,
            "url": DEMO_APP.format(year=year),
            "endpoint": DEMO_RPC,
            "method": "official_query_api",
            "months": latest_month,
            "provisional": True,
            "municipality_month_rows": int(len(data)),
        })

    monthly = pd.concat(parts, ignore_index=True)
    monthly = monthly.sort_values(
        ["Codice comune", "Anno", "Mese"]
    ).drop_duplicates(["Codice comune", "Anno", "Mese"], keep="last")
    if monthly.empty:
        raise RuntimeError("Nessuna fonte DEMO ISTAT disponibile.")
    return monthly, source_info


def theil_sen_rows(arr):
    arr = np.asarray(arr, float)
    n = arr.shape[1]
    slopes = []
    for i in range(n - 1):
        for j in range(i + 1, n):
            slopes.append((arr[:, j] - arr[:, i]) / (j - i))
    return np.nanmedian(np.vstack(slopes), axis=0)


def spearman_time_rows(arr):
    n = arr.shape[1]
    time = np.arange(n, dtype=float)
    centered_time = time - time.mean()
    time_den = np.sqrt(np.sum(centered_time ** 2))
    out = np.empty(arr.shape[0])
    for idx, row in enumerate(arr):
        ranks = rankdata(row, method="average")
        centered = ranks - ranks.mean()
        den = np.sqrt(np.sum(centered ** 2)) * time_den
        out[idx] = np.sum(centered * centered_time) / den if den > 0 else 0.0
    return out


def mad_rows(arr, normal=True):
    arr = np.asarray(arr, float)
    median = np.nanmedian(arr, axis=1, keepdims=True)
    mad = np.nanmedian(np.abs(arr - median), axis=1)
    return mad * 1.4826 if normal else mad


def scope_birth_death(count, population):
    if count >= 150 or population >= 25000:
        return "GENERAL"
    if count >= 75 or population >= 10000:
        return "TERRITORIALE"
    return "LOCALE"


def scope_migration(count, population):
    if count >= 250 or population >= 25000:
        return "GENERAL"
    if count >= 100 or population >= 10000:
        return "TERRITORIALE"
    return "LOCALE"


def normalize(monthly):
    group_cols = [
        "Anno", "Codice comune", "Comune", "Codice provincia",
        "Provincia", "Codice regione", "Regione",
    ]
    annual = monthly.groupby(group_cols, as_index=False).agg(
        months=("Mese", "nunique"),
        births=("Nati vivi", "sum"),
        deaths=("Morti", "sum"),
        imm_internal=("Immigrati da altro comune", "sum"),
        emi_internal=("Emigrati per altro comune", "sum"),
        imm_foreign=("Immigrati dall'estero", "sum"),
        emi_foreign=("Emigrati per l'estero", "sum"),
        territorial_adjustment_abs=(
            "Unità in più/meno dovute a variazioni territoriali",
            lambda series: float(np.abs(series.fillna(0)).sum()),
        ),
        population_start=("Popolazione inizio periodo", "first"),
        population_end=("Popolazione fine periodo", "last"),
    )

    quality_annual = annual[annual["Anno"].isin(COMPLETE_YEARS)].copy()

    passport = quality_annual.groupby("Codice comune").agg(
        years=("Anno", "nunique"),
        min_months=("months", "min"),
        territorial_adjustment_abs=("territorial_adjustment_abs", "sum"),
        names=("Comune", "nunique"),
        provinces=("Codice provincia", "nunique"),
        regions=("Codice regione", "nunique"),
    ).reset_index()

    passport["quality_A"] = (
        passport["years"].eq(len(COMPLETE_YEARS))
        & passport["min_months"].eq(12)
        & passport["territorial_adjustment_abs"].eq(0)
        & passport["names"].eq(1)
        & passport["provinces"].eq(1)
        & passport["regions"].eq(1)
    )

    stable_codes = set(
        passport.loc[passport["quality_A"], "Codice comune"].astype(str)
    )
    annual = annual[annual["Codice comune"].isin(stable_codes)].copy()
    monthly = monthly[monthly["Codice comune"].isin(stable_codes)].copy()

    meta = (
        annual.sort_values(["Codice comune", "Anno"])
        .groupby("Codice comune")
        .tail(1)[
            [
                "Codice comune", "Comune", "Provincia", "Regione",
                "Codice provincia", "population_end",
            ]
        ]
        .set_index("Codice comune")
    )
    return monthly, annual, passport, meta, stable_codes


def annual_matrix(annual, column):
    return (
        annual.pivot(index="Codice comune", columns="Anno", values=column)
        .reindex(columns=YEARS)
        .dropna()
    )


def inversion_candidates(annual, meta, column, label, min_count):
    matrix = annual_matrix(annual, column)
    codes = matrix.index.to_numpy()
    values = matrix.to_numpy(float)
    history = values[:, :5]
    current = values[:, 5]
    previous = values[:, 4]
    med = np.median(history, axis=1)
    slope = theil_sen_rows(history)
    rho = spearman_time_rows(history)
    differences = np.diff(history, axis=1)
    dominant = np.sign(np.median(differences, axis=1))
    dominance = np.mean(np.sign(differences) == dominant[:, None], axis=1)

    x = np.arange(5, dtype=float)
    intercept = np.median(history - slope[:, None] * x, axis=1)
    expected = intercept + slope * 5
    residuals = history - (intercept[:, None] + slope[:, None] * x)
    scale = np.maximum(
        np.maximum(mad_rows(residuals), mad_rows(differences)),
        1.0,
    )
    reversal_gap = np.abs(current - expected) / scale
    delta = current - previous
    pct = np.divide(
        delta,
        np.abs(previous),
        out=np.zeros_like(delta),
        where=np.abs(previous) > EPS,
    )

    population = meta.loc[codes, "population_end"].to_numpy(float)
    scopes = np.array(
        [scope_birth_death(count, pop) for count, pop in zip(med, population)]
    )
    min_pct = np.where(
        scopes == "GENERAL",
        0.03,
        np.where(scopes == "TERRITORIALE", 0.05, 0.10),
    )
    min_abs = np.maximum(
        5,
        np.where(
            scopes == "GENERAL",
            0.01 * med,
            np.where(scopes == "TERRITORIALE", 0.03 * med, 0.10 * med),
        ),
    )

    keep = (
        (med >= min_count)
        & (dominance >= 0.75)
        & (np.abs(rho) >= 0.80)
        & (np.abs(slope) > EPS)
        & (np.sign(delta) != np.sign(slope))
        & (reversal_gap >= 2.0)
        & (np.abs(pct) >= min_pct)
        & (np.abs(delta) >= min_abs)
    )

    rows = []
    for idx in np.where(keep)[0]:
        code = str(codes[idx])
        m = meta.loc[code]
        strength_gap = min(100, 50 + 20 * max(0, reversal_gap[idx] - 2))
        strength_material = min(100, abs(pct[idx]) * 500)
        rows.append({
            "Codice comune": code,
            "Comune": m["Comune"],
            "Provincia": m["Provincia"],
            "Regione": m["Regione"],
            "Indicatore": label,
            "Pattern": "INVERSIONE",
            "Scope": scopes[idx],
            "Strength": 0.65 * strength_gap + 0.35 * strength_material,
            "Persistence": min(
                100, 50 + 30 * dominance[idx] + 20 * abs(rho[idx])
            ),
            "Population": population[idx],
            "Metric": reversal_gap[idx],
        })

    result = pd.DataFrame(rows)
    if len(result):
        result["Rarity"] = result["Metric"].rank(pct=True) * 100
    return result


def divergence_candidates(annual, meta, column, label, min_count):
    frame = annual[
        ["Anno", "Codice comune", "Codice provincia", column, "population_start"]
    ].copy()
    province = frame.groupby(
        ["Anno", "Codice provincia"], as_index=False
    ).agg(
        prov_flow=(column, "sum"),
        prov_pop=("population_start", "sum"),
    )
    frame = frame.merge(province, on=["Anno", "Codice provincia"], how="left")
    frame["rest_flow"] = frame["prov_flow"] - frame[column]
    frame["rest_pop"] = frame["prov_pop"] - frame["population_start"]
    frame["rate"] = frame[column] / frame["population_start"] * 1000
    frame["rest_rate"] = frame["rest_flow"] / frame["rest_pop"] * 1000

    local = (
        frame.pivot(index="Codice comune", columns="Anno", values="rate")
        .reindex(columns=YEARS)
        .dropna()
    )
    benchmark = (
        frame.pivot(index="Codice comune", columns="Anno", values="rest_rate")
        .reindex(columns=YEARS)
        .dropna()
    )
    counts = (
        annual.pivot(index="Codice comune", columns="Anno", values=column)
        .reindex(columns=YEARS)
        .dropna()
    )

    index = (
        local.index
        .intersection(benchmark.index)
        .intersection(counts.index)
        .intersection(meta.index)
    )
    rates = local.loc[index].to_numpy(float)
    bench = benchmark.loc[index].to_numpy(float)
    raw_counts = counts.loc[index].to_numpy(float)

    valid = (rates[:, :-1] > 0).all(axis=1) & (bench[:, :-1] > 0).all(axis=1)
    with np.errstate(divide="ignore", invalid="ignore"):
        local_change = np.diff(rates, axis=1) / rates[:, :-1]
        bench_change = np.diff(bench, axis=1) / bench[:, :-1]
    gap_history = local_change - bench_change
    history = gap_history[:, :4]
    median_history = np.nanmedian(history, axis=1)
    scale = np.maximum(mad_rows(history), 0.03)
    dz = (gap_history[:, 4] - median_history) / scale
    directional = np.sign(local_change[:, 4]) != np.sign(bench_change[:, 4])
    gap = gap_history[:, 4]

    median_count = np.median(raw_counts[:, :5], axis=1)
    population = meta.loc[index, "population_end"].to_numpy(float)
    scopes = np.array(
        [
            scope_birth_death(count, pop)
            for count, pop in zip(median_count, population)
        ]
    )
    material = np.where(directional, np.abs(gap) >= 0.05, np.abs(gap) >= 0.10)
    keep = (
        valid
        & np.isfinite(dz)
        & (median_count >= min_count)
        & (np.abs(dz) >= 2.5)
        & material
        & (scopes != "LOCALE")
    )

    rows = []
    codes = index.to_numpy()
    for idx in np.where(keep)[0]:
        code = str(codes[idx])
        m = meta.loc[code]
        strength_dz = min(100, 50 + 20 * max(0, abs(dz[idx]) - 2.5))
        strength_gap = min(100, abs(gap[idx]) * 500)
        rows.append({
            "Codice comune": code,
            "Comune": m["Comune"],
            "Provincia": m["Provincia"],
            "Regione": m["Regione"],
            "Indicatore": label,
            "Pattern": "DIVERGENZA",
            "Scope": scopes[idx],
            "Strength": 0.60 * strength_dz + 0.40 * strength_gap,
            "Persistence": 60.0,
            "Population": population[idx],
            "Metric": abs(dz[idx]),
        })

    result = pd.DataFrame(rows)
    if len(result):
        result["Rarity"] = result["Metric"].rank(pct=True) * 100
    return result


def rolling12_matrix(monthly, column):
    pivot = monthly.pivot(index="Codice comune", columns="date", values=column)
    end = monthly["date"].max()
    dates = pd.date_range("2019-01-01", end, freq="MS")
    pivot = pivot.reindex(columns=dates).dropna()
    values = pivot.to_numpy(float)
    if values.shape[1] < 12:
        raise RuntimeError("Serie mensile troppo corta per rolling 12 mesi.")
    cumulative = np.cumsum(values, axis=1)
    width = values.shape[1] - 11
    rolling = np.empty((values.shape[0], width), dtype=float)
    rolling[:, 0] = cumulative[:, 11]
    rolling[:, 1:] = cumulative[:, 12:] - cumulative[:, :-12]
    return pivot.index, rolling


def rolling_detectors(monthly, annual, meta, monthly_col, label, annual_col, min_count):
    index, rolling = rolling12_matrix(monthly, monthly_col)
    annual_counts = annual_matrix(annual, annual_col).reindex(index)
    median_count = np.nanmedian(annual_counts.to_numpy(float)[:, :5], axis=1)
    population = meta.loc[index, "population_end"].to_numpy(float)
    scopes = np.array(
        [
            scope_birth_death(count, pop)
            for count, pop in zip(median_count, population)
        ]
    )
    eligible = (median_count >= min_count) & (scopes != "LOCALE")
    rows = []

    current = rolling[:, -1]
    prior = rolling[:, :-1]
    previous_max = np.max(prior, axis=1)
    previous_min = np.min(prior, axis=1)
    new_max = current > previous_max
    new_min = current < previous_min
    margin = np.where(
        new_max,
        current - previous_max,
        np.where(new_min, previous_min - current, 0),
    )
    reference = np.where(new_max, previous_max, np.where(new_min, previous_min, 1))
    keep = (
        eligible
        & (new_max | new_min)
        & (margin >= np.maximum(5, 0.01 * np.maximum(reference, 1)))
    )
    for idx in np.where(keep)[0]:
        code = str(index[idx])
        m = meta.loc[code]
        margin_pct = margin[idx] / max(abs(reference[idx]), 1) * 100
        rows.append({
            "Codice comune": code,
            "Comune": m["Comune"],
            "Provincia": m["Provincia"],
            "Regione": m["Regione"],
            "Indicatore": label,
            "Pattern": "RECORD_MAX" if new_max[idx] else "RECORD_MIN",
            "Scope": scopes[idx],
            "Strength": min(100, 55 + margin_pct * 4),
            "Persistence": 70.0,
            "Population": population[idx],
            "Metric": margin_pct,
        })

    old = rolling[:, -13:-6]
    new = rolling[:, -7:]
    old_slope = theil_sen_rows(old)
    new_slope = theil_sen_rows(new)
    volatility = np.maximum(mad_rows(np.diff(rolling[:, -18:], axis=1)), 1.0)
    recent = np.diff(rolling[:, -4:], axis=1)
    recent_ok = (
        np.sum(np.sign(recent) == np.sign(new_slope)[:, None], axis=1) >= 2
    )
    level = np.maximum(np.abs(np.median(new, axis=1)), 1)
    min_slope = 0.0015 * level
    same_sign = (
        (np.sign(old_slope) == np.sign(new_slope))
        & (np.abs(old_slope) > EPS)
        & (np.abs(new_slope) > EPS)
    )

    ratio = np.abs(new_slope) / (np.abs(old_slope) + EPS)
    score = (np.abs(new_slope) - np.abs(old_slope)) / volatility
    keep = (
        eligible
        & same_sign
        & recent_ok
        & (np.abs(new_slope) > np.abs(old_slope))
        & (ratio >= 1.5)
        & (score >= 1.5)
        & (np.abs(new_slope) >= min_slope)
    )
    for idx in np.where(keep)[0]:
        code = str(index[idx])
        m = meta.loc[code]
        strength_a = min(100, 50 + 20 * max(0, score[idx] - 1.5))
        strength_b = min(100, 50 + 30 * max(0, ratio[idx] - 1.5))
        rows.append({
            "Codice comune": code,
            "Comune": m["Comune"],
            "Provincia": m["Provincia"],
            "Regione": m["Regione"],
            "Indicatore": label,
            "Pattern": "ACCELERAZIONE",
            "Scope": scopes[idx],
            "Strength": 0.65 * strength_a + 0.35 * strength_b,
            "Persistence": 75.0,
            "Population": population[idx],
            "Metric": score[idx],
        })

    ratio = np.abs(new_slope) / (np.abs(old_slope) + EPS)
    score = (np.abs(old_slope) - np.abs(new_slope)) / volatility
    keep = (
        eligible
        & same_sign
        & recent_ok
        & (np.abs(new_slope) < np.abs(old_slope))
        & (ratio <= 0.75)
        & (score >= 1.5)
        & (np.abs(old_slope) >= min_slope)
    )
    for idx in np.where(keep)[0]:
        code = str(index[idx])
        m = meta.loc[code]
        strength_a = min(100, 50 + 20 * max(0, score[idx] - 1.5))
        strength_b = min(100, 50 + 40 * max(0, 0.75 - ratio[idx]))
        rows.append({
            "Codice comune": code,
            "Comune": m["Comune"],
            "Provincia": m["Provincia"],
            "Regione": m["Regione"],
            "Indicatore": label,
            "Pattern": "RALLENTAMENTO",
            "Scope": scopes[idx],
            "Strength": 0.65 * strength_a + 0.35 * strength_b,
            "Persistence": 75.0,
            "Population": population[idx],
            "Metric": score[idx],
        })

    history = rolling[:, -25:-1]
    slope = theil_sen_rows(history)
    x = np.arange(history.shape[1], dtype=float)
    intercept = np.median(history - slope[:, None] * x, axis=1)
    expected = intercept + slope * history.shape[1]
    residuals = history - (intercept[:, None] + slope[:, None] * x)
    residual_median = np.median(residuals, axis=1)
    raw_mad = np.median(
        np.abs(residuals - residual_median[:, None]), axis=1
    )
    std = np.std(residuals, axis=1)
    scale = np.where(raw_mad > EPS, raw_mad, np.where(std > EPS, std, np.nan))
    z = 0.6745 * ((current - expected) - residual_median) / scale
    gap_pct = (current - expected) / np.maximum(np.abs(expected), 1) * 100
    keep = (
        eligible
        & np.isfinite(z)
        & (np.abs(z) >= 4.0)
        & (np.abs(gap_pct) >= 3.0)
    )
    for idx in np.where(keep)[0]:
        code = str(index[idx])
        m = meta.loc[code]
        strength_z = min(100, 50 + 12.5 * max(0, abs(z[idx]) - 4))
        strength_gap = min(100, abs(gap_pct[idx]) * 5)
        rows.append({
            "Codice comune": code,
            "Comune": m["Comune"],
            "Provincia": m["Provincia"],
            "Regione": m["Regione"],
            "Indicatore": label,
            "Pattern": "ANOMALIA",
            "Scope": scopes[idx],
            "Strength": 0.65 * strength_z + 0.35 * strength_gap,
            "Persistence": 50.0,
            "Population": population[idx],
            "Metric": abs(z[idx]),
        })

    result = pd.DataFrame(rows)
    if len(result):
        result["Rarity"] = (
            result.groupby("Pattern")["Metric"].rank(pct=True) * 100
        )
    return result


def migration_rolling(
    monthly, annual, meta, monthly_col, label, annual_col, min_count
):
    index, rolling = rolling12_matrix(monthly, monthly_col)
    annual_counts = annual_matrix(annual, annual_col).reindex(index)
    median_count = np.nanmedian(annual_counts.to_numpy(float)[:, :5], axis=1)
    population = meta.loc[index, "population_end"].to_numpy(float)
    scopes = np.array(
        [
            scope_migration(count, pop)
            for count, pop in zip(median_count, population)
        ]
    )
    eligible = (median_count >= min_count) & (scopes != "LOCALE")
    rows = []

    current = rolling[:, -1]
    prior = rolling[:, :-1]
    previous_max = np.max(prior, axis=1)
    previous_min = np.min(prior, axis=1)
    new_max = current > previous_max
    new_min = current < previous_min
    margin = np.where(
        new_max,
        current - previous_max,
        np.where(new_min, previous_min - current, 0),
    )
    reference = np.where(new_max, previous_max, np.where(new_min, previous_min, 1))
    keep = (
        eligible
        & (new_max | new_min)
        & (margin >= np.maximum(10, 0.02 * np.maximum(reference, 1)))
    )
    for idx in np.where(keep)[0]:
        code = str(index[idx])
        m = meta.loc[code]
        margin_pct = margin[idx] / max(abs(reference[idx]), 1) * 100
        rows.append({
            "Codice comune": code,
            "Comune": m["Comune"],
            "Provincia": m["Provincia"],
            "Regione": m["Regione"],
            "Indicatore": label,
            "Pattern": "RECORD_MAX" if new_max[idx] else "RECORD_MIN",
            "Scope": scopes[idx],
            "Strength": min(100, 55 + margin_pct * 3),
            "Persistence": 70.0,
            "Population": population[idx],
            "Metric": margin_pct,
        })

    old = rolling[:, -13:-6]
    new = rolling[:, -7:]
    old_slope = theil_sen_rows(old)
    new_slope = theil_sen_rows(new)
    volatility = np.maximum(mad_rows(np.diff(rolling[:, -18:], axis=1)), 1.0)
    recent = np.diff(rolling[:, -4:], axis=1)
    recent_ok = (
        np.sum(np.sign(recent) == np.sign(new_slope)[:, None], axis=1) >= 2
    )
    level = np.maximum(np.abs(np.median(new, axis=1)), 1)
    same_sign = (
        (np.sign(old_slope) == np.sign(new_slope))
        & (np.abs(old_slope) > EPS)
        & (np.abs(new_slope) > EPS)
    )
    min_slope = 0.002 * level

    ratio = np.abs(new_slope) / (np.abs(old_slope) + EPS)
    score = (np.abs(new_slope) - np.abs(old_slope)) / volatility
    keep = (
        eligible
        & same_sign
        & recent_ok
        & (np.abs(new_slope) > np.abs(old_slope))
        & (ratio >= 1.75)
        & (score >= 1.75)
        & (np.abs(new_slope) >= min_slope)
    )
    for idx in np.where(keep)[0]:
        code = str(index[idx])
        m = meta.loc[code]
        strength_a = min(100, 50 + 18 * max(0, score[idx] - 1.75))
        strength_b = min(100, 50 + 25 * max(0, ratio[idx] - 1.75))
        rows.append({
            "Codice comune": code,
            "Comune": m["Comune"],
            "Provincia": m["Provincia"],
            "Regione": m["Regione"],
            "Indicatore": label,
            "Pattern": "ACCELERAZIONE",
            "Scope": scopes[idx],
            "Strength": 0.65 * strength_a + 0.35 * strength_b,
            "Persistence": 75.0,
            "Population": population[idx],
            "Metric": score[idx],
        })

    ratio = np.abs(new_slope) / (np.abs(old_slope) + EPS)
    score = (np.abs(old_slope) - np.abs(new_slope)) / volatility
    keep = (
        eligible
        & same_sign
        & recent_ok
        & (np.abs(new_slope) < np.abs(old_slope))
        & (ratio <= 0.65)
        & (score >= 1.75)
        & (np.abs(old_slope) >= min_slope)
    )
    for idx in np.where(keep)[0]:
        code = str(index[idx])
        m = meta.loc[code]
        strength_a = min(100, 50 + 18 * max(0, score[idx] - 1.75))
        strength_b = min(100, 50 + 35 * max(0, 0.65 - ratio[idx]))
        rows.append({
            "Codice comune": code,
            "Comune": m["Comune"],
            "Provincia": m["Provincia"],
            "Regione": m["Regione"],
            "Indicatore": label,
            "Pattern": "RALLENTAMENTO",
            "Scope": scopes[idx],
            "Strength": 0.65 * strength_a + 0.35 * strength_b,
            "Persistence": 75.0,
            "Population": population[idx],
            "Metric": score[idx],
        })

    history = rolling[:, -25:-1]
    slope = theil_sen_rows(history)
    x = np.arange(history.shape[1], dtype=float)
    intercept = np.median(history - slope[:, None] * x, axis=1)
    expected = intercept + slope * history.shape[1]
    residuals = history - (intercept[:, None] + slope[:, None] * x)
    residual_median = np.median(residuals, axis=1)
    raw_mad = np.median(
        np.abs(residuals - residual_median[:, None]), axis=1
    )
    std = np.std(residuals, axis=1)
    scale = np.where(raw_mad > EPS, raw_mad, np.where(std > EPS, std, np.nan))
    z = 0.6745 * ((current - expected) - residual_median) / scale
    gap_pct = (current - expected) / np.maximum(np.abs(expected), 1) * 100
    keep = (
        eligible
        & np.isfinite(z)
        & (np.abs(z) >= 4.5)
        & (np.abs(gap_pct) >= 5.0)
    )
    for idx in np.where(keep)[0]:
        code = str(index[idx])
        m = meta.loc[code]
        strength_z = min(100, 50 + 12 * max(0, abs(z[idx]) - 4.5))
        strength_gap = min(100, abs(gap_pct[idx]) * 4)
        rows.append({
            "Codice comune": code,
            "Comune": m["Comune"],
            "Provincia": m["Provincia"],
            "Regione": m["Regione"],
            "Indicatore": label,
            "Pattern": "ANOMALIA",
            "Scope": scopes[idx],
            "Strength": 0.65 * strength_z + 0.35 * strength_gap,
            "Persistence": 50.0,
            "Population": population[idx],
            "Metric": abs(z[idx]),
        })

    result = pd.DataFrame(rows)
    if len(result):
        result["Rarity"] = (
            result.groupby("Pattern")["Metric"].rank(pct=True) * 100
        )
    return result


def merge_events(events, migration=False):
    rows = []
    for (code, indicator), group in events.groupby(
        ["Codice comune", "Indicatore"]
    ):
        first = group.iloc[0]
        patterns = list(dict.fromkeys(group["Pattern"].tolist()))
        strength = float(group["Strength"].max())
        rarity = (
            float(group["Rarity"].max())
            if group["Rarity"].notna().any()
            else 50.0
        )
        persistence = float(group["Persistence"].max())
        convergence = (
            (80.0 if migration else 85.0)
            if len(patterns) >= 2
            else 30.0
        )
        context = 60.0 if migration else (90.0 if "DIVERGENZA" in patterns else 60.0)
        freshness = 50.0
        quality = 0.95
        base = (
            0.40 * strength
            + 0.20 * rarity
            + 0.15 * persistence
            + 0.10 * convergence
            + 0.10 * freshness
            + 0.05 * context
        )
        score = round(quality * base, 1)
        scope = first["Scope"]

        if score >= 80 and scope == "GENERAL":
            status = "VALIDATO — FEED GENERALE"
        elif score >= 72 and scope in ("GENERAL", "TERRITORIALE"):
            status = "VALIDATO — FEED TERRITORIALE"
        elif score >= 65:
            status = "PROMETTENTE — RIVEDERE"
        else:
            status = "ARCHIVIO / SCARTO"

        rows.append({
            "Codice comune": code,
            "Comune": first["Comune"],
            "Provincia": first["Provincia"],
            "Regione": first["Regione"],
            "Indicatore": indicator,
            "Patterns": " + ".join(patterns),
            "Scope": scope,
            "Strength": strength,
            "Rarity": rarity,
            "Persistence": persistence,
            "Convergence": convergence,
            "Freshness_backtest": freshness,
            "Context": context,
            "Quality": quality,
            "PULSE_Score_backtest": score,
            "Stato_validazione": status,
        })
    return pd.DataFrame(rows)


def build_feed(monthly, annual, meta):
    births_deaths = pd.concat(
        [
            inversion_candidates(annual, meta, "births", "Nati vivi", 50),
            inversion_candidates(annual, meta, "deaths", "Morti", 80),
            divergence_candidates(annual, meta, "births", "Nati vivi", 75),
            divergence_candidates(annual, meta, "deaths", "Morti", 100),
            rolling_detectors(
                monthly, annual, meta, "Nati vivi", "Nati vivi", "births", 100
            ),
            rolling_detectors(
                monthly, annual, meta, "Morti", "Morti", "deaths", 150
            ),
        ],
        ignore_index=True,
        sort=False,
    )
    bd = merge_events(births_deaths, migration=False)

    migration = pd.concat(
        [
            migration_rolling(
                monthly, annual, meta,
                "Immigrati da altro comune",
                "Immigrati da altro comune",
                "imm_internal", 150,
            ),
            migration_rolling(
                monthly, annual, meta,
                "Emigrati per altro comune",
                "Emigrati per altro comune",
                "emi_internal", 150,
            ),
            migration_rolling(
                monthly, annual, meta,
                "Immigrati dall'estero",
                "Immigrati dall'estero",
                "imm_foreign", 75,
            ),
            migration_rolling(
                monthly, annual, meta,
                "Emigrati per l'estero",
                "Emigrati per l'estero",
                "emi_foreign", 50,
            ),
        ],
        ignore_index=True,
        sort=False,
    )
    mig = merge_events(migration, migration=True)

    combined = pd.concat([bd, mig], ignore_index=True, sort=False)
    combined = combined.sort_values(
        "PULSE_Score_backtest", ascending=False
    ).reset_index(drop=True)
    feed = combined[combined["PULSE_Score_backtest"] >= 65].copy()
    feed["event_id"] = [
        hashlib.sha1(
            f"{row['Codice comune']}|{row['Indicatore']}|{LATEST_PERIOD.strftime('%Y-%m')}|{row['Patterns']}".encode()
        ).hexdigest()[:16]
        for _, row in feed.iterrows()
    ]
    return feed.reset_index(drop=True)


def make_detail_payload(feed, monthly, annual):
    province_totals = {}
    for indicator, key in ANNUAL_KEY.items():
        province_totals[indicator] = annual.groupby(
            ["Anno", "Codice provincia"], as_index=False
        ).agg(flow=(key, "sum"), pop=("population_start", "sum"))

    rows = []
    for _, event in feed.iterrows():
        code = str(event["Codice comune"])
        indicator = event["Indicatore"]
        source_column = INDICATOR_COLUMN[indicator]
        series = monthly[
            monthly["Codice comune"].eq(code)
        ].sort_values("date")

        annual_frame = series[
            series["Anno"].isin(COMPLETE_YEARS)
        ].groupby("Anno", as_index=False).agg(
            value=(source_column, "sum"),
            pop=("Popolazione inizio periodo", "first"),
        )
        annual_values = [int(value) for value in annual_frame["value"].tolist()]

        values = series[source_column].astype(float).to_numpy()
        rolling_values = []
        if len(values) >= 12:
            rolling = pd.Series(values).rolling(12).sum()
            rolling_values = [
                int(round(value))
                for idx, value in enumerate(rolling)
                if idx >= 11 and pd.notna(value)
            ]

        key = ANNUAL_KEY[indicator]
        local_annual = annual[
            annual["Codice comune"].eq(code)
            & annual["Anno"].isin(COMPLETE_YEARS)
        ].sort_values("Anno")
        province = province_totals[indicator]
        benchmark_local = []
        benchmark_rest = []
        for _, row in local_annual.iterrows():
            province_row = province[
                province["Anno"].eq(row["Anno"])
                & province["Codice provincia"].eq(row["Codice provincia"])
            ]
            if not len(province_row):
                continue
            pr = province_row.iloc[0]
            local_flow = float(row[key])
            local_pop = float(row["population_start"])
            rest_flow = float(pr["flow"]) - local_flow
            rest_pop = float(pr["pop"]) - local_pop
            benchmark_local.append(
                round(local_flow / local_pop * 1000, 3)
                if local_pop else np.nan
            )
            benchmark_rest.append(
                round(rest_flow / rest_pop * 1000, 3)
                if rest_pop else np.nan
            )

        patterns = [
            item.strip() for item in str(event["Patterns"]).split("+")
        ]
        analysis = []

        if "INVERSIONE" in patterns and len(annual_values) >= 2:
            previous, current = annual_values[-2], annual_values[-1]
            pct = (current - previous) / previous * 100 if previous else 0.0
            analysis.append(
                f"Inversione: nel {YEARS[-1]} la serie cambia direzione "
                f"da {previous} a {current} ({pct:+.1f}%)."
            )

        if (
            "DIVERGENZA" in patterns
            and len(benchmark_local) >= 2
            and benchmark_local[-2]
            and benchmark_rest[-2]
        ):
            local_change = (
                benchmark_local[-1] / benchmark_local[-2] - 1
            ) * 100
            rest_change = (
                benchmark_rest[-1] / benchmark_rest[-2] - 1
            ) * 100
            analysis.append(
                f"Divergenza territoriale: il tasso locale varia del "
                f"{local_change:+.1f}% contro {rest_change:+.1f}% "
                f"nel resto della provincia."
            )

        if "RECORD_MAX" in patterns and rolling_values:
            analysis.append(
                f"Record: il rolling 12 mesi di {LATEST_PERIOD.strftime('%Y-%m')} "
                f"({rolling_values[-1]}) supera il massimo precedente "
                f"({max(rolling_values[:-1])})."
            )
        if "RECORD_MIN" in patterns and rolling_values:
            analysis.append(
                f"Record: il rolling 12 mesi di {LATEST_PERIOD.strftime('%Y-%m')} "
                f"({rolling_values[-1]}) scende sotto il minimo precedente "
                f"({min(rolling_values[:-1])})."
            )
        if "ACCELERAZIONE" in patterns:
            analysis.append(
                "Accelerazione: il fenomeno prosegue nella stessa direzione "
                "ma la pendenza recente aumenta rispetto alla finestra precedente."
            )
        if "RALLENTAMENTO" in patterns:
            analysis.append(
                "Rallentamento: il fenomeno prosegue nella stessa direzione "
                "ma la pendenza recente si riduce rispetto alla finestra precedente."
            )
        if "ANOMALIA" in patterns:
            analysis.append(
                "Anomalia: l'ultimo valore rolling 12 mesi si discosta in modo "
                "robusto dal trend recente oltre la soglia tecnica PULSE."
            )

        analysis.append(
            f"PULSE Score: {float(event['PULSE_Score_backtest']):.1f}/100. "
            f"Stato: {event['Stato_validazione']}."
        )

        if "INVERSIONE" in patterns and len(annual_values) >= 2:
            previous, current = annual_values[-2], annual_values[-1]
            pct = (current - previous) / previous * 100 if previous else 0.0
            verb = (
                "tornano a crescere"
                if current > previous
                else "tornano a diminuire"
            )
            summary = (
                f"{event['Comune']}: {indicator.lower()} {verb} nel {YEARS[-1]} "
                f"({previous} → {current}, {pct:+.1f}%)."
            )
            if (
                "DIVERGENZA" in patterns
                and len(benchmark_rest) >= 2
                and benchmark_rest[-2]
            ):
                rest_change = (
                    benchmark_rest[-1] / benchmark_rest[-2] - 1
                ) * 100
                summary += (
                    f" Il movimento diverge dal resto della provincia "
                    f"({rest_change:+.1f}%)."
                )
        elif "RECORD_MAX" in patterns and rolling_values:
            summary = (
                f"{event['Comune']}: {indicator.lower()} raggiunge un nuovo "
                f"massimo dei 60 mesi precedenti su base mobile 12 mesi "
                f"({rolling_values[-1]})."
            )
        elif "RECORD_MIN" in patterns and rolling_values:
            summary = (
                f"{event['Comune']}: {indicator.lower()} raggiunge un nuovo "
                f"minimo dei 60 mesi precedenti su base mobile 12 mesi "
                f"({rolling_values[-1]})."
            )
        else:
            summary = (
                f"{event['Comune']}: rilevato "
                f"{str(event['Patterns']).lower()} su {indicator.lower()}."
            )

        rows.append({
            "id": event["event_id"],
            "municipality_code": code,
            "municipality": event["Comune"],
            "province": event["Provincia"],
            "region": event["Regione"],
            "indicator": indicator,
            "patterns": "|".join(patterns),
            "scope": event["Scope"],
            "score": round(float(event["PULSE_Score_backtest"]), 1),
            "validation_status": event["Stato_validazione"],
            "period": LATEST_PERIOD.strftime("%Y-%m"),
            "summary": summary,
            "annual": "|".join(map(str, annual_values)),
            "rolling12": "|".join(map(str, rolling_values)),
            "benchmark_local": "|".join(
                "" if pd.isna(value) else str(value)
                for value in benchmark_local
            ),
            "benchmark_rest": "|".join(
                "" if pd.isna(value) else str(value)
                for value in benchmark_rest
            ),
            "analysis": "¦".join(analysis),
            "source_family": "DEMO ISTAT — Bilancio demografico mensile",
            "source_url": "https://demo.istat.it/app/?i=D7B",
        })

    return pd.DataFrame(rows)


def main():
    global YEARS, COMPLETE_YEARS, LATEST_PERIOD

    ASSET_DIR.mkdir(parents=True, exist_ok=True)
    monthly, source_info = load_sources()

    month_counts = monthly.groupby("Anno")["Mese"].nunique().sort_index()
    COMPLETE_YEARS = [int(year) for year, count in month_counts.items() if int(count) == 12]
    if len(COMPLETE_YEARS) < 6:
        raise RuntimeError(
            f"Servono almeno 6 anni completi; disponibili: {COMPLETE_YEARS}"
        )

    YEARS = COMPLETE_YEARS[-6:]
    LATEST_PERIOD = monthly["date"].max()

    print(f"Complete years for annual Radar: {YEARS}")
    print(f"Latest monthly period: {LATEST_PERIOD.strftime('%Y-%m')}")

    monthly, annual, passport, meta, stable_codes = normalize(monthly)
    feed = build_feed(monthly, annual, meta)
    detail = make_detail_payload(feed, monthly, annual)
    detail.to_csv(OUT_TSV, sep="\t", index=False)
    feed_sha256 = hashlib.sha256(OUT_TSV.read_bytes()).hexdigest()

    manifest = {
        "version": "0.5",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "feed_sha256": feed_sha256,
        "source_period": f"2019-{LATEST_PERIOD.strftime('%Y-%m')}",
        "complete_years": COMPLETE_YEARS,
        "annual_radar_years": YEARS,
        "latest_period": LATEST_PERIOD.strftime("%Y-%m"),
        "latest_period_provisional": LATEST_PERIOD.year > max(COMPLETE_YEARS),
        "quality_A_municipalities": len(stable_codes),
        "feed_events": len(feed),
        "indicators": sorted(feed["Indicatore"].unique().tolist()),
        "sources": source_info,
        "disclaimer": (
            "Prototipo indipendente basato su dati pubblici ISTAT. "
            "Non è un prodotto ufficiale ISTAT."
        ),
    }
    OUT_MANIFEST.write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    if len(feed) < 50:
        raise RuntimeError(
            f"Quality guardrail failed: feed unexpectedly small ({len(feed)} events)"
        )

    print(f"PULSE feed generated: {len(feed)} events")
    print(feed["Indicatore"].value_counts().to_string())
    print(f"Asset: {OUT_TSV} ({OUT_TSV.stat().st_size} bytes)")


if __name__ == "__main__":
    main()
