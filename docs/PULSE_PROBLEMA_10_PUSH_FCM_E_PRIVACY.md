# PULSE — Problema 10: vere push FCM, consenso, territori e deduplica

Data: 12 ottobre 2026. Stato: software sviluppato e testato in rami sperimentali, NON attivato su telefoni o Firebase produttivo.

## 1. Difetto originale e soluzione

Prima: PulseNewsAlerts.kt utilizzava WorkManager con un controllo del feed ogni due ore. Non era una vera notifica push, e Android poteva rinviare il controllo.

Adesso: Firebase Cloud Messaging (FCM HTTP v1) riceve il comando dal backend dopo la pubblicazione del feed Radar e trasporta messaggi data-only. PulseFcmService.kt riceve il messaggio e mostra la notifica senza interrogare ogni due ore il feed. All'avvio della nuova versione si cancella il vecchio job pulse_news_radar_periodic; il consenso del vecchio poller NON viene automaticamente trasferito a FCM.

## 2. Componenti e costi

- Firebase Cloud Messaging HTTP v1: sistema push remoto, invio senza costo per messaggio.
- Firebase Authentication anonima: UID dell'installazione senza nome, account personale, telefono, email o GPS.
- Cloud Firestore: documenti push_subscriptions/UID contenenti solo token FCM, versione/data del consenso e preferenze topic, PULSE Score e territorio; push_delivery_receipts/hash(UID,articleId) per dedup.
- GitHub Actions: scripts/pulse_push_dispatch.py, server-only, legge Firestore e invia con Firebase Admin SDK usando un segreto GitHub Actions (mai nella APK).
- Android: PulsePushRegistration.kt registra, modifica e revoca consenso; PulseNotificationsSettings.kt visualizza preferenze; PulseFcmService.kt verifica di nuovo il consenso e la dedup locale prima di mostrare una notifica.

Piano Firebase consigliato: Spark con limiti gratuiti e nessuna fatturazione attiva. FCM è no-cost; Firestore/Auth hanno quote gratuite da monitorare. Nessuna API AI a pagamento.

## 3. Evento di pubblicazione e trigger GitHub corretto

Il News Radar viene aggiornato in quattro finestre giornaliere (06, 11, 16 e 22 ora di Roma, in base al workflow esistente), salvo lancio manuale. Quando aggiorna data/news/articles.json, il workflow refresh-news-radar.yml fa il commit e subito dopo chiama il dispatcher FCM.

**Vincolo tecnico risolto:** un commit creato con il GITHUB_TOKEN standard NON avvia automaticamente un altro workflow GitHub Actions. La dispatch viene perciò eseguita nello stesso workflow che ha pubblicato il feed. Il separato pulse-real-push-fcm.yml resta utilizzabile per push manuali o da un attore normale.

Questo trasforma il metodo di CONSEGNA in push reale, ma NON anticipa la scoperta delle notizie prima del prossimo aggiornamento Radar. Non promettere notifiche istantanee dall'ora di pubblicazione dell'ente fonte.

## 4. Filtri territoriali tipizzati

Profilo per dispositivo: territory.level = ITALIA, REGIONE, PROVINCIA o COMUNE; territory.code rispettivamente vuoto, codice ISTAT 2 cifre, 3 cifre o 6 cifre. Include_national è una scelta separata.

Il backend accetta geografia articolo push_geo con codice esplicito oppure SOLO una regione riconosciuta esattamente dall'elenco delle regioni ISTAT o il valore unico ITALIA. Non desume comuni o province da un testo libero. Se mancano i codici geografici, il matching ristretto non può effettuarsi; non invia notifiche territorialmente false.

COPERTURA ATTUALE: le sorgenti News Radar sono prevalentemente Italia o regioni; per rendere pienamente fruibili i filtri provinciali e comunali occorre associare alle singole notizie gli effettivi codici ISTAT. L'interfaccia accetta già i codici ma non implica dati geografici che non esistono.

## 5. Consenso e protezione dei dati

L'utente deve aderire esplicitamente da Impostazioni: consenso versione pulse-push-consent-v1, timestamp UTC, permission Android POST_NOTIFICATIONS quando necessaria. La configurazione di default è OFF anche per chi usava le notifiche periodiche. La stessa schermata permette argomenti, PULSE Score minimo, territorio e scelta se ricevere le notizie nazionali.

