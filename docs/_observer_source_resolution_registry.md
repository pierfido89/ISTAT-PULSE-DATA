# Observer Source Resolution Registry

> Internal technical registry for ISTAT PULSE data connectors.
> This file is intentionally not used by the Android UI. It exists as a
> source-code maintenance memory: before changing a connector, read this file.
> Do not expose it in the app.

## Purpose

This registry records, for every Observer source that required special handling:

- failure mode observed on GitHub-hosted runners;
- stable connector/adapter used in production;
- discovery transport;
- final accepted source domain/path;
- verification strategy;
- fallback strategy;
- historical notes and known traps.

The authoritative machine configuration remains:
`data/observer_sources.json`

The implementation remains:
`scripts/update_observer_archive.py`

This document explains WHY those rules exist.

---

## Global rules

### 1. Never reopen blocked sources after successful URL decoding

For RSS-decoder adapters, once Google News RSS has been decoded to the
official publisher URL, do **not** call `page_info()` on the official source
again if that source is known to block GitHub runners.

The decoded official URL + RSS publication date is already the verified
transport result.

Current RSS-decoder adapters:

- `anfia_google_news_rss`
- `confcommercio_google_news_rss`
- `gse_google_news_rss`
- `salute_google_news_rss`
- `mim_google_news_rss`

Verification method:
`decoded_official_url_rss_date`

### 2. Google News is transport only

Never store a Google News URL as the public source.

Pipeline:

Google News RSS
→ signed Google News article URL
→ decode with `googlenewsdecoder`
→ validate final domain/path
→ store only official publisher URL

Pinned runtime:

- `googlenewsdecoder` from commit
  `d38ddbdd510561859da0dae0c1176e3a2676c159`
- `selectolax==0.4.12`

Reason:
newer `selectolax 1.x` removed the backend used by the decoder and caused
ImportError before decoding.

### 3. Preserve working fallbacks

Do not remove an official fallback merely because a stronger adapter is added.
Examples:

- MIM keeps `dati.gov.it`
- OpenCoesione uses `dati.gov.it`
- SINAB keeps scoped SSL relaxation

---

# Source resolutions

## ANFIA

Adapter:
`anfia_google_news_rss`

Observed problem:
- old generic discovery historically produced ~55 items;
- later the same generic pipeline found candidate URLs but detail verification
  returned zero;
- direct ANFIA transport became unstable from GitHub runners;
- reopening official pages after discovery reintroduced the failure.

Stable solution:
- Google News RSS thematic discovery;
- async signed-URL decoding;
- accept only final URLs on `anfia.it`;
- retain only:
  - `/it/comunicazione/notizie-e-comunicati/`
  - `/it/attivita/studi-e-statistiche/focus-dossier-pubblicazioni/`

Exclude:
- events;
- training / formazione;
- press review;
- service subdomains;
- unrelated PDFs/pages.

Validated production result on 2026-10-07:
- indexed: 73
- useful decoded official items: 46
- decode misses: 0

Important:
the old historical ~55 count is NOT the current benchmark to force artificially.
Current stable clean coverage is 46 and should grow with future publications.

---

## Confcommercio

Adapter:
`confcommercio_google_news_rss`

Observed problem:
- archive, sitemap, robots, RSS and feed return HTTP 403 to GitHub runners.

Stable solution:
- Google News RSS;
- decode signed URLs concurrently;
- retain only official central pages:
  `confcommercio.it/-/`

Validated result:
- 440 publications for 2026
- 440 decoded
- 0 decode errors

Do not:
- keep Google News URLs;
- crawl territorial sites unless explicitly added as separate sources.

---

## GSE

Adapter:
`gse_google_news_rss`

Observed problem:
- GSE newsroom/statistics/sitemap/RSS return HTTP 403 to GitHub runners.

Stable solution:
Google News RSS → decoder → official GSE URL

Allowed paths:
- `/media/comunicati/`
- `/servizi-per-te/news/`
- `/media/focus/`

Exclude:
- FAQ;
- tenders/procurement;
- regional regulation pages;
- unrelated technical PDFs.

Validated result:
- 31 publications for 2026
- 31 decoded
- 0 decode errors

---

## Ministero della Salute

Adapter:
`salute_google_news_rss`

