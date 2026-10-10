# PULSE Research Engine 3.1 — ricerca documentale e confronti

**Stato verificato:** nucleo di ricerca sperimentale funzionante nel ramo
`feat/pulse-editorial-ai-1.0`. Nessuna pubblicazione, APK o modifica dei
feed in produzione. Il motore non chiama Qwen3 e non richiede API a pagamento.

## Funzioni effettivamente realizzate

1. **Lettura integrale dello strato testuale PDF.** Il modulo
   `scripts/pulse_research_reading.py` esamina le pagine del file,
   conserva hash SHA-256, posizioni pagina/riga, paragrafi e un rapporto
   verificabile sulle pagine lette. Rende espliciti i limiti dovuti
   a PDF immagine, pagine senza testo o capienza massima.
   Non effettua OCR né pretende di verificare automaticamente
   i numeri narrati nel testo.

2. **Ricerca di fenomeni nel testo.** Sono classificate segnalazioni
   tematiche per popolazione, lavoro, economia, ambiente, istruzione,
   turismo e società. I passaggi restano citazioni della fonte con
   `proof_status=narrative_lead_unverified_needs_structured_source_witness`:
   non diventano prove statistiche e non entrano nell'articolo autonomo.

3. **Comparabilità delle evidenze già certificate.** Il modulo
   `scripts/pulse_editorial_pairs.py` mantiene i vincoli di struttura,
   popolazione, periodo, fonte e unità per gli indicatori turistici.
   Il Research Engine ordina gli angoli possibili con motivazioni,
   non con un falso PULSE Score.

4. **Confronti storici su serie annuali.** Il modulo
   `scripts/pulse_research_comparisons.py` ammette solo serie
   esplicitamente verificate, annuali e consecutive, con sorgente/hash,
   indicatore, unità, popolazione, territorio e posizione documentale.
   Calcola differenze e direzioni; non inventa record o significatività.

5. **Confronti territoriali su tassi omogenei.** Richiede territorio
   codificato, livello geografico identico, stesso denominatore,
   stessa popolazione, sesso/età, indicatore, unità, periodo, fonte
   e hash. Non confronta conteggi grezzi di territori molto differenti
   come prova automatica di un fenomeno.

6. **Importazione universale preliminare.**
   `scripts/pulse_research_import.py` importa file PDF ufficiali locali
   anche fuori dal turismo. Sono subito analizzabili i temi narrativi;
   le evidenze numeriche rimangono zero fino a estrazione verificata.
   L'URL ufficiale viene dichiarato dall'editor e in questo percorso
   **non è confrontato automaticamente con una copia scaricata**.

7. **Rapporto di copertura e rischio.** Il JSON di ricerca documenta
   quanti elementi sono strutturati, quanti passaggi narrativi esistono,
   pagine accessibili, candidati verificati, ricerche preliminari
   ancora da provare, e mancanza di dati temporali o geografici.

## Test con fonti e limiti reali

Il test di integrazione ha scaricato il PDF ufficiale
ISTAT *Flussi turistici, II trimestre 2026* e ha verificato:

- PDF di **9 pagine**, 9 pagine di testo esaminabili;
- **180 passaggi** conservati con provenienza pagina/riga;
- **18 evidenze strutturate verificate** per il caso pilota;
- **3 coppie** Arrivi/Presenze comparabili;
- nessuna serie annuale o confronto regionale attestato
  **in quel particolare workbench**, senza inventarne.

La verifica CI del ramo esegue **118 test editoriali + 28 di ricerca**,
oltre all'esame del vero PDF ISTAT. I test per storia e territori
usano **dati sintetici dichiarati come tali**: non dimostrano
che gli adattatori di tutte le fonti ISTAT siano già attivi.

## Principali comandi gratuiti sul Surface

Aggiornamento:

```powershell
cd C:\Users\fiori\ISTAT-PULSE-AI-TEST
git pull origin feat/pulse-editorial-ai-1.0
```

Ispezione del PDF pilota già predisposto:

```powershell
py scripts/pulse_research_engine.py --input workbench/turismo_q2_2026.json --inspect
```

**Attenzione:** per avere anche il testo integrale bisogna
rigenerare il workbench con la versione aggiornata:

```powershell
py scripts/pulse_editorial_sample.py --output workbench/turismo_q2_2026_completo.json
py scripts/pulse_research_engine.py --input workbench/turismo_q2_2026_completo.json --output workbench/ricerca_turismo_3_1.json
```

Per ricercare un altro PDF già scaricato localmente:

```powershell
py scripts/pulse_research_import.py --pdf "C:\Percorso\studio.pdf" --source-url "https://www.istat.it/..." --title "Titolo della pubblicazione" --output workbench/altra_pubblicazione.json
py scripts/pulse_research_engine.py --input workbench/altra_pubblicazione.json --output workbench/altra_ricerca.json
```

I tre puntini nell'indirizzo sono un **segnaposto**: utilizzare
l'URL ufficiale reale del documento. L'importatore non accede
a Internet e non chiama Ollama.

## Criterio di completamento e limite di diffusione

La **base tecnica del Research Engine 3.1 è funzionante** e separa
in modo rigoroso conoscenza verificata, contesto e materiale
ancora da controllare. Ciò NON equivale a dichiarare finita
l'integrazione automatica di ogni tabella, grafico, serie storica
e territorio di tutte le pubblicazioni ISTAT. Per tale obiettivo
rimangono necessari adattatori metodologici ufficiali per fonte,
test su più ambiti e verifica editoriale umana.

Non si deve presentare il sistema come una AI che "legge e comprende
tutto" senza specificare i livelli di verifica. Il secondo obiettivo,
PULSE Editorial Intelligence, potrà utilizzare questa base senza
attribuire fatti non dimostrati a un modello Qwen3 4B.
