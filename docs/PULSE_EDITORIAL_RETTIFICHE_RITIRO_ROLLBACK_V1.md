# PULSE Editorial — Rettifiche, ritiri e rollback (fase backend isolata)

**Versione sperimentale:** 1.0 · 12 ottobre 2026  
**Ramo:** feat/pulse-editorial-revisions-withdraw-rollback-20261012  
**Stato:** implementazione OFFLINE collaudata; **non** attivata su feed pubblico, app Android o infrastruttura remota. Non è autorizzazione all'autopubblicazione.

## 1. Cosa funziona nel prototipo

Il motore scripts/pulse_editorial_lifecycle.py conserva una storia di eventi, una sequenza monotona di revisioni per articolo e un archivio paginato V2 compatibile con il preesistente scripts/pulse_editorial_archive_v2.py.

Un articolo ha **identificativo permanente**, prima pubblicazione UTC, stato ACTIVE o WITHDRAWN, numero della revisione corrente e tutta la storia delle revisioni originali. Ogni revisione conserva il testo approvato, la sua impronta SHA-256, la motivazione e un riferimento all'evento di creazione.

Ogni mutazione genera un **evento append-only** con numero progressivo, data/ora UTC, operatore dichiarato, articolo, revisione, motivazione, hash della proiezione e collegamento hash all'evento precedente. Il registro è sostituito in modo atomico, con fsync, lock esclusivo e possibilità di rifiutare aggiornamenti basati su una generazione ormai superata.

Un **ritiro d'emergenza** porta l'articolo a WITHDRAWN, crea una tombstone pubblicabile con motivo e ora del ritiro, esclude il corpo dall'archivio corrente e marca non sicura la versione ritirata. Nessuna vecchia versione viene cancellata dal ledger protetto, così le prove restano disponibili per audit. I ritiri duplicati sono respinti.

Una **rettifica** crea una nuova versione senza sovrascrivere la precedente, registra la motivazione e richiede una nuova scheda già approvata da un revisore umano. Se il testo precedente contiene dati scorretti, l'opzione --invalidate-previous lo marca non sicuro e impedisce un successivo ripristino di quella versione.

Un **rollback** richiede target di versione esistente, nuova conferma operativa, un operatore umano identificato e motivazione. Non sposta indietro il contatore delle versioni: crea invece una **nuova versione** che copia i contenuti della vecchia versione sicura, salvando restored_from_version. Non consente mai il recupero di una versione esplicitamente marcata come unsafe.

## 2. Esportazione e contratto dati per il lettore

L'esportazione offline produce:
- snapshots/generation_XXXXXXXXXX/index.json — manifest dell'archivio e riferimenti alle pagine;
- snapshots/generation_XXXXXXXXXX/pages/page_XXXXX.json — pagine contenenti SOLO versioni ACTIVE;
- snapshots/generation_XXXXXXXXXX/lifecycle.json — revisioni e stati, con tombstone e motivazioni (non i testi ritirati);
- current.json — puntatore atomico all'ultima generazione verificata, scritto per **ultimo**.

Le pagine e il manifest sono controllati tramite SHA-256, anche quando vengono riutilizzati. Una generazione precedente non può sostituire il puntatore corrente. Le cartelle di generazione precedenti restano disponibili per audit ma **non devono poter essere usate come sorgente attiva senza nuova verifica lifecycle**.

Una **rettifica** deve far sostituire, non duplicare, l'articolo negli elenchi, nei preferiti e nelle condivisioni, mantenendo lo stesso ID e mostrando la nuova versione e la nota di modifica.

Un **ritiro** deve impedire il rendering del vecchio corpo, annullare la cache degli articoli e dei PDF PULSE ritirati, togliere il contenuto da ricerche e preferiti, invalidare eventuali schede già aperte e mostrare una pagina di cortesia con motivo e data del ritiro. Non cancellare automaticamente l'eventuale PDF originale dell'ente fonte (non è di PULSE).

**Regola forte:** prima di mostrare testi PULSE salvati localmente, il client deve verificare una lifecycle generation aggiornata; in assenza di rete, i contenuti editoriali che potrebbero essere stati ritirati vanno nascosti o chiaramente resi non disponibili, non serviti come se fossero verificati.

Il server / CDN dovrà consegnare current.json e lifecycle con Cache-Control: no-store, ETag o equivalente e controlli periodici; il backend dovrà essere in grado di effettuare un push di invalidazione delle cache. Il prototipo non dispone ancora di questa infrastruttura.

