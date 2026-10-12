# PULSE — Registro permanente degli aggiornamenti della Bibbia tecnica

**Documentazione viva:** tutte le modifiche devono essere registrate nel dossier originale e qui, senza sostituire pagine con riepiloghi superficiali. Il file PDF master aggiornato viene consegnato al progettista dopo ogni problema trattato.

## Base immutabile di riferimento
- **PULSE Bibbia Tecnica v4.3.6**, edizione 11 ottobre 2026, 114 pagine originali.
- Android congelato a v4.3.6, codice verificato sul tag b4dbdfb8611a2542481b04ccd668cf54335a7fcf.
- Ideazione e progettazione: Ludovico Fiori; sviluppo e documentazione con ChatGPT.
- Prototipo indipendente: non attribuire patrocini ISTAT.
- Non confondere stato implementato, operativo allo snapshot, parziale e roadmap.

## 12 ottobre 2026 — Problema 12: rettifiche, ritiro, rollback, operatori, cache
**Allegato integrato nel PDF:** W.00–W.15, ulteriori **16 pagine**. Master risultante: **130 pagine** conservando tutte le 114 pagine originarie.

**Problema:** assenza di un ciclo completo e verificabile per rettificare, ritirare e ripristinare contenuti editoriali PULSE, senza cancellare la storia.

**Soluzione architetturale:**
1. Ledger privato append-only logico con revisioni, motivazioni, hash degli eventi, tombstone e unsafe_versions.
2. Esportazione di una generazione immutable con indice/pagine/lifecycle e avanzamento monotono del puntatore.
3. Preparazione release remota verificando SHA e identità GitHub autenticata; seconda review APPROVED su commit esatto.
4. Android fail-closed per i soli articoli opt-in lifecycle_managed, verifica ogni 30 secondi, timeout attestazione 45 secondi, blocco versioni ritirate, vecchie o sconosciute.
5. Conservazione del file ufficiale originale quando viene ritirata soltanto l'interpretazione PULSE.

**Test tecnici:** 17 lifecycle + 6 remote delivery + 14 compatibilità = **37/37** nel workflow GitHub Actions 38225557008; **4 test Android e compilazione Kotlin** nel workflow 38225631224, senza APK.

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
