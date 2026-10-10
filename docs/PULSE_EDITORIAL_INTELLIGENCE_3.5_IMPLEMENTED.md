# PULSE Editorial Intelligence 3.5 — Sistema editoriale multi-ambito e laboratorio Qwen3 4B

**Data:** 10 ottobre 2026  
**Ramo sperimentale:** `feat/pulse-editorial-ai-1.0` — [PR #13](https://github.com/pierfido89/ISTAT-PULSE-DATA/pull/13)  
**Stato:** software della fase editoriale implementato e verificato **per il perimetro dei sei PDF ISTAT del Research Engine 3.3**. **La resa stilistica reale del modello locale Qwen3 4B deve ancora essere provata sul Surface Pro 8**. Nessuna pubblicazione automatica, APK o API a pagamento.

## Architettura editoriale

La Fase 2 è stata divisa in **tre percorsi** rigorosamente separati.

**A. Fatti verificati → articolo redazionale controllato**  
`scripts/pulse_editorial_publication.py`

Il Research Engine, validato su sei pubblicazioni, alimenta sedici possibili piste di ricerca e sei tipi di storia: turismo, lavoro, prezzi, popolazione, istruzione, ambiente. Il nuovo motore costruisce una notizia con:

- titolo e sottotitolo che rispettano l'evidenza;
- attacco con cifre verificate;
- dettaglio aggiuntivo ricavato dai fatti, come i valori intermedi della serie 2022–2024 o il livello dei tre indici dei prezzi;
- spiegazione divulgativa separata dalle interpretazioni causali;
- avvertenze metodologiche specifiche;
- riferimento preciso a URL, SHA del PDF e posizione documentale;
- stato `draft_only` e revisione umana obbligatoria.

I testi di questa modalità sono **composizioni controllate**, non prosa scritta liberamente da un modello linguistico: garantiscono la tracciabilità a costo computazionale quasi nullo.

**B. Qwen3 4B come regista editoriale**  
Nello stesso modulo, con `--use-local-ai`, il modello già presente su Ollama sceglie solo campi chiusi: `story_id`, `voice` (notizia, analisi, divulgazione), `focus` (fenomeno, confronto, metodo), `order` (comparazione, spiegazione). Se propone un ID inesistente, campi aggiuntivi o una struttura non valida, il piano viene scartato e subentra quello verificato.

Il modello organizza l'articolo e ne sceglie l'impostazione, mentre le affermazioni fattuali continuano a essere ricostruite indipendentemente.

**C. Qwen3 4B scrive in italiano libero, ma in quarantena**  
`scripts/pulse_editorial_local_writer.py`

Il modello può davvero proporre una riscrittura dei quattro paragrafi. Il sistema controlla:

- JSON e quattro paragrafi senza campi aggiuntivi;
- numeri introdotti o numeri fondamentali della fonte omessi;
- esempi di rivendicazioni causalistiche, primati o previsioni non documentati;
- URL estranei alla fonte;
- paragrafi duplicati o fortemente ridondanti;
- lunghezza ragionevole;
- regressioni grammaticali note, compreso l'errore `I arrivi`.

**Vincolo essenziale:** un controllo di cifre e strutture **non dimostra che ogni frase nuova sia vera**. Anche se la proposta supera questi filtri, il suo stato rimane `needs_human_semantic_review`; non sostituisce l'articolo approvato, non è pubblicabile e non altera la fonte. L'utente potrà inviare le proposte per la revisione insieme ai riferimenti ISTAT.

## Confronto su sei ambiti realmente verificati

| Dominio | Aggancio Research Engine | Protezione editoriale |
|---|---|---|
| Turismo | Arrivi e presenze del II trimestre 2026 | Non confondere arrivi e notti; niente cause inventate |
| Lavoro | Occupati/disoccupati/inattivi agosto 2026 | Unità da migliaia a persone; categoria di genere conservata |
| Prezzi | NIC, IPCA, FOI definitivi agosto 2026 | Panieri, variazioni annuali e livelli indice distinti |
| Popolazione | Bilancio 2025 provvisorio | Migliaia arrotondate, non conteggi esatti |
| Istruzione | Quote 2022, 2023, 2024 | Serie continua; differenze in punti percentuali |
| Ambiente | Indicatori omogenei fra cinque ripartizioni | Stesso periodo e denominatore, nessun confronto con totali grezzi |

Il collegamento fra dati è svolto dal nostro codice; il modello locale ha accesso soltanto alle alternative già verificate. Il sistema non attribuisce un PULSE Score e non inventa classificazioni formali di pattern.

## Esempi di interpretazione corretta

**Istruzione, Italia, 25–64 anni:** quota con titolo terziario: 20,3% nel 2022, 21,6% nel 2023, 22,3% nel 2024. La differenza fra estremi è **+2,0 punti percentuali** e il passaggio del 2023 è mostrato come osservazione intermedia, non stimata.

**Raccolta differenziata 2024:** il Nord-est registra 77,8%, il Sud 59,9%. Il divario è **17,9 punti percentuali**. I territori e i denominatori sono compatibili nel documento ufficiale. Non equivale a una prova causale o a una classifica dei comuni italiani.

**Demografia 2025:** le cifre di 355 mila nascite e 652 mila decessi sono **provvisorie e arrotondate**. Il calcolo aritmetico di 297 mila decessi in più non è presentato come conteggio preciso né come spiegazione completa dell'andamento della popolazione.

## Controllo indipendente della notizia

`independent_check()` **rigenera** titolo, sottotitolo, lead, paragrafi, corpo, fonte ed evidenza a partire da una scheda del Research Engine e da un piano appartenente all'elenco consentito. Qualsiasi differenza rispetto alla versione verificata è bloccata. `quality_report()` verifica struttura, ripetizioni evidenti, lunghezza e presenza dei quattro paragrafi, ma **non è un correttore grammaticale universale**.

Il laboratorio di prosa libera applica invece `assess_model_copy()`, che esamina il *candidato* di Qwen3 senza mai promuoverlo al testo fattuale.

## Risultati di test

- **149 test editoriali e di controllo, 49 test del Research Engine, 198 test automatici totali superati.**
- CI collegata a sei documenti ufficiali ISTAT (91 pagine e 70 osservazioni validate nella fase precedente).
- Esito operativo della pipeline: **16 idee editoriali**, **6 articoli controllati di quattro paragrafi**, 6 stati `review_required`, **0 pubblicazioni**.
- Il laboratorio Qwen dispone di test di simulazione di errore, ma **non è stato ancora eseguito il modello reale sul Surface dell'utente**. La qualità stilistica di Qwen non si può dichiarare accettata prima di analizzare quelle uscite.

## Istruzioni operative — Surface Pro 8, una procedura alla volta

Aggiornare il branch:

```powershell
cd C:\Users\fiori\ISTAT-PULSE-AI-TEST
git pull origin feat/pulse-editorial-ai-1.0
```

Con i sei workbench prodotti dai moduli del Research Engine, creare articoli di base **senza AI**:

```powershell
py scripts/pulse_editorial_publication.py --input workbench/turismo_q2_2026.json --additional-input workbench/lavoro_agosto2026.json workbench/prezzi_agosto2026.json workbench/popolazione_2025.json workbench/istruzione_2024.json workbench/ambiente_2024_2025.json --output workbench/edizione_editoriale_3_5.json
```

Ripetere questo comando con `--use-local-ai` **solo dopo aver verificato gli input** per consentire a Qwen di scegliere la struttura.

Per la vera prova della scrittura italiana di Qwen (inizialmente **due** articoli, per non caricare troppo il Surface):

```powershell
py scripts/pulse_editorial_local_writer.py --input workbench/edizione_editoriale_3_5.json --output workbench/riscritture_qwen_3_5.json --limit 2
```

Il JSON della riscrittura contiene separati testo approvato e proposta Qwen. Le proposte restano non pubblicabili finché non siano state valutate semanticamente.

## Criterio di chiusura della fase 2

**Implementazione software e controlli per i sei ambiti: COMPLETATI e verificati in CI.**  
**Qualità linguistica reale Qwen3 4B su hardware dell'utente: DA CONVALIDARE.**

Il punto 2 non deve essere presentato come “AI eccellente validata sul campo” finché mancano la prova con Ollama locale e la valutazione di riscritture reali. Un modello da 4B può fornire spunti di stile utili, ma non va trasformato nell'arbitro della verità statistica.

Il successivo **PULSE Fact Checker** potrà ampliare questa architettura ad altre tipologie di frasi, senza rimuovere il divieto di pubblicazione non verificata.
