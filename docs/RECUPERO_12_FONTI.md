# PULSE — Recupero delle 12 fonti (6 ottobre 2026)

## Obiettivo e ambito

Le fonti residue sono CNR, Confcommercio, SVIMEZ, ENIT, GSE, ISMEA, Ministero della Salute, MIM, MIT, OpenCoesione, SINAB, SNAM. CNA, CONSOB e INPS non vengono sovrascritte.

I nuovi adapter usano ingressi istituzionali dedicati, non tentativi generici `/opendata` o `/dataset`. I record sono **pubblicazioni** e **indici di cataloghi**, non affermazioni statistiche già verificate. È vietato promuovere numeri da pagine o PDF a `verified_series` senza verifiche di dimensioni, unità, territorio, periodo e coerenza dell'estrazione.

## Stato verificabile

- Siti/URL istituzionali identificati con ricerca web il 15/10/2026 e catalogati in `data/observer_sources_12_registry.json`.
- Script `scripts/repair_observer_sources_12.py`: contatta le 12 pagine, verifica HTTPS, appartenenza all'ente, titolo e data esplicita nello stesso record; esclude date mancanti, collegamenti esterni e pagine non pertinenti; registra anche gli errori senza attribuire successi fittizi.
- Output `data/observer_sources_12_status.json` e `data/observer_articles_12.json` (prodotti dall'esecuzione reale, NON consegnati come se fossero già stati scaricati). Il campo `article_type` distingue `official_publication` e `dataset_catalog`.
- Script `scripts/merge_observer_sources_12.py`: accetta solo l'archivio ufficiale completo (>=1000 elementi) e scrive su un nuovo percorso. Non altera `published_at`, non elimina articoli preesistenti, non inventa titoli, statistiche o date, non sovrascrive il JSON originale.
- 6 test locali offline passati il 15/10/2026. Non equivalgono a un test di raggiungibilità in rete: il fetch live va eseguito su Windows o su runner autorizzato.

## Esecuzione (Windows)

Apri `AVVIA-RECUPERO-12-FONTI.cmd`, che usa `py -3`, installa le dipendenze essenziali e genera i due output in `data/`. NON tocca i file nell'app né GitHub.

Per l'inserimento finale in PULSE: eseguire il merge con l'archivio completo `observer_articles.json` ufficiale e sottoporre i nuovi record a QA editoriale (non classificarli come notizie statistiche verificate); gli aggiornamenti automatici del ramo `main` richiedono autorizzazione al merge e avvio programmato, non vengono simulati.

## Evidenze ufficiali dei portali

| Fonte | Pagina ufficiale individuata | Tipo |
|---|---|---|
| CNR | https://www.cnr.it/it/comunicati-stampa | comunicati datati |
| Confcommercio | https://www.confcommercio.it/ | rapporti studi e congiuntura |
| SVIMEZ | https://www.svimez.it/ | rapporti e ricerche |
| ENIT | https://www.enit.it/it/ufficio-studi | studi turismo |
| GSE | https://www.gse.it/dati-e-scenari/statistiche | statistiche energia |
| ISMEA | https://www.ismeamercati.it/dati-agroalimentare/indice-prezzi | indice prezzi / download |
| Ministero della Salute | https://www.dati.salute.gov.it/ | open data CSV/JSON |
| MIM | https://dati.istruzione.it/opendata/opendata/catalogo/elements1/?area=Scuole | portale dati della scuola |
| MIT | https://dati.mit.gov.it/catalog/dataset/ | CKAN open data |
| OpenCoesione | https://opencoesione.gov.it/it/opendata/dataset/progetti_esteso_fsc_2021-2027/ | dataset ufficiale |
| SINAB | https://sinab.it/bionovita/ | pubblicazioni sul biologico |
| SNAM | https://www.snam.it/it/documenti.html | report, bilanci, dati XLSX |

## Regole future

1. I file di input su GitHub non sono automaticamente nuovi dati nell'APK Android: occorre aggiornare il job di produzione delle PUBBLICAZIONI e l'archivio completo.
2. Un 403, 429 o un problema TLS viene riportato, non eluso disattivando la verifica dei certificati.
3. Un dataset individuato non è una pubblicazione del giorno: si utilizza solo la data espressamente associata al record.
4. Non convertire PDF o pagine istituzionali in `primary_statistical_source` senza verifica delle serie.
5. Non modificare `main` né automatismi senza autorizzazione; nessun nuovo workflow viene avviato in questa fase, anche per non consumare minuti GitHub Actions.
