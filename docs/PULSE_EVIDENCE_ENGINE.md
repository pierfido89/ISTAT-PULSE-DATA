# ISTAT PULSE — Motore di evidenze documentali (fase 1)

Scopo: estrarre **solo** confronti annuali verificabili dalla stessa tabella di una fonte primaria. Questa prima fase non modifica l'APK.

## Input supportati

- HTML: tabelle con anni espliciti e indicatori omogenei.
- PDF: tabelle testuali/vettoriali, fino a 35 pagine; non OCR.
- XLS e XLSX: massimo 30 fogli, 2.000 righe e 40 colonne per foglio.
- CSV/TSV: tabelle con intestazioni annuali esplicite.
- JSON: array tabulari espliciti; non decodifica arbitraria di ogni schema JSON/SDMX.

Il motore espone `extract_url(url)` e `extract_bytes(bytes, source_url, mime, filename)` in `scripts/pulse_evidence.py`. Il Radar riutilizza i documenti originali già acquisiti, anziché fare un secondo download.

## Gate di pubblicazione

Ogni evidenza conserva URL HTTPS finale, hash SHA256 del documento, posizione tabella/riga, indicatore, unità, due anni, due valori grezzi e normalizzati, differenza e metodo di estrazione. Un confronto passa solo se **nella stessa riga e nella stessa tabella** esistono almeno due intestazioni annuali, unità percentuale esplicita, valori validi nell'intervallo 0–100 e distanza temporale non superiore a cinque anni.

Numeri sciolti nella prosa, PDF fotografici, intervalli temporali troppo lunghi, unità assenti, valori mancanti e unità non percentuali **non sono automaticamente confrontati**. Lo stato `no_comparable_series` non equivale a un errore.

La verifica della fonte primaria nel Radar mantiene ulteriori filtri su dominio, parole chiave e riscontro numerico. Le evidenze estratte non devono essere equiparate automaticamente a un articolo editoriale completo.

## Test

- `python -m unittest discover -s tests -p test_pulse_evidence.py -v`
- `python -m unittest discover -s tests -p test_pulse_evidence_live.py -v`

La seconda suite verifica la consultabilità e la gestione *prudente* di cinque **pagine di pubblicazioni reali**: ISTAT, INPS, ISPRA, Banca d'Italia, Eurostat. **Non** certifica il recupero di tutti gli allegati PDF/Excel presenti in tali pagine. Il job live rimane diagnostico e può fallire per limiti di accesso esterni.

## Limiti ancora aperti

1. OCR per PDF scansionati e riconoscimento tabelle su più pagine;
2. SDMX-JSON / SDMX-XML secondo i rispettivi schemi, con metadati serie;
3. Valori assoluti, euro, tassi diversi dalle percentuali e confronti con unità multiple;
4. Gestione di revisioni, rotture metodologiche e comparabilità territoriale;
5. Download automatico di allegati PDF/XLSX da pagine di pubblicazione;
6. Collegamento del nuovo schema nell'app Android: **non attivato in questa fase**.

La denominazione 'universale' si riferisce al **contenitore estendibile multi-formato**, non alla garanzia di estrazione completa da ogni documento.
