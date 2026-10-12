# PULSE — Problema 11: distintivo NEW, prima pubblicazione e 180 minuti

**Data:** 12 ottobre 2026  
**Priorità originale:** MEDIA  
**Ambito:** News Radar / Notizie PULSE / Home / dettaglio / Preferiti.  
**Esclusioni:** Pubblicazioni (archivio dei documenti originali degli osservatori), report storici, pagine delle fonti, date di ultimo download o ultimo aggiornamento.

## 1. Contratto temporale

NEW compare **soltanto** quando un articolo porta un timestamp esplicito, valido e timezone-aware nel campo `first_published_at_utc`, riferito **al primo ingresso nella pubblicazione di PULSE**, non al rilascio del documento da parte della fonte.

Formula: `0 <= now_utc - first_published_at_utc < 180 minuti`. Esattamente a 180 minuti (10.800.000 ms) il badge scompare; non è mostrato per timestamp futuri, mancanti, senza timezone o malformati. Il cambio di giorno, il refresh orario e il riavvio dell'app non riavviano il conteggio.

Un articolo già presente nei feed precedenti all'implementazione non riceve il nuovo timestamp **retroattivamente**. Niente falsi «NEW» per vecchi articoli importati adesso.

## 2. Produzione del dato

`scripts/pulse_new_badge.py` introduce `stamp_first_pulse_publication(...)`. `scripts/update_news_radar.py` lo invoca all'ingresso dei tre percorsi editoriali (notizia giornalistica attribuita, fonte primaria verificata e articolo verificato manualmente nel Radar). Per evitare false novità, la sorgente deve avere una data RSS con timezone e non più vecchia di 24 ore al momento della prima pubblicazione PULSE. Il campo viene scritto una volta, conservato nei refresh successivi e NON deriva da last_seen_at / generated_at / download time.

Questo vincolo prudenziale delle 24 ore è una **condizione aggiuntiva di ammissione al badge**, non la durata del distintivo: il badge resta di **180 minuti dalla prima pubblicazione PULSE**. Nei casi con fonte senza orario attendibile il badge non viene mostrato.

La paginazione editoriale separata conserva già `first_published_at_utc` delle schede approvate: il client è compatibile con lo stesso campo, ma **non** rende NEW visibile ai documenti archivistici `ObserverArticle`.

## 3. Integrazione Android

- `PulseModels.kt`: `NewsRadarArticle.firstPublishedAtUtc` letto dal JSON; stringa vuota predefinita per i vecchi feed.
- `PulseNewBadge.kt`: funzione pura `PulseNewBadge.isNew` + Composable pill rosso `NEW`.
- `PulseHome.kt`: Home, quattro card in evidenza, NewsRadarCard, articolo interno, controllo UI ogni 15 secondi; aggiornamento automatico dell'età anche senza rete e senza rigenerare l'app.
- `PulseApp.kt`: aggiunto il badge alle **notizie** salvate nei Preferiti e ai loro dettagli, senza modificare le card Pubblicazioni (documenti storici).
- Compatibilità con il problema 12: la logica di revoca continua a oscurare articoli ritirati o non riconvalidati, a prescindere dal badge; NEW non rende mai pubblicabile un articolo ritirato.

L'aspetto grafico usa rosso PULSE intenso (#D31B32), testo bianco bold, piccolo rettangolo con angoli arrotondati, in posizione coerente col titolo/dati.

## 4. Criteri di verifica

- Data originale PULSE presente; `179m 59s` = NEW, `180m 00s` = no.
- Prima pubblicazione immutabile attraverso aggiornamenti, riscritture o fetch successivi.
- Non taggare dati storici anche se scaricati oggi.
- Orari UTC, offset Italia, cambio mezzanotte; rifiuto del futuro.
- Mancanza o errore di data: non mostrare NEW, senza crash.
- Preferiti e articolo aperto si aggiornano allo scadere con l'orologio UI.
- Non modificare `main`, non generare APK o pubblicare nuovi articoli senza autorizzazione.

## 5. Prove e stato

Script di test: `tests/test_pulse_new_badge.py`. Android: `PulseNewBadgeTest.kt`. Workflow CI dei rami sperimentali: `pulse-new-badge-news-tests.yml` e `pulse-new-badge-tests.yml`.

**Stato:** implementato nei rami di sviluppo. I test e i link della loro esecuzione dovranno essere registrati dopo il completamento delle pipeline; la nuova versione 4.3.6 installata non viene aggiornata automaticamente da questi commit. Rollout soltanto dopo integrazione e nuova release richiesta.

**Regola della Bibbia:** nessun problema si considera documentato senza registrare motivazione, file cambiati, dati, test, limiti e stato reale di adozione.