L'adesione registra token FCM e preferenze nel documento Firestore accessibile solo al proprietario autenticato anonimo con le regole firebase/firestore.rules. Nessun GPS. Nessuna retroattività: non si inviano notizie pubblicate prima del consenso.

Alla revoca, push_opted_in diventa subito FALSE, il client disabilita l'auto-inizializzazione FCM, chiede di cancellare il token e il proprio documento Firestore. Se una push è già in viaggio, il telefono ricontrolla consenso e impostazioni e non la mostra. La cancellazione remota può attendere il ritorno della rete.

Le ricevute nel backend usano chiavi hash non reversibili direttamente e un campo expires_at a 30 giorni. **Prima dell'attivazione configurare TTL Firestore su expires_at**, assicurare informativa privacy visibile e verifica applicabile GDPR.

## 6. Deduplicazione

Il backend applica un lease transazionale per coppia UID + articolo, registra il risultato del tentativo e non reinvia lo stesso articolo già marcato SENT. Una perdita di processo fra consegna FCM e salvataggio esito può produrre un retry: PulseFcmService blocca ulteriori avvisi locali dello stesso article_id memorizzato tra gli ultimi 400 IDs.

Un invio è ammesso solo per un articolo nuovo pubblicato PULSE, con validazione editoriale, data first_published_at_utc verificabile, identificativo valido, geografia strutturata, topic/score coerenti e consenso più vecchio dell'articolo. Non si usano ora di download, data PDF o ultimo crawl per ricreare notifiche.

Lato FCM e lato Android la finestra massima di visualizzazione è 180 minuti per evitare avvisi tardivi.

## 7. Configurazione esterna indispensabile (account unico)

1. L'account del proprietario crea un progetto Firebase nel piano Spark senza abilitare spese a consumo, registra l'app con package it.ludovicofiori.istatpulse e abilita Authentication anonima, Firestore e Cloud Messaging HTTP v1.
2. Applica in Firebase le rules versionate nel file firebase/firestore.rules. Abilita la TTL policy per push_delivery_receipts.expires_at e verifica quote e consensi.
3. Imposta i QUATTRO identificatori pubblici Android nel file Gradle locale o variabili di build: pulseFirebaseApiKey, pulseFirebaseAppId, pulseFirebaseProjectId e pulseFirebaseSenderId. I valori non sono credenziali amministrative; in assenza di configurazione l'interruttore push resta disabilitato.
4. Inserisce la credenziale del SERVICE ACCOUNT server nel segreto GitHub Actions DATA denominato PULSE_FIREBASE_SERVICE_ACCOUNT_JSON. Non caricare mai il file privato nel repository, nell'app o in questa chat.
5. Integra deliberatamente i rami e prepara una APK di prova soltanto quando richiesta dal proprietario. Applica la nuova versione a un dispositivo Android con Google Play Services.
6. Verifica su dispositivo: default OFF; opt-in e registrazione Firestore; ricezione per articolo realmente nuovo; nessun duplicato su seconda dispatch; topic, punteggio e regione corretti; opt-out e assenza di avvisi dopo la revoca; telefono senza rete e riavvio.
7. Solo dopo questi risultati lo stato diventa OPERATIVO. Il superamento dei test locali da solo non prova la consegna di una push remota.

## 8. Codice e test

DATA: scripts/pulse_push_dispatch.py; tests/test_pulse_push_dispatch.py; firebase/firestore.rules; .github/workflows/pulse-real-push-fcm.yml; modifica a .github/workflows/refresh-news-radar.yml; .github/workflows/pulse-push-security-tests.yml.

Android: PulsePushRegistration.kt, PulseFcmService.kt, PulseNotificationsSettings.kt, PulseNewsAlerts.kt, PulseApp.kt, AndroidManifest.xml, app/build.gradle.kts e PulseFcmPushTest.kt.

I test tecnici controllano consenso, geografia, dedup, news vecchie e canale Android; risultati ufficiali nelle run CI del ramo di sviluppo. **Senza progetto Firebase e dispositivo collegati resta una implementazione testata, non una consegna remota verificata.**

Compatibilità: il problema 11 usa il timestamp primo inserimento PULSE; il problema 12 oscura articoli ritirati. Nessuna push può aggirare una rettifica o una tombstone quando l'utente apre la news.

**Regola Bibbia viva: un errore si corregge, ma la storia delle correzioni non si cancella mai.**
