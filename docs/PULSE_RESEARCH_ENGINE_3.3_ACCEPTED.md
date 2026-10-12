# ISTAT PULSE — Research Engine 3.3, fase 1 completata (perimetro MVP)

**Data:** 10 ottobre 2026. **Branch:** `feat/pulse-editorial-ai-1.0`,
**PR:** #13. Il risultato è un prototipo indipendente, sperimentale,
non integrato nel feed, senza APK e senza pubblicazione automatica.

## Che cosa significa COMPLETATO

La fase di validazione dell'**MVP del Research Engine**, definita in modo
misurabile come la capacità di leggere, estrarre e confrontare dati ufficiali
su **sei ambiti documentati**, ha superato la procedura di accettazione.
Questa conclusione **non** significa che ogni tabella, immagine, grafico,
PDF scansionato o flusso ISTAT futuro sia già supportato. La copertura di
nuovi formati richiede estrattori adattati e prove ripetibili.

## Test d'integrazione reale — risultati verificati

La GitHub Action ha scaricato sei PDF dal dominio ufficiale
`www.istat.it`, li ha letti integralmente nel livello di testo,
ha confermato gli SHA-256 e ha applicato gli estrattori di fonte.

| Ambito | Riferimento | Pagine PDF | Osservazioni verificabili |
|---|---|---:|---:|
| Turismo | Flussi turistici II trimestre 2026 | 9 | 18 righe |
| Lavoro | Occupati e disoccupati agosto 2026 | 16 | 9 righe |
| Prezzi | Prezzi al consumo agosto 2026, definitivi | 22 | 3 indici |
| Popolazione | Indicatori demografici anno 2025 | 12 | 8 voci arrotondate |
| Istruzione | Livelli di istruzione, anno 2024 | 15 | 12 osservazioni in 4 serie |
| Ambiente | Raccolta differenziata 2024–2025 | 17 | 20 valori di tasso/rapporto |

**Totale: 91 pagine, 70 osservazioni statistiche in sei contratti di
verifica e 16 piste di ricerca supportate dalle fonti.**

La prova di accettazione è in
`scripts/pulse_research_acceptance.py` e fallisce se manca uno dei
sei documenti, se le fonti vengono mescolate, se un valore ufficiale
non coincide, se la lettura di un PDF è incompleta o se le osservazioni
non soddisfano i rispettivi contratti.

### Risultati verificati su numeri REALI (non fixture sintetiche)

- Turismo: clienti residenti negli esercizi alberghieri,
  12.464.038 arrivi (−4,3%) e 32.162.873 notti di presenze
  (+1,7%). Due indicatori diversi con stessa fonte e trimestre.
- Lavoro: 24.352 (migliaia) occupati, ossia 24.352.000 persone.
  Il parser conserva le unità della tabella e i gruppi di genere.
- Prezzi: NIC +3,3%, IPCA +3,2%, FOI +3,4% tendenziali.
  Indici distinti: valori base 2025=100 e panieri diversi.
- Popolazione: 355 mila nascite e 652 mila decessi nel 2025
  in una tabella provvisoria, **arrotondata alle migliaia**;
  non sono presentati come conteggi esatti di individui.
- Istruzione: quota nazionale di 25–64enni con titolo terziario:
  20,3% nel 2022, 21,6% nel 2023, 22,3% nel 2024.
  Differenza 2022–24: **+2,0 punti percentuali**, non +2%.
- Ambiente: raccolta differenziata 2024: 77,8% nel Nord-est
  contro 59,9% nel Sud. Differenza **17,9 punti percentuali**.
  Stessa definizione, denominatore, periodo e ripartizione territoriale.

### Confronti storico-territoriali attestati dalle fonti

Sono stati accettati **quattro confronti storici annuali** (due classi
d'età, Italia e UE27) per il 2022–2024 dal Prospetto ISTAT, e
**quattro confronti territoriali** da una tabella a cinque
ripartizioni sui rifiuti. Le percentuali sono confrontate in punti
percentuali; la quantità di rifiuti è normalizzata per abitante.
Non vengono equiparati conteggi grezzi di territori differenti.

### La catena metodologica

1. Individuazione del documento ufficiale esatto (allowlist + HTTPS).
2. Download del PDF, controllo del dominio di destinazione e SHA-256.
3. Lettura di tutte le pagine con posizione testuale e rapporto copertura.
4. Parsing di tabelle esplicite, schema proprio per ciascuna fonte.
5. Rifiuto delle tabelle parziali, ambigue o senza unità/periodo.
6. Prova di comparabilità per serie storica e per ripartizione.
7. Dossier di ricerca classificato, con priorità spiegabili.
8. Separazione netta fra numeri verificati e prosa non verificata.
9. **Mai pubblicazione senza revisione umana**; nessun PULSE Score.

I moduli sono in `scripts/pulse_research_new_domains.py`,
`scripts/pulse_research_new_domains_sample.py`,
`scripts/pulse_research_comparisons.py`,
`scripts/pulse_research_engine.py` e
`scripts/pulse_research_acceptance.py`.

## Stato dei test

La CI esegue test mockati per errori su numeri, periodi,
unità e attribuzione geografica, e scarica separatamente
i sei PDF per una **prova reale di accettazione**. Una prova
con fixture sintetiche, da sola, non vale come validazione
del formato ISTAT.

**Fonte della verifica CI:** il workflow
`.github/workflows/verify-pulse-editorial-ai.yml`, consultabile
nella PR #13 su GitHub.

## Uso facoltativo su Windows Surface, senza AI

Il Surface non ha bisogno di modelli più potenti o API a pagamento.
Dopo aver aggiornato il branch si possono riprodurre i dossier locali:

```powershell
py scripts/pulse_research_new_domains_sample.py --domain popolazione --output workbench/popolazione_2025.json
```

```powershell
py scripts/pulse_research_new_domains_sample.py --domain istruzione --output workbench/istruzione_2024.json
```

```powershell
py scripts/pulse_research_new_domains_sample.py --domain ambiente --output workbench/ambiente_2024_2025.json
```

Per analizzare più workbench contemporaneamente si usa
`scripts/pulse_research_engine.py --input <prima-fonte>
--additional-input <altre-fonti...> --output <dossier-separato>`.
Qwen3 4B non è necessario per estrazione e fact-check statistico.

## Confini e prossimo passaggio

**FASE 1 / Research Engine 3.3: ACCETTATA nel perimetro dei sei PDF
e delle sei classi di tabelle validate.**

**Non è universale:** restano futuri adattatori per altre pubblicazioni,
lettura di grafici non tabellari, OCR per PDF scansiti e maggiore
ricchezza di serie storiche e territori. Ogni adattatore futuro
deve superare esattamente lo stesso criterio verificabile.

**FASE 2 / Editorial Intelligence:** potrà utilizzare questi dossier
fonte-verificati per far scegliere a Qwen3 4B un angolo giornalistico
e sviluppare testi, mantenendo un Fact Checker esterno e il controllo
umano obbligatorio. Nessuna modifica alla produzione è stata autorizzata.
