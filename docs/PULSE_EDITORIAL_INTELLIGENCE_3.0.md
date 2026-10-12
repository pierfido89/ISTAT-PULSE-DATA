# PULSE Editorial Intelligence 3.0 — percorso senza nuovo hardware

**Stato:** prototipo indipendente sul ramo feat/pulse-editorial-ai-1.0.
Modello invariato: Ollama Qwen3 4B Instruct. Nessuna API a pagamento,
nessuna nuova installazione, nessun APK, nessuna pubblicazione.

## Decisione di progetto

1. PULSE Research Engine: SI, gradualmente.
2. PULSE Editorial Intelligence: SI, con compiti adatti al 4B.
3. PULSE Fact Checker indipendente: SI, a ogni passaggio.
4. Confronto con modelli superiori: RINVIATO, nessun download.

L'intelligenza del prodotto viene principalmente dalle evidenze
verificate, dalle relazioni fra indicatori e dalle elaborazioni
statistiche controllate, non dal testo inventato dal modello.

## Research Engine — primo funzionamento

Il file scripts/pulse_research_engine.py legge tutte le evidenze
strutturate nel workbench. Nel PDF pilota ISTAT turismo II trimestre
2026 la CI ha estratto 18 risultati, considerato 18 evidenze
verificate e identificato tre coppie comparabili Arrivi + Presenze:
residenti, non residenti e totale.

Produce angolazioni documentate (andamenti opposti, paralleli,
permanenza media calcolata) con una priorità editoriale motivata.
La priorità NON è PULSE Score e NON misura significatività statistica.

**Limite esplicito:** questa versione analizza le evidenze
strutturate, NON tutte le parti in prosa del PDF. Non ha ancora
implementato confronti territoriali o serie storiche multianno.
Se le dimensioni mancano, vengono segnalate, non inventate.

## Editorial Intelligence — usare Qwen3 4B nel ruolo appropriato

Il file scripts/pulse_editorial_intelligence.py propone due modalità:

- OFFLINE: selezione dell'angolazione più promettente attraverso
  regole esplicite, senza Ollama.
- LOCAL AI: Qwen3 4B sceglie soltanto la coppia e l'angolazione
  tra ID ammessi. Se sceglie dati non disponibili o aggiunge
  testo libero, il motore rifiuta la scelta e ripiega sulle
  evidenze prioritarie.

I testi fattuali sono ricostruiti dal codice e dai dati ISTAT.
Il modello partecipa al giudizio editoriale, ma non inventa
numeri, informazioni o spiegazioni. Non è ancora stata
dimostrata una qualità eccellente della prosa autonoma:
questa è una base controllata per svilupparla con prudenza.

## Fact Checker — prime garanzie effettive

Il controllo check_locked_story ricostruisce titolo, lead,
corpo, popolazione e calcolo derivato dagli stessi due indicatori
ufficiali. Una cifra o una frase fattuale diversa dal modello
autorizzato viene respinta.

Questo controllo funziona su queste bozze a struttura bloccata;
NON è ancora un validatore universale della prosa libera.
Le uscite rimangono draft_only e richiedono revisione umana.

## Windows PowerShell — ricerca senza Ollama

    cd C:\Users\fiori\ISTAT-PULSE-AI-TEST
    git pull origin feat/pulse-editorial-ai-1.0
    py scripts/pulse_research_engine.py --input workbench/turismo_q2_2026.json --inspect

Per salvare il dossier:

    py scripts/pulse_research_engine.py --input workbench/turismo_q2_2026.json --output workbench/ricerca_turismo_v3.json

Per produrre una bozza con i soli dati validati:

    py scripts/pulse_editorial_intelligence.py --input workbench/turismo_q2_2026.json --output workbench/bozza_editoriale_v3_offline.json

Facoltativo: provare la scelta editoriale del Qwen3 già installato:

    py scripts/pulse_editorial_intelligence.py --input workbench/turismo_q2_2026.json --output workbench/bozza_editoriale_v3_qwen.json --use-local-ai

L'ultimo comando non cerca modelli alternativi. Usa soltanto
Ollama locale, già configurato. Non richiede hardware nuovo.

## Qualità e roadmap

La CI al primo rilascio del prototipo ha superato 118 test
senza chiamate a modelli cloud e ha verificato l'estrazione
dal PDF ufficiale ISTAT. Sono test di correttezza del codice:
non certificano ancora la qualità del giornalismo generativo.

Passi successivi: copertura di pubblicazioni diversificate,
testi in prosa degli originali con citazioni per paragrafo,
relazioni storiche/territoriali solo dove i dati coincidono,
revisione di 20 pubblicazioni diverse e misurazione della
qualità editoriale da parte di persone. Non entra in produzione
senza approvazione.
