# ISTAT PULSE — Surface: collegamento editoriale controllato (11 ottobre 2026)

## Stato reale

Preparati e salvati su GitHub, **NON ancora installati sul Surface**:
- agente Python in allowlist: automation/pulse_local_agent.py
- richiesta remota disabilitata: automation/editorial_job.json
- esecuzione ricorrente: automation/run_scheduled.ps1
- uploader privato: automation/upload_results.ps1
- configurazione iniziale guidata: automation/setup_surface.ps1
- test di regressione e CI che controllano anche la sintassi PowerShell

**Repository Android ISTAT-PULSE: INALTERATO.** Branch dati sperimentale e PR #13
non devono essere uniti o pubblicati automaticamente.

## Prima configurazione — una sola sessione PowerShell, guidata

Dal PC già dotato di Git, Python, Ollama e workbench:
1. Aggiornare il branch sperimentale con git pull --ff-only (mai git reset --hard).
2. Eseguire una volta automation/setup_surface.ps1.
3. Il programma testa il collegamento esistente senza avviare Qwen.
4. Si apre il browser per creare **pierfido89/ISTAT-PULSE-EDITORIAL-RESULTS**
   come repository **PRIVATE** con README, ramo predefinito **main**.
5. Si apre GitHub per creare un **fine-grained personal access token**:
   - Resource owner: pierfido89
   - Repository access: **Only selected repositories**, selezionando SOLO
     ISTAT-PULSE-EDITORIAL-RESULTS
   - Repository permissions: **Contents: Read and write**, Metadata: Read
   - Nessuna autorizzazione su Actions, Administration, Workflows, Secrets o
     sugli altri repository
   - Scadenza limitata; rinnovo manuale alla scadenza
6. Incollare il token **esclusivamente** al prompt oscurato di PowerShell,
   MAI in chat, log, messaggi o commit.
7. L'installer verifica via GitHub API identità, riservatezza e ramo di
   destinazione. Se il controllo non passa, non registra alcun task.
8. Il token viene protetto in %LOCALAPPDATA% per l'utente Windows tramite
   DPAPI (ConvertFrom-SecureString). Non è un file in chiaro.
9. Windows Task Scheduler registra un task dell'utente corrente a permessi
   LIMITATI (non amministratore), eseguito ogni 30 minuti con sessione aperta.

**Non si installa alcun self-hosted runner GitHub sul Surface.** L'utente
può fermare il task in Utilità di pianificazione di Windows in qualsiasi momento.

## Ciclo automatico dopo il setup

1. Il task avvia SOLO il codice locale approvato.
2. Il programma legge l'unico JSON allowlisted da GitHub pubblico.
   Può scegliere esclusivamente job_id, start (0-5), limit (1-2) e enabled.
   Non può specificare comandi, nuovi script, repository o URL.
3. Fino a quando enabled=false: non esegue Qwen.
4. Quando enabled=true e il job_id non è stato elaborato, l'agente chiama
   Qwen3.5 9B **su 127.0.0.1** e produce esclusivamente bozze in quarantena
   nella cartella locale workbench/local-automation-outbox.
5. Un secondo passaggio verifica report, status, flag di revisione umana e
   SHA-256 degli articoli, poi trasferisce *solo questi due JSON* nel repo
   privato: runs/<job_id>/result.json e runs/<job_id>/report.json.
6. Il caricamento è idempotente: non sovrascrive mai un risultato esistente
   diverso. Se la rete non funziona, il programma conserva gli output locali
   e ritenta al prossimo avvio. L'agente non rilancia lo stesso job_id.
7. ChatGPT può consultare questi file tramite GitHub **solo se il
   connettore GitHub è autorizzato ad accedere al nuovo repository privato**.
   Potrebbe essere necessaria una autorizzazione aggiuntiva dell'app GitHub.

Il Surface deve essere acceso e con sessione dell'utente avviata; lo schermo
può essere bloccato, ma Windows non deve essere sospeso. Non promettere tempi
esatti se la macchina è in standby. L'automazione non aggiorna mai il
proprio codice, non pubblica notizie, non integra l'APK, non crea proiezioni
arbitrarie e non sostituisce la revisione umana.

## Verifiche, arresto e pulizia

- Task: "ISTAT PULSE - Laboratorio editoriale locale"
- Log: %LOCALAPPDATA%\IstatPulseEditorialBridge\last-run.log
- Credenziale DPAPI: stessa cartella, github-upload-token.dpapi
- Output: workbench/local-automation-outbox/
- Arrestare senza cancellare output:
  Disable-ScheduledTask -TaskName "ISTAT PULSE - Laboratorio editoriale locale"
- Riattivare:
  Enable-ScheduledTask -TaskName "ISTAT PULSE - Laboratorio editoriale locale"
- Rimuovere il task se non più necessario:
  Unregister-ScheduledTask -TaskName "ISTAT PULSE - Laboratorio editoriale locale" -Confirm:$false
- Revocare il token nelle GitHub Developer settings e cancellare il file
  DPAPI locale se si dismette il sistema.
- Non incollare password, token, o interi log contenenti dati sensibili in chat.
- Se il token scade, l'upload fallisce senza passare a un repo pubblico.

## Limitazione fondamentale

**Il task non fa lavorare ChatGPT in background.** Permette al Surface di
eseguire job espliciti e caricare i risultati privati. ChatGPT può quindi
leggerli nei turni successivi oppure con un'automazione separatamente
richiesta e disponibile; non esiste un ciclo autonomo di ChatGPT che
modifica il codice e prende decisioni continue senza nuovi trigger.

## Sicurezza e proprietà dei dati

- Il repository DATA è PUBBLICO. Tutte le proposte AI e i report devono
  stare esclusivamente nel repository PRIVATO dedicato.
- La GitHub fine-grained PAT può scrivere contenuti nel solo repo selezionato
  e non concede esplicitamente permessi agli altri repository.
- Il codice proveniente da GitHub non viene aggiornato automaticamente.
  Quando si decide di aggiornarlo, verificare sempre le modifiche prima
  di lanciarlo sul Surface.
- Il task usa le autorizzazioni dell'utente Windows che lo ha installato:
  non è una sandbox di sicurezza totale. Continuare a proteggere Windows.
