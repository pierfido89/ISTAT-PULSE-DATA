# PULSE Editorial Intelligence 3.4 — avvio Fase 2

**Stato:** prima integrazione sperimentale del motore editoriale
con il PULSE Research Engine 3.3. Il Research Engine 3.3 resta
**accettato nel perimetro dei sei PDF ISTAT**. La Editorial
Intelligence, invece, **NON è ancora completa**.

## Cosa funziona ora

Il modulo `scripts/pulse_editorial_storyboards.py` riceve un
dossier contenente uno o più workbench ufficiali e ricostruisce
possibili articoli con affermazioni supportate dalle evidenze
del Research Engine, tra sei tipi di notizia:

1. **Turismo:** confronto degli arrivi e delle presenze;
   elaborazione della permanenza media soltanto dove ammessa.
2. **Lavoro:** livelli e variazioni tendenziali di occupati
   e disoccupati, con conversione corretta da migliaia a
   persone, senza fondere gruppi e indicatori.
3. **Prezzi:** NIC, IPCA e FOI, panieri distinti e variazioni
   tendenziali mantenute separate dai livelli indice.
4. **Popolazione:** bilancio provvisorio 2025, nascite e
   decessi arrotondati alle migliaia; niente falsi conteggi
   esatti delle persone.
5. **Istruzione:** quote con tre osservazioni annuali
   confrontabili; le differenze fra quote sono espresse
   in **punti percentuali**, non come incremento percentuale.
6. **Ambiente:** tassi di raccolta differenziata e misure
   normalizzate, con denominatori, periodo e livello
   geografico coerenti.

Ogni bozza contiene titolo, introduzione, testo, evidenze
sorgente con URL, SHA e posizioni nel PDF, tema scelto,
stato di revisione e pubblicazione disabilitata.

Il risultato di default comprende **un esempio per ciascuno
dei sei ambiti documentati**, invece di limitarsi a turismo.

## Ruolo di Qwen3 4B

Il modello esistente `qwen3:4b-instruct` su Ollama locale
può scegliere la **notizia** e l'**angolazione** fra
alternative già verificate: `main` (fenomeno) o
`method` (significato e metodologia).

Non può ancora scrivere liberamente paragrafi destinati alla
pubblicazione: qualunque risposta con nuove affermazioni,
titoli, numeri o campi extra viene respinta. In tal caso
il motore ricorre alla priorità documentata.

**Questa è la prima fase della Editorial Intelligence,
non la soluzione finale al problema della qualità
giornalistica**. Dobbiamo ancora progettare e valutare
una scrittura locale naturale, non ripetitiva, con controlli
sui fatti indipendenti dalla formulazione linguistica.
Nessuna affermazione di "qualità eccellente" è giustificata
finché non abbiamo confrontato le bozze Qwen reali sul Surface.

## Verifica CI

Il workflow GitHub su branch sperimentale esegue
**129 test editoriali + 49 test Research = 178 test**,
e, dopo download di sei PDF ISTAT reali, genera:

`/tmp/pulse-editorial-six-drafts.json`

Esito della CI: **16 opzioni editoriali, 6 bozze da
revisionare, 0 pubblicazioni**. Tutti i test superati
al commit `1219df06328c12c4502e1088c7867b1344949e8c`
e successiva pipeline.
Il sistema non usa servizi AI esterni nei test.

## Riprodurre senza spese sul Surface

Per prima cosa aggiornare il ramo sperimentale:

```powershell
cd C:\Users\fiori\ISTAT-PULSE-AI-TEST
git pull origin feat/pulse-editorial-ai-1.0
```

Poi occorrono i sei workbench locali, già generabili
con gli estrattori documentati in
`docs/PULSE_RESEARCH_ENGINE_3.3_ACCEPTED.md`.

Quando tutti e sei sono presenti, generare il fascicolo
editoriale senza LLM (workbench e nomi di esempio):

```powershell
py scripts/pulse_editorial_storyboards.py --input workbench/turismo_q2_2026.json --additional-input workbench/lavoro_agosto2026.json workbench/prezzi_agosto2026.json workbench/popolazione_2025.json workbench/istruzione_2024.json workbench/ambiente_2024_2025.json --output workbench/bozze_editoriali_3_4.json
```

Aggiungendo `--use-local-ai` alla fine, Qwen3 4B
sceglierà la notizia e l'angolo che ritiene più
interessanti, *senza produrre nuovi numeri*. L'esito
reale di Qwen deve essere controllato separatamente.

## Limiti e prossima milestone

- **Realizzato:** ponte Research -> schede editoriali
  multisettoriali -> scelta vincolata con Qwen ->
  controllo delle affermazioni strutturate.
- **Non realizzato:** generazione di prosa giornalistica
  pienamente naturale e originale, revisione automatica
  di ogni possibile affermazione libera, pubblicazione.
- **Prossima milestone:** stimolare Qwen3 4B
  con dossier ricchi e puntuali per progettare una
  narrazione articolata, valutando qualità e correttezza
  su sei temi e conservando la verifica indipendente
  dei fatti. Tutte le bozze rimangono `draft_only`.

Il codice non modifica il feed di produzione, non
genera APK e non comporta costi per API.