Observed problem:
- official pages and RSS exist, but Gcore browser validation masks them for
  GitHub runners;
- HTTP 200 may actually be the anti-bot validation page;
- direct RSS cannot therefore be trusted from the runner.

Stable solution:
Google News RSS → signed-token decoder → final `salute.gov.it` URL

Decoder notes:
- protocol uses `data-n-a-sg`, `data-n-a-ts`, RPC `Fbv4je`;
- pin decoder + selectolax versions as documented above.

Validated result:
- 23/23 RSS items decoded correctly in the focused test;
- 35 publications reached by the full 2026 source process at validation time.

Never store Google News URLs.

---

## Ministero dell'Istruzione e del Merito (MIM)

Adapter:
`mim_google_news_rss`

Observed problem:
- `mim.gov.it` returns HTTP 403 from GitHub runners for:
  - newsroom;
  - sitemap;
  - robots;
  - RSS;
  - Liferay APIs.

Stable solution:
Google News RSS → decoder → official MIM URL

Accept only central Ministry publication paths:
- `/web/guest/-/`
- root `/-/`

Exclude:
- USR;
- provincial/local offices;
- local interpelli;
- territorial pages.

Date rule:
if the official title contains an explicit date, prefer that date over Google
News pubDate because Google News may reflect re-indexing.

Fallback:
retain `dati.gov.it` as a secondary official source for MIM datasets.

Validated result:
- 271 central MIM publications
- +1 official dati.gov.it fallback
- total 272 for 2026 at validation time.

---

## ISMEA

Adapter:
`ismea_listing`

Observed problem:
- GitHub runner cannot validate the certificate chain served by `ismea.it`.

Stable solution:
- scoped SSL verification relaxation ONLY for `ismea.it`;
- parse official monthly newsroom archives:
  `/Press-Area/Comunicati-Stampa/L/IT/YY/<year>/MM/<month>`

Do not use legacy query-string monthly URLs; they returned 404/unstable results.

Validated result:
- 59 total 2026 publications in the source process;
- 46 directly from the monthly archive adapter at validation time.

---

## SINAB

Adapter:
`wordpress_rest_ssl_fallback`

Observed problem:
broken/incomplete TLS certificate chain on GitHub runners.

Stable solution:
- scoped SSL relaxation only for SINAB hosts;
- WordPress REST API fallback.

Validated historical result:
230 publications for 2026.

---

## MIT

Observed problem:
TLS certificate chain issue on GitHub runners.

Stable solution:
scoped SSL verification relaxation only for `mit.gov.it`.

Validated historical result:
121 publications for 2026.

---

## SNAM

Adapter:
`snam_sitemap`

Stable solution:
- official sitemap;
- collect URLs under:
  `/it/media/news-e-comunicati-stampa/comunicati-stampa/<year>/`
- resolve AEM detail metadata through `.model.json`.

Validated historical result:
32 publications for 2026.

---

## CGIA Mestre

Adapter:
`cgiamestre`

Stable solution:
dedicated listing parser.

Validated historical result:
55 publications.

---

## OpenCoesione

Adapter:
`opencoesione_datigov`

Observed problem:
official OpenCoesione endpoints return country/IP based access denial from
GitHub-hosted US runners.

Stable solution:
use official Italian catalog `dati.gov.it` as discovery/fallback and retain
original OpenCoesione URLs where available.

Validated historical result:
82 publications/datasets for 2026.

---

# Operational checklist before changing any connector

1. Read this file.
2. Read the source block in `data/observer_sources.json`.
3. Inspect the source-specific adapter in
   `scripts/update_observer_archive.py`.
4. Run the isolated source workflow.
5. Never declare a source fixed only because the workflow completed.
6. Verify the logical result count in logs.
7. Keep the final public URL on the official source domain.
8. Do not replace a working permanent adapter with a generic crawler unless
   there is a measured regression.
9. If a source blocks GitHub runners, do not reintroduce direct page
   verification after an already verified decoder/fallback step.
10. Update this registry whenever a source resolution changes.

---

# Current status

As of 2026-10-07:
- all 65 Observer sources have an automatic connector/path;
- ANFIA was the last unresolved connector and is now handled by
  `anfia_google_news_rss`.

This file is maintenance documentation, not user-facing product content.
