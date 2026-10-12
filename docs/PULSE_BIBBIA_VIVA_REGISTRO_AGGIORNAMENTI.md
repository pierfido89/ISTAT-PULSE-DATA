# PULSE — Registro permanente degli aggiornamenti della Bibbia tecnica

**Documentazione viva:** tutte le modifiche devono essere registrate nel dossier originale e qui, senza sostituire pagine con riepiloghi superficiali. Il file PDF master aggiornato viene consegnato al progettista dopo ogni problema trattato.

## Base immutabile di riferimento
- **PULSE Bibbia Tecnica v4.3.6**, edizione 11 ottobre 2026, 114 pagine originali.
- Android congelato a v4.3.6, codice verificato sul tag b4dbdfb8611a2542481b04ccd668cf54335a7fcf.
- Ideazione e progettazione: Ludovico Fiori; sviluppo e documentazione con ChatGPT.
- Prototipo indipendente: non attribuire patrocini ISTAT.
- Non confondere stato implementato, operativo allo snapshot, parziale e roadmap.

## 12 ottobre 2026 — Problema 12: rettifiche, ritiro, rollback, operatori, cache
**Allegato integrato nel PDF:** W.00–W.16, ulteriori **17 pagine**. Master risultante: **131 pagine** conservando tutte le 114 pagine originarie.

**Problema:** assenza di un ciclo completo e verificabile per rettificare, ritirare e ripristinare contenuti editoriali PULSE, senza cancellare la storia.

**Soluzione architetturale:**
1. Ledger privato append-only logico con revisioni, motivazioni, hash degli eventi, tombstone e unsafe_versions.
2. Esportazione di una generazione immutable con indice/pagine/lifecycle e avanzamento monotono del puntatore.
3. Preparazione release remota verificando SHA e identità GitHub autenticata, in modalità amministratore unico pierfido89 con conferma manuale e commit esatto. Nessuna falsa seconda revisione.
4. Android fail-closed per i soli articoli opt-in lifecycle_managed, verifica ogni 30 secondi, timeout attestazione 45 secondi, blocco versioni ritirate, vecchie o sconosciute.
5. Conservazione del file ufficiale originale quando viene ritirata soltanto l'interpretazione PULSE.

**Test tecnici:** 18 lifecycle + 9 remote delivery + 14 compatibilità = **41/41** nel workflow GitHub Actions 38229021236; **4 test Android e compilazione Kotlin** nel workflow 38227410169, senza APK.