## 3. Procedure operative (solo laboratorio)

Le seguenti righe sono **esempi di CLI**, non una pubblicazione. Usare una directory di test e un file JSON contenente **un singolo** articolo già revisionato nel formato approved-v1; non utilizzare una bozza ChatGPT.

### Creare archivio vuoto

    python -m scripts.pulse_editorial_lifecycle init --ledger /tmp/pulse-secure/ledger.json

### Prima registrazione approvata

    python -m scripts.pulse_editorial_lifecycle register --ledger /tmp/pulse-secure/ledger.json --article /tmp/approved-item.json --actor "Responsabile editoriale" --reason "Prima registrazione dopo revisione delle evidenze" --output-dir /tmp/pulse-export

### Rettificare contenuto con errore statistico

    python -m scripts.pulse_editorial_lifecycle rectify --ledger /tmp/pulse-secure/ledger.json --article /tmp/reapproved-item.json --actor "Responsabile editoriale" --reason "Rettifica del valore alla luce del documento ufficiale" --invalidate-previous --output-dir /tmp/pulse-export

### Ritiro di emergenza (una sola operazione per ledger + puntatore locale)

    python -m scripts.pulse_editorial_lifecycle withdraw --ledger /tmp/pulse-secure/ledger.json --id PULSE-TEST-001 --actor "Responsabile editoriale" --reason "Fonte ritirata: sospensione cautelativa dell'articolo" --confirm-withdraw --output-dir /tmp/pulse-export

### Ripristinare una versione SICURA con nuova revisione

    python -m scripts.pulse_editorial_lifecycle rollback --ledger /tmp/pulse-secure/ledger.json --id PULSE-TEST-001 --target-version 1 --actor "Responsabile editoriale" --reviewed-by "Responsabile editoriale" --reason "Ripristino verificato della versione originale, fonte riconfermata" --confirm-safe-target --output-dir /tmp/pulse-export

### Controllare integrità della cronologia

    python -m scripts.pulse_editorial_lifecycle verify --ledger /tmp/pulse-secure/ledger.json

Le operazioni non inviano richieste a GitHub, CDN, app, OpenAI o Firebase. Un errore nell'esportazione dopo il ritiro **non annulla** l'evento di ritiro salvato nel ledger: il comando termina con errore e richiede l'intervento sull'esportazione/puntatore. Non deve essere scambiato per un ritiro già propagato ai telefoni.

## 4. Sicurezza e limiti espliciti

- **Test di sicurezza**: rifiuto di bozze non autorizzate, hash degli eventi, individuazione manomissioni accidentali, lock di scrittura, controllo generation, ritiro in archivio vuoto, blocco rollback unsafe, paginazione oltre 40 articoli, importo e provenienza dei dati preapprovati.
- **Autenticazione ancora assente**: actor e reviewed_by sono etichette audit, **non** identità crittograficamente provate. Prima del rilascio remoto servono ruoli server-side e autenticazione forte, per la fase sperimentale, un solo proprietario autenticato GitHub e audit esplicito 'single_owner_self_review'; una seconda revisione umana potrà essere introdotta nella fase istituzionale.
- **Non è una prova antimanomissione assoluta**: chi può riscrivere l'intero ledger può ricalcolare la catena hash. Per garanzia forte occorre ancorare hash e eventi su una piattaforma append-only protetta o con firma digitale.
- **Non è rollback remoto immediato**: il prototipo aggiorna un puntatore locale in modo atomico. Distribuzione CDN, invalidazione delle cache, osservabilità, failover e versione Android compatibile non sono ancora integrate.
- **Offline non garantibile**: un dispositivo scollegato non può essere aggiornato nell'istante di ritiro. Le versioni PULSE che adotteranno questo contratto dovranno progettare una politica fail-closed per contenuti non riconvalidati.
- **Gate editoriale invariato**: questa funzione non può trasformare bozze non approvate in articoli pubblicati né sostituire il Fact Checker.

## 5. Test e criteri per andare in produzione

Test automatici: tests/test_pulse_editorial_lifecycle.py, integrati ai test originali archive-v2 e publication-gate. GitHub Actions usa permissions contents: read, niente API a pagamento né distribuzione. La prova dell'esito corrente è nel workflow branch-only di GitHub.

