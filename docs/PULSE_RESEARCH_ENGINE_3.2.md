# PULSE Research Engine 3.2 — Tre pubblicazioni ISTAT reali validate

**Data:** 10 ottobre 2026. **Stato:** fase 1 ancora aperta;
nuovo progresso reale, documentato in PR #13 sul ramo
`feat/pulse-editorial-ai-1.0`. Non tocca APK, feed di notizie
pubblicate o modelli AI. Qwen3 4B rimane inalterato.

## Avanzamento verificato in CI

Tre PDF ufficiali ISTAT, completamente letti nel loro strato testuale:

| Dominio | Documento | Pagine lette | Evidenze numeriche |
|---|---|---:|---:|
| Turismo | Flussi turistici, II trimestre 2026 | 9/9 | 18 evidenze, 3 coppie Arrivi/Presenze |
| Lavoro | Occupati e disoccupati, agosto 2026 | 16/16 | 9 righe da Prospetto 1 |
| Prezzi | Prezzi al consumo, agosto 2026, definitivi | 22/22 | 3 righe da Prospetto 1 (NIC/IPCA/FOI) |

La CI sul commit `b91b74082a84351c37094b8b2cfcad9942b7336e`
ha completato senza errori **118 test editoriali e 41 test
di ricerca = 159 test**, oltre ai download e alle verifiche
effettive sui tre PDF. Log GitHub:
https://github.com/pierfido89/ISTAT-PULSE-DATA/actions/runs/38070337410

## Il progresso non è semplicemente leggere il PDF

- Il nuovo `scripts/pulse_research_labor.py` legge soltanto
  il **Prospetto 1**, richiedendo titolo, periodo, unità
  (migliaia di persone), gruppo MASCHI/FEMMINE/TOTALE e
  tutte e nove le righe esplicite. Interpreta correttamente
  `24.352` come **24.352.000 persone**, e `838`
  come **838.000**, non come 838 persone. Conserva variazioni
  tendenziali, periodo, hash e pagina/riga.
- `scripts/pulse_research_prices.py` legge soltanto il
  **Prospetto 1** dei dati definitivi di agosto 2026;
  distingue NIC, IPCA, FOI, livelli indice base 2025=100,
  cambi congiunturali e tendenziali. I tre indici NON sono
  falsamente fusi in una serie o in un indicatore unico.
- `scripts/pulse_research_engine.py` ora aggiunge
  `labor_signals`, `price_signals` e le tracce alla coda
  `research_stories`. Si tratta di segnalazioni da
  revisionare, non notizie pronte alla pubblicazione.

## Evidenze reali ISTAT

### Lavoro

Occupati agosto 2026: **24.352.000** (unità); variazione
tendenziale ufficiale **+1,2%**. Disoccupati: **1.591.000**,
variazione tendenziale **+8,8%**. Entrambe le cifre sono
compatibili con Prospetto 1, e il parser le mantiene
distinte per gruppo e indicatore.

Documento:
https://www.istat.it/wp-content/uploads/2026/10/CS_Occupati-e-disoccupati_AGOSTO_2026.pdf

### Prezzi

Agosto 2026 (dati definitivi):
**NIC +3,3%**, **IPCA +3,2%**, **FOI +3,4%**
su base annua. I rispettivi valori indice sono 103,9;
102,7 e 103,7, base 2025=100, ma le popolazioni e
finalità non coincidono e richiedono confronto prudente.

Documento:
https://www.istat.it/wp-content/uploads/2026/09/CS_Prezzi-al-consumo_Def_Agosto2026.pdf

## Cosa manca per chiudere l'obiettivo 1

Non si può ancora dichiarare il Research Engine interamente
concluso: mancano **validazioni numeriche su pubblicazioni
reali di popolazione, istruzione e ambiente**, una
copertura più generalizzabile dei formati tabellari,
e test di comparabilità storico-territoriale direttamente
su dati ufficiali omogenei anziché esclusivamente sintetici.
La lettura del PDF non equivale alla certificazione dei
numeri contenuti nella prosa.

La versione 3.2 **non è un prodotto pronto**. Questo
è un avanzamento reale verso il completamento dell'obiettivo.

## Procedura locale gratuita, nessun APK

Nel repository di sviluppo aggiornato:

```powershell
py scripts/pulse_research_labor_sample.py --output workbench/lavoro_agosto2026.json
```

```powershell
py scripts/pulse_research_prices_sample.py --output workbench/prezzi_agosto2026.json
```

I file sono **solo workbench**, revisionabili con
`py scripts/pulse_research_engine.py --input <file> --inspect`.
Le fonti primarie sono scaricate dal sito ISTAT,
non tramite API AI a pagamento.
