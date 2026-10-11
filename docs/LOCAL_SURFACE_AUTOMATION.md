# ISTAT PULSE — Automazione locale prudente (fase pilota)

**11 ottobre 2026 — SOLO branch sperimentale.** Non unire nella produzione,
non modificare l'APK e non pubblicare gli articoli.

## Perché non installiamo un runner GitHub sul Surface

ISTAT-PULSE-DATA è pubblico. GitHub sconsiglia fortemente i self-hosted
runner permanenti nei repository pubblici perché il codice non attendibile
può compromettere il dispositivo. Sul Surface personale, in questa fase,
**NON** installiamo GitHub Actions Runner e **NON** esponiamo Ollama in rete.

## Architettura fase 1

1. ChatGPT può preparare su GitHub esclusivamente un **file JSON di richiesta**
   nel branch sperimentale: `automation/editorial_job.json`.
2. `automation/pulse_local_agent.py`, copiato **localmente e senza aggiornamento
   automatico**, scarica il JSON tramite HTTPS pubblico.
3. Il JSON è convalidato contro uno schema chiuso. Non esistono campi per
   shell, PowerShell, script, URL arbitrari, directory o codice eseguibile.
4. L'agente può chiamare solo il writer locale
   `scripts/pulse_editorial_local_writer.py` con il workbench fisso
   `workbench/edizione_editoriale_3_5.json`, start 0-5 e limit massimo 2.
5. Le proposte rimangono in `workbench/local-automation-outbox/` con revisione
   umana sempre obbligatoria. Il report non equivale a fact checking semantico.
6. Il file JSON iniziale è disabilitato. Si verifica prima `--dry-run`.
   **Nessun job viene eseguito finché non abilitiamo esplicitamente il pilota.**

Il worker **non** fa `git pull`, non aggiorna il proprio codice, non installa
software, non riceve comandi shell, non accetta PR come sorgente del job, non
richiede accesso amministratore, non esegue un server e non carica risultati in
Internet. L'esecuzione richiede PC acceso e Ollama già disponibile su
`127.0.0.1:11434`.

## Primo test PowerShell (nessun modello e nessuna modifica)

Dopo aver aggiornato **manualmente e verificato** il branch sperimentale:
```powershell
py automation/pulse_local_agent.py --dry-run
```
Si deve ricevere `ready: true`, `enabled: false`, domini `lavoro` e
`prezzi`, `ollama_invoked: false`.

## Fase 2, NON ancora configurata

Per restituire automaticamente i risultati a ChatGPT occorre decidere un
canale autenticato **privato** e a permessi minimi, separato dalla produzione,
ad esempio un nuovo repository GitHub privato dedicato alle prove.
Non inserire PAT/token in codice, commit, log, URL o chat. Solo dopo il
collaudo della fase 1 predisporre upload privato degli artifact e un processo
di revisione. ChatGPT non ha accesso diretto a Windows e non può leggere
automaticamente l'outbox locale senza tale canale.

### Limiti da ricordare

- Le modifiche Python proposte su GitHub non si eseguono automaticamente sul
  computer. Questa è una misura di sicurezza intenzionale: un aggiornamento
  eseguibile deve avere una revisione/approvazione separata.
- Il JSON remoto può cambiare la selezione di bozza solo entro gli intervalli
  consentiti, non può introdurre nuovi comandi.
- Nessun risultato viene pubblicato nell'app.
- Per arrestare la futura attività pianificata basterà disabilitare la
  relativa attività di Utilità di pianificazione Windows; **non** è ancora
  stata creata alcuna attività pianificata.
- Questa soluzione riduce i passaggi manuali ma non autorizza ChatGPT a
  continuare lavori autonomamente in chat senza una richiesta/automazione.
