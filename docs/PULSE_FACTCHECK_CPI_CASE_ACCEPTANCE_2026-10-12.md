# PULSE — Accettazione tecnica Fact Checker, caso prezzi agosto 2026

_Data: 12 ottobre 2026 · modulo sperimentale · nessuna modifica APK o pubblicazione._

## Risultato

**Superato il controllo deterministico del primo articolo approfondito PULSE**, titolo: «Inflazione al 3,3% ad agosto 2026: l’energia accelera, la componente di fondo rallenta». La pubblicazione non è autorizzata da questo documento.

L'articolo ha **344 parole, cinque paragrafi e 21 frasi incluso il titolo**. Il nuovo registro cita **35 valori numerici**, ciascuno attribuito al proprio indicatore, alla misura corretta (livello dell'indice, variazione mensile, variazione annua o differenziale in punti percentuali) e a un'evidenza proveniente dal PDF originale.

### I numeri ufficiali verificati

| Indicatore | Luglio 2026, tasso annuo | Agosto 2026, tasso annuo | Nota |
| --- | ---: | ---: | --- |
| NIC generale | +2,9% | +3,3% | NIC +0,5% su mese; inclusi tabacchi |
| Beni energetici | +11,6% | +17,1% | Prospetto 3 |
| Energetici regolamentati | +14,8% | +18,6% | Prospetto 3 |
| Energetici non regolamentati | +11,4% | +17,0% | Prospetto 3 |
| Beni | +3,2% | +4,1% | Prospetto 3 |
| Servizi | +2,7% | +2,4% | Prospetto 3 |
| Differenziale servizi meno beni | -0,5 p.p. | -1,7 p.p. | Calcolo controllato, non nuova osservazione |
| Inflazione di fondo | +1,6% | +1,5% | Esclusi energetici e alimentari freschi |
| Indice senza energetici | +1,8% | +1,7% | Definizione diversa dalla precedente |
| Carrello della spesa | +1,0% | +0,9% | Alimentari e prodotti per casa/persona |
| IPCA | — | +3,2% | Indice 102,7, mese +0,1% |
| FOI | — | +3,4% | Al netto tabacchi; indice 103,7, mese +0,6% |
| NIC livello indice | — | 103,9 | Base 2025=100; non percentuale |

## Come è stato risolto il difetto originario

Il Research Engine conservava tre soli fatti per il tema prezzi: NIC, IPCA, FOI. Era impossibile verificare in modo rigoroso i paragrafi su energia, beni, servizi e componente di fondo.

Il nuovo estrattore **`scripts/pulse_cpi_evidence_extended.py`** ha scaricato e verificato l'**originale PDF ufficiale ISTAT di 22 pagine**, con impronta SHA-256 bloccata:

`d3647dade0220cfe1525be8e69166d691b4b89c5c48303ff6624fd7d76bd7024`

Il PDF struttura la riga «Componente di fondo» in tre linee fuori dall'ordine di lettura; abbiamo individuato la disposizione reale e programmato una ricostruzione vincolata da etichetta, peso e cinque colonne numeriche, **senza imputare o inventare valori**. Sono stati estratti **9 indicatori della tabella e un differenziale derivato**, con 10 identificativi nuovi `E-PRICES-01-…-04` fino a `…-13`. Il dossier esteso contiene **13 fatti per il tema prezzi**, mantenendo invariati i 16 dossier tematici precedenti.

**CI sorgente reale:** https://github.com/pierfido89/ISTAT-PULSE-DATA/actions/runs/38217129007

**Dossier verificato:** https://github.com/pierfido89/ISTAT-PULSE-DATA/blob/feat/pulse-editorial-ai-1.0/data/research/chatgpt_evidence_packet_cpi_v2.json

## Controllo indipendente della singola frase

Il file privato `checks/pulse_cpi_longform_audit.py` confronta ogni frase **esattamente** con il registro della bozza v2, vieta omissioni di valori nel registro, controlla la corrispondenza con il fatto e con la metrica esatta, distingue decimali italiani e Python, richiede la direzione negativa corretta per il differenziale e verifica le qualifiche NIC/FOI rispetto ai tabacchi. Non utilizza ChatGPT per decidere se una cifra è corretta.

Risultato del report:
- **21/21 frasi** incluse nel registro, compreso il titolo;
- **35/35 menzioni numeriche** confrontate con il fatto originale corretto;
- **13** fatti disponibili sul PDF ufficiale per la storia prezzi;
- **0 blocchi** nell'esito deterministico;
- Quattro test avversariali: valore fittizio, fonte numerica sbagliata, segno invertito e popolazione/indice errati: **tutti rifiutati**.

**CI autonoma:** https://github.com/pierfido89/ISTAT-PULSE-EDITORIAL-RESULTS/actions/runs/38217748620

**Report privato:** https://github.com/pierfido89/ISTAT-PULSE-EDITORIAL-RESULTS/blob/main/checks/reports/PULSE_PREZZI_AGOSTO_2026_v2.audit.json

**Bozza v2 con registro per frase:** https://github.com/pierfido89/ISTAT-PULSE-EDITORIAL-RESULTS/blob/main/drafts/longform/PULSE_PREZZI_AGOSTO_2026_v2.json

## Secondo controllo semantico

ChatGPT ha svolto una distinta lettura del testo, usando la sintesi ufficiale e i Prospetti 1 e 3 (pagine 1, 2 e 4), registrando un esame di **21/21 frasi**. Nessun errore critico è stato identificato **nel perimetro revisionato**. Questo non è un parere di un revisore umano indipendente e non dimostra di aver ricontrollato integralmente tutte le 22 pagine; una parte delle frasi sono spiegazioni editoriali coerenti, non dati autonomi.

**Resoconto privato:** https://github.com/pierfido89/ISTAT-PULSE-EDITORIAL-RESULTS/blob/main/checks/semantic/PULSE_PREZZI_AGOSTO_2026_v2.semantic.json

## Condizioni prima di qualsiasi pubblicazione

- Revisione umana indipendente sulla fonte originale e sull'interpretazione finale per il primo rilascio.
- Collaudo in ambiente di prova del gate automatico PULSE, autorizzato come obiettivo futuro ma **attualmente disabilitato**.
- Nessuna nuova APK, nessun codice della versione stabile Android modificato, nessun credito OpenAI acquistato o chiamata API a pagamento.
- Se l'ente modifica il PDF, la diversa SHA-256 provoca un **blocco** e una nuova verifica, non un'accettazione silenziosa.
- I miglioramenti di questo caso specifico **non** certificano automaticamente gli altri nove articoli o le altre fonti.

**Conclusione tecnica:** il difetto delle sole tre evidenze nel primo articolo è stato risolto con fonte originale e verifica indipendente dei numeri; l'articolo è **candidato ad approvazione dopo ultimo controllo umano**, non ancora pubblicabile automaticamente.