Per dichiarare **definitivamente risolto il problema 12 in produzione** mancano: API di esercizio autenticata, persistenza remota transazionale e append-only, integrazione del puntatore nel feed reale, aggiornamento della app Android per lifecycle e cache, verifica della latenza di revoca end-to-end online/offline, e runbook di emergenza con monitoraggio ed esercitazioni. Eseguire test su più di un dispositivo e un rollback reale non distruttivo in staging.

**Conclusione:** realizzato e testato il motore indipendente del ciclo di vita. Il sistema LIVE non è ancora stato attivato e non viene dichiarato protetto finché backend remoto e client non sono connessi.


## 6. DECISIONE DEL PROGETTISTA — OPERATORE UNICO (12 ottobre 2026)

La decisione vigente è utilizzare **esclusivamente l'account GitHub autenticato pierfido89** come responsabile, senza richiedere un secondo account nel prototipo. Questo **sostituisce** le istruzioni che prevedevano una review indipendente obbligatoria per il rilascio sperimentale.

- **Rettifiche e rilascio ordinario in PREVIEW:** PR privata non in bozza con commit esatto; avvio manuale owner-only; digitazione della conferma PUBBLICA-ANTEPRIMA; l'identità deriva da GitHub Actions github.actor e dall'autore della PR, non da un campo JSON.
- **Ritiro d'emergenza PREVIEW:** workflow manuale owner-only; ID articolo, motivazione pubblica (almeno 12 caratteri) e conferma RITIRA-ARTICOLO. **Nessuna attesa di revisore**: il ledger privato riceve l'evento di ritiro, viene generata una tombstone e il nuovo snapshot viene inviato al ramo di prova.
- **Rollback:** occorre il controllo versione precedente sicura, motivazione e conferma. Nel registro l'evento indica single_owner_self_review se operatore e revisore sono la stessa persona; mai dichiarare una revisione indipendente inesistente.
- **Persistenza dell'incidente:** il workflow di emergenza scrive **prima** il ledger privato e **poi** la versione remota. Se il secondo push fallisce, un successivo avvio del comando riprende senza alterare lo stato già ritirato. Non dichiarare completata la propagazione prima della verifica remota.
- **Sicurezza:** le vecchie versioni unsafe non possono essere ripubblicate con rollback; ogni evento resta nella catena hash. Solo gli articoli redatti da PULSE con editorial_lifecycle_managed=true sono sottoposti alle regole Android.
- **Distinzione di modalità:** independent_review resta disponibile nel codice come possibile upgrade futuro, ma il percorso operativo desiderato attualmente è single_owner_manual / single_owner_emergency.

### Codice dei due comandi GitHub

- .github/workflows/pulse-editorial-controlled-remote-preview.yml — rilascio ordinario solo da main, account pierfido89, secret PULSE_PRIVATE_READ_TOKEN con **sola lettura** repository privato.
- .github/workflows/pulse-editorial-owner-emergency-withdraw.yml — ritiro d'emergenza solo da main, account pierfido89, secret PULSE_PRIVATE_WRITE_TOKEN con permesso Contents Read/Write **solo** sul repository EDITORIAL-RESULTS.
- In entrambi i casi è necessario consentire al github.token del repository DATA la scrittura **solo** sul ramo di anteprima; il ramo main e i repository Android non sono destinazioni del deploy.
- Ambiente GitHub: pulse-editorial-preview. Nel modello ad amministratore unico **non** è prevista la configurazione di un altro utente come revisore obbligatorio. Mantenere protetto l'accesso all'account con passkey/2FA e verificare le autorizzazioni dei token.

**Queste configurazioni non sono state create automaticamente**. I workflow sono in un ramo di sviluppo e diventeranno accessibili tramite Actions dopo l'integrazione autorizzata nel ramo default del repository DATA. Non usarli sul ramo principale senza prima verificare le protezioni e il comportamento sul ramo di prova.

### Differenza fra completamento tecnico e servizio realmente attivo

Tutte le procedure backend e i controlli Android interessati sono realizzati e collaudati a livello unitario. Non è ancora attestato un ritiro effettivo verificato su dispositivo installato dopo un push remoto: mancano le credenziali owner, il rollout controllato e le prove di latenza/cache GitHub Raw. La release v4.3.6 e i file di notizie attuali non sono stati modificati. Non si promettono rollback istantanei su telefoni offline o copie PDF già condivise.

**Regola vincolante: un errore si corregge, ma la storia delle correzioni non si cancella mai.**