**Codice e pull request:**
- DATA [#14](https://github.com/pierfido89/ISTAT-PULSE-DATA/pull/14), script lifecycle, validatore release remota, workflow, test e runbook.
- Android [#36](https://github.com/pierfido89/ISTAT-PULSE/pull/36), lifecycle manager, UI filtro revoche, test JVM.
- Editorial results privato [#2](https://github.com/pierfido89/ISTAT-PULSE-EDITORIAL-RESULTS/pull/2), ledger privato inizialmente vuoto.
- Endpoint di anteprima: https://raw.githubusercontent.com/pierfido89/ISTAT-PULSE-DATA/pulse-editorial-lifecycle-preview/data/editorial/lifecycle/current.json (generazione 0, zero articoli).

**Stato corretto:** implementato e testato nei rami di sviluppo; endpoint di anteprima pubblico e vuoto. **Non ancora operativo in produzione.** Per attivare occorrono GitHub Environment protetto con second reviewer, secret read-only per il repository privato, revisione PR, merge esplicito e prove end-to-end di rete/Android/cache. La distribuzione GitHub Raw non garantisce invalidazione CDN istantanea; un dispositivo offline non può ricevere un ritiro nell'istante in cui viene eseguito.

**Vincolo assoluto:** non effettuare un merge per il solo fatto che un test è verde; nessuna nuova APK senza richiesta esplicita e collaudo.

## Metodo obbligatorio per i prossimi problemi
Ogni nuovo problema richiede: rischio iniziale; soluzione progettata e implementata; codici, rami e commit; dati originali e schema; test e prove eseguite; limiti residui; modifiche alle schede e alla cache; criteri di rollout/rollback; aggiornamento effettivo del master PDF con preservazione della versione storica.

Regola editoriale permanente: **Un errore si corregge, ma la storia delle correzioni non si cancella mai.**

## 12 ottobre 2026 — Decisione proprietario unico, completamento tecnico della priorità 12

- Account operativo autorizzato: **pierfido89**. Nessun secondo account richiesto nel prototipo; eventuale controllo indipendente è un upgrade futuro.
- Rilascio ordinario controllato: PR privata con HEAD e autore verificati tramite GitHub, conferma manuale `PUBBLICA-ANTEPRIMA` e pubblicazione solo sul ramo preview.
- Ritiro d'emergenza: workflow distinto, ID/motivazione/conferma `RITIRA-ARTICOLO`, ledger privato prima del ramo preview, ripetizione idempotente quando il push remoto non riesce. Nessun blocco in attesa di un revisore esterno.
- Ripristino: `single_owner_self_review` registrato apertamente; nessuna versione unsafe ripubblicabile.
- Prove: 18 test ledger + 9 release/emergenza + 14 compatibilità + 4 Android = **45 test**, tutti superati. CI DATA https://github.com/pierfido89/ISTAT-PULSE-DATA/actions/runs/38229021236; CI Android https://github.com/pierfido89/ISTAT-PULSE/actions/runs/38227410169.
- Documento PDF definitivo di lavoro: `PULSE_Bibbia_Tecnica_v4.3.6_Problema12_Governance_Proprietario_Unico_2026-10-12.pdf`; **131 pagine**, con 114 pagine storiche conservate e 17 pagine dell'Allegato W.
- Nessuna attivazione produttiva, nessuna APK, nessuna news pubblicata. Necessaria configurazione GitHub da parte dell'owner e prova live su dispositivo prima di etichettare il sistema OPERATIVO.

## 12 ottobre 2026 — Problema 11: distintivo NEW 180 minuti

- **Problema:** badge NEW mancante nella UI; rischio false novità da cache, articoli d'archivio e timestamp della fonte.
- **Soluzione dati:** nuovo `first_published_at_utc` registrato solo al primo ingresso di nuova notizia PULSE, se data originale RSS con timezone e non precedente oltre 24 ore; conservato senza reset ad ogni refresh. Le vecchie notizie senza primo timestamp restano prive del badge.
- **Soluzione Android:** pill rossa `NEW` nelle notizie Radar, quattro card Home, dettagli e Preferiti; calcolo stretto `0 <= delta < 180 minuti`; timer UI ogni 15 secondi. Nessun badge per gli `ObserverArticle` storici.
- **Codice DATA:** `scripts/pulse_new_badge.py`, `scripts/update_news_radar.py`, `tests/test_pulse_new_badge.py`.
- **Codice Android:** `PulseNewBadge.kt`, `PulseModels.kt`, `PulseHome.kt`, `PulseApp.kt`, `PulseNewBadgeTest.kt`.
- **Test eseguiti:** 12 test Python e 6 test Kotlin tutti verdi; compilazione Kotlin superata. CI DATA https://github.com/pierfido89/ISTAT-PULSE-DATA/actions/runs/38231088547 ; CI Android https://github.com/pierfido89/ISTAT-PULSE/actions/runs/38231083331 . Nessun APK, feed pubblico o app main modificati.
- **Dossier PDF master:** `PULSE_Bibbia_Tecnica_v4.3.6_Problemi_12_11_NEW_2026-10-12.pdf`, 135 pagine. 131 pagine precedenti preservate senza modifiche ai flussi di contenuto e 4 nuove pagine Allegato X.
- **Stato:** implementato e testato sui rami dedicati; non ancora distribuito alla release stabile installata. L'avvio produttivo segue la fase di integrazione controllata.
- **Codice in revisione:** PR DATA [#15](https://github.com/pierfido89/ISTAT-PULSE-DATA/pull/15); PR Android [#37](https://github.com/pierfido89/ISTAT-PULSE/pull/37), entrambe in bozza e non integrate nel ramo principale.
- **Specifiche approfondite:** `docs/PULSE_PROBLEMA_11_NEW_BADGE_180_MINUTI.md`.

## 12 ottobre 2026 — Problema 10: vere push Firebase Cloud Messaging

- **Difetto:** WorkManager ogni 2 ore: polling lato telefono, non push.
- **Risoluzione:** backend FCM HTTP v1 avviato dal workflow di aggiornamento Radar, client Android FirebaseMessagingService data-only e disattivazione del polling legacy.
- **Utenti e consenso:** OFF di default, nessuna migrazione automatica del consenso vecchio, Firebase Auth anonima, permesso POST_NOTIFICATIONS quando necessario, revoca locale immediata e richiesta cancellazione token/Firestore.
- **Filtri:** topic, PULSE Score minimo, ITALIA/REGIONE/PROVINCIA/COMUNE con codici ISTAT e scelta esplicita delle news nazionali; non interpretare titoli liberi come coordinate geografiche. Precisione provinciale/comunale limitata a feed con metadati codice.
- **Dedup:** ricevuta backend hash(uid,id) con lease Firestore, più idempotenza sul telefono. Firestore TTL expires_at 30 giorni da abilitare manualmente.
- **Privacy:** Firestore rules per UID, niente GPS e niente chiavi amministrative in app; informativa e verifica GDPR prima del rilascio pubblico.
- **Particolarità GitHub risolta:** il GITHUB_TOKEN con cui il Radar aggiorna main non lancia un altro workflow su push; FCM è invocato direttamente nello stesso refresh-news-radar.yml dopo il push.
- **Prove tecniche:** 16 test backend e 11 Android; compilazione Kotlin verde; link CI DATA https://github.com/pierfido89/ISTAT-PULSE-DATA/actions/runs/38234962274 e Android https://github.com/pierfido89/ISTAT-PULSE/actions/runs/38234984362 . Zero APK, zero messaggi veri, zero servizi a pagamento attivati.
- **Bibbia master:** PULSE_Bibbia_Tecnica_v4.3.6_Problemi_12_11_10_PUSH_FCM_2026-10-12.pdf; 142 pagine. 135 pagine precedenti preservate e Allegato Y di 7 pagine; compatibile con gli Allegati W e X.
- **Limite esterno dichiarato:** il progetto Firebase e le credenziali proprietario non esistono nel repo; senza configurazione FCM non può inviare. Per dichiarare il problema CHIUSO OPERATIVO serve prova su telefono dopo collegamento Firebase. Le quattro finestre giornaliere di raccolta Radar restano in vigore.
- **Dettaglio:** docs/PULSE_PROBLEMA_10_PUSH_FCM_E_PRIVACY.md.

- **Pull request problema 10:** DATA https://github.com/pierfido89/ISTAT-PULSE-DATA/pull/16 e Android https://github.com/pierfido89/ISTAT-PULSE/pull/38, in bozza verso i rami che già contengono i problemi 11 e 12. I 135 fogli originali e aggiornamenti precedenti della Bibbia master rimangono preservati nel PDF 142 pagine.

## 12 ottobre 2026 — Addendum AA: Notizie in tre sottoschede e sticky PULSE compatto

- **Decisione:** eliminata la sottoscheda Home duplicata. NOTIZIE presenta solo Oggi / Ieri / Archivio. L'eventuale stato salvato Home viene ricondotto a Oggi.
- **Oggi:** PULSE LIVE, quattro evidenze esclusive selezionate da pulseSelectTodayHighlights, elenco delle ulteriori notizie con esclusione degli ID gia' in evidenza (nessuna card ripetuta).
- **Ieri:** PULSE LIVE riferito alla giornata precedente e rispettivo elenco; **Archivio** isolato dalla giornata attiva.
- **Sticky per ogni scheda:** componente condiviso PulseStickyByline per BY e logo PULSE; originale approvato invariato, generazione della sola derivazione senza margini trasparenti, spaziatura 1 dp.
- **Collaudi:** nuovi unit test sulla scelta delle quattro evidenze e feed corti, aggiornati test Android di navigazione e UI di condivisione, QA di build per marchio e rimozione Home. La verifica strumentale su emulatore va valutata separatamente.
- **Branch:** https://github.com/pierfido89/ISTAT-PULSE/tree/fix/pulse-p9-ui-regression-full-qa-20261012 ; PR https://github.com/pierfido89/ISTAT-PULSE/pull/39 . Main invariato e nessuna nuova APK richiesta.
- **Master PDF Bibbia:** PULSE_Bibbia_Tecnica_v4.3.6_Aggiornamento_Notizie_Sticky_2026-10-12.pdf, 148 pagine: tutte le 146 precedenti preservate e due nuove pagine di Allegato AA, che prevale sull'assetto Home/Oggi del precedente Allegato Z.
