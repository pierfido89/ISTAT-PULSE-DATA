# PULSE — Research Engine → ChatGPT → Fact Checker → Android (2026-10-11)

**Stato:** laboratorio verificato per sei pubblicazioni ufficiali. Nessuna API OpenAI a pagamento; nessun Qwen; nessuna pubblicazione automatica.

## Ricerca automatizzata, non inventata

Il workflow `.github/workflows/research-chatgpt-evidence-daily.yml` è installato sul branch `main` **solo come schedulatore**, ma preleva il codice e salva i risultati **esclusivamente** nel branch `feat/pulse-editorial-ai-1.0`. L'esperimento su push di branch è già riuscito.

Il programma `scripts/pulse_research_chatgpt_packet.py` esige il controllo integrale del test di accettazione sui sei PDF di fonte ISTAT. Il pacchetto JSON canonico è `data/research/chatgpt_evidence_packet.json`: 6 PDF, 91 pagine, 70 osservazioni, 16 storie, 34 fatti collegati a indicatori, popolazioni, periodi, URL, SHA-256 e pagina/riga.

**Limite:** i sei adattatori esaminano sei documenti specifici, anche storici; questo NON equivale a un sistema universale che incorpora ogni nuova pubblicazione non supportata. Per un nuovo documento occorrono parsing, prova di accettazione, aggiornamento del catalogo e nuova revisione.

## Collegamento ChatGPT con il piano personale

L'attività ChatGPT `PULSE — Redazione documentata ChatGPT` legge il file GitHub verificato e, se trova una storia nuova rispetto al repository privato `pierfido89/ISTAT-PULSE-EDITORIAL-RESULTS`, può produrre fino a due bozze. Il format `pulse-chatgpt-research-draft-v2` impone lo `story_id` e una `claim_ledger` per ogni frase del titolo e di tutti i paragrafi, con gli `evidence_id` atomici della stessa storia.

L'esecuzione programmata dipende da autorizzazioni/limiti di ChatGPT e non è un'API server permanente. La prima esecuzione automatica del nuovo protocollo va ancora verificata; un pilota manuale end-to-end è presente su GitHub.

## Fact Checker indipendente dalle generazioni AI

Il repository privato contiene `checks/pulse_fact_checker.py`, test di regressione e un workflow GitHub Actions. Per ogni frase controlla:
- identità della frase e della citazione rispetto al claim ledger;
- copertura degli identificativi di evidenza e appartenenza alla stessa storia;
- valori numerici rispetto ai fatti citati, incluso il corretto indicatore (NIC/IPCA/FOI);
- segno e direzione delle variazioni quando specificati;
- espressioni causali o previsioni non giustificate dalla tabella;
- metadati di quarantena (published=false, auto_publish=false, revisione umana obbligatoria).

Per il pilota prezzi: 7/7 frasi abbinate, 0 blocchi nell'ultima verifica. Rapporto privato `checks/reports/research-chatgpt-pilot-20261011.audit.json`.

**Limite epistemico inderogabile:** un programma deterministico non può certificare integralmente la verità semantica di qualsiasi proposizione italiana. Ogni frase ha il warning `semantic_truth_requires_human_source_review`, anche se lo stato tecnico è verde. Una fonte non verificata o una nuova interpretazione richiede controllo umano con PDF originale.

## Collegamento Android

Il branch `pulse-rebrand-2026` dell'app contiene `PulseEditorialBridge.kt` e il tab `Articoli` in Notizie. Il lettore usa il JSON HTTPS `data/editorial/approved_articles.json` sul branch dati sperimentale, che per scelta è vuoto. Un gate offline richiede approvazione umana espressa e vincolo SHA-256 dell'esatta bozza; ChatGPT e la CI non possono autorizzare da soli una pubblicazione.

La CI `verify-editorial-android-e2e.yml` costruisce un APK solo per il test e prova codice Kotlin, Robolectric, navigazione, PDF Android nativo e tab Articoli su emulatore. Non modifica l'APK installato, non crea release e non carica artifact GitHub, che hanno storage esaurito. Prima di qualunque rilascio vedere l'esito verde **dell'esecuzione più recente**, non soltanto i test statici.

## Regola di prodotto

La correttezza delle cifre ufficiali viene prima della qualità stilistica; l'aiuto ChatGPT non trasforma automaticamente l'articolo in un segnale statistico né gli assegna un PULSE Score. PULSE è un prodotto indipendente; ISTAT resta citata come fonte, non come editore.
