# PULSE Editorial AI 2.0 — Notizie da indicatori collegati

**Stato:** prototipo di laboratorio separato dalla produzione, nel ramo
`feat/pulse-editorial-ai-1.0` e nella relativa PR. **Non pubblica articoli,
non modifica feed, non modifica l'APK e non assegna PULSE Score.**
È una fase successiva sperimentale rispetto alle bozze mono-indicatore v1.1–1.4.

## Perché nasce

Nei test reali v1.1–1.4 sul Surface Pro 8, Qwen3 4B ha talvolta scritto
bozze numericamente corrette ma ridondanti, e talvolta ha inventato
totali passati, durate sbagliate o spiegazioni non dimostrate.
La causa di fondo è anche editoriale: **una singola statistica non è
sempre una notizia articolata**.

Il nuovo motore cerca prima collegamenti reali e certificabili
fra due indicatori *distinti* della medesima fonte primaria,
poi costruisce una narrazione ancorata a quei confronti.

## Il primo caso verificato: ISTAT, turismo II trimestre 2026

La fonte primaria è il PDF statistico ISTAT del II trimestre 2026:

https://www.istat.it/wp-content/uploads/2026/09/Statistica-Flash_II_Trimestre_2026.pdf

Fra le evidenze estratte con pagina, riga, URL e hash SHA-256:

| Segmento | Arrivi | Var. tendenziale | Presenze (notti) | Var. tendenziale |
|---|---:|---:|---:|---:|
| Esercizi alberghieri · residenti | 12.464.038 | −4,3% | 32.162.873 | +1,7% |

Le due variazioni procedono in direzioni opposte.
**Questo è un confronto descrittivo, NON una prova di
cambiamento dei comportamenti, delle cause o della durata media
del soggiorno.**

Il test live di estrazione ISTAT in GitHub Actions identifica
**3 coppie** per il periodo 2026-Q2: residenti,
non residenti e totale negli esercizi alberghieri.
Sono tutte coppie **Arrivi + Presenze**.

## Garanzie del raggruppamento

`scripts/pulse_editorial_pairs.py` seleziona SOLO coppie che rispettano:

1. Fonte primaria statistica ufficiale HTTPS, verificata dal lettore
   delle evidenze già esistente.
2. **Identico URL, identico SHA-256** del PDF.
3. **Identico trimestre, struttura ricettiva e segmento di residenza**.
4. Due indicatori diversi, univoci, con valori assoluti e variazioni
   tendenziali ufficiali riferite allo stesso trimestre precedente.
5. Evidenze **distinte e tracciate** a posizioni diverse del PDF.
6. Unità corrette: `arrivi` per Arrivi; `notti` per Presenze.
7. Nessun conflitto, duplicato ambiguo o reinterpretazione di dati
   verificati. Se le prove non bastano, non viene creata la coppia.

Il codice si concentra volutamente sulla prima tipologia
documentata, quella degli esercizi alberghieri. Altre coppie
(occupazione, energia, scuola ecc.) richiedono definizioni
specifiche e test propri.

## Separazione tra dati, giornalismo e linguaggio

- **Titolo e introduzione** vengono assemblati dal codice in base
  ai valori verificati, non vengono inventati da Qwen3.
- **Corpo base** fornisce una definizione statistica controllata
  di Arrivi e Presenze e il periodo di confronto.
- **Qwen3 locale** prova a proporre UNA frase complementare di
  contesto, senza cifre né nuovi fatti. Il motore respinge contesti
  con numeri inventati, inversioni di direzione, gruppi errati,
  durate non supportate, record, causalità, falsa significatività
  o inferenze non dimostrate fra i due fenomeni.
- Una proposta respinta è conservata per audit nel campo
  `model_proposed_context`, ma **non viene aggiunta al corpo**
  costruito dal codice.
- Una proposta che supera le verifiche è solo `review_required`;
  la revisione umana resta obbligatoria. La verifica semantica
  lessicale non è infallibile.

Campi dell'output: `evidence_count:2`, `evidence` con due
tracce ufficiali, `comparison_basis`, `insight_type`,
`editorial_format:paired_indicator_draft`, `quality`,
`publication_status:draft_only`, `pulse_score:null`,
`patterns:[]`. Una direzione opposta NON viene confusa
con il pattern formale `INVERSIONE` di PULSE, che richiede
prove di serie temporali più ampie.

## Prova gratuita sul Surface Pro 8 — Windows PowerShell

Nel progetto già scaricato:

```powershell
cd C:\Users\fiori\ISTAT-PULSE-AI-TEST
git pull origin feat/pulse-editorial-ai-1.0
```

Prima **solo ispezione**, senza attivare Ollama:

```powershell
py scripts/pulse_editorial_pairs.py --input workbench/turismo_q2_2026.json --inspect
```

Output atteso: `paired_candidates: 3`, salvo cambiamenti
nelle evidenze scaricate in precedenza.

Per **una singola notizia accoppiata** con il modello gratuito
già installato, senza rigenerare le tre vecchie schede:

```powershell
py scripts/pulse_editorial_pairs.py --input workbench/turismo_q2_2026.json --output workbench/bozza_coppia_turismo_q2_2026.json --limit 1
```

Allegare il file `workbench/bozza_coppia_turismo_q2_2026.json`
per la valutazione dei contenuti da parte dell'editor.
Se Ollama non risponde, il programma non attiva alcuna API cloud.
Il file originale `turismo_q2_2026.json` resta invariato.

Per eseguire i test offline, senza Qwen:

```powershell
py -m unittest discover -s tests -p "test_pulse_editorial*.py" -v
```

## Sviluppi successivi, non ancora implementati

1. Verifica editoriale delle coppie reali generate dal Surface.
2. Valutazione di eventuale statistica derivata della durata media:
   servirebbe un rapporto controllato con denominatori omogenei,
   dimensioni identiche, intervalli e arrotondamenti gestiti,
   più revisione metodologica. **Non calcolata né affermata ora.**
3. Raggruppamenti di tre o più indicatori, solo per fonti e domini
   con dimensionalità provata.
4. Comparazione della qualità tra mini-notizia deterministica,
   testo assistito da Qwen3 e successiva revisione umana.
5. Eventuale integrazione nell'app SOLO dopo approvazione distinta.
