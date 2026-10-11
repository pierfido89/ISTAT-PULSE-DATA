# PULSE Editorial Intelligence 3.5 — Sistema editoriale e laboratorio Qwen locale (Qwen3.5 9B)

**Data:** 11 ottobre 2026  
**Ramo sperimentale:** `feat/pulse-editorial-ai-1.0` — [PR #13](https://github.com/pierfido89/ISTAT-PULSE-DATA/pull/13)  
**Stato (aggiornamento sul campo 10 ottobre 2026):** sei PDF ISTAT verificati; **Qwen3 4B eseguito realmente sul Surface Pro 8 in due prove successive**. La prima proposta copiava i paragrafi, la seconda li ha riscritti ma con difetti di italiano, interpretazioni non giustificate e una chiave JSON `lead` aggiuntiva. **Qualità giornalistica NON ancora approvata**. Entrambi gli errori sono stati registrati come test di regressione; nuove correzioni del controllo in fase di convalida. Nessuna pubblicazione automatica, APK o API a pagamento.

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

**B. Qwen3.5 9B come regista editoriale**  
Nello stesso modulo, con `--use-local-ai`, il modello già presente su Ollama sceglie solo campi chiusi: `story_id`, `voice` (notizia, analisi, divulgazione), `focus` (fenomeno, confronto, metodo), `order` (comparazione, spiegazione). Se propone un ID inesistente, campi aggiuntivi o una struttura non valida, il piano viene scartato e subentra quello verificato.

Il modello organizza l'articolo e ne sceglie l'impostazione, mentre le affermazioni fattuali continuano a essere ricostruite indipendentemente.

**C. Qwen3.5 9B scrive in italiano libero, ma in quarantena**  
`scripts/pulse_editorial_local_writer.py`

Il modello può davvero proporre una riscrittura dei quattro paragrafi. Il sistema controlla:

- JSON con **schema Ollama esplicito** per imporre soltanto `headline` e quattro `paragraphs`, senza campi aggiuntivi (il verificatore indipendente resta obbligatorio);
- numeri introdotti o numeri fondamentali della fonte omessi;
- esempi di rivendicazioni causalistiche, primati o previsioni non documentati;
- URL estranei alla fonte;
- paragrafi duplicati o fortemente ridondanti;
- lunghezza ragionevole;
- regressioni grammaticali note, compresi `I arrivi`, `sui arrivi`, `i clienti si verificano` e l'uso improprio di `stanzialità`;
- imitazioni quasi letterali del testo originale e omissioni nel titolo della categoria di clientela;
- affermazioni non autorizzate su cambiamenti delle abitudini/comportamenti dei clienti ricavate impropriamente dal rapporto arrivi-presenze;
- **diagnosi cumulativa**: un campo aggiuntivo `lead` non interrompe l'analisi degli altri difetti (il candidato resta rifiutato).

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

- Test prima della migrazione: **155 editoriali, 49 Research Engine = 204 test superati**. Dopo la migrazione al modello 9B, nuove verifiche automatiche garantiscono che il payload invii `think: false` al livello corretto dell'API Ollama; controllare l'esito CI del commit più recente.
- CI collegata a sei documenti ufficiali ISTAT (91 pagine e 70 osservazioni validate nella fase precedente).
- Esito operativo della pipeline: **16 idee editoriali**, **6 articoli controllati di quattro paragrafi**, 6 stati `review_required`, **0 pubblicazioni**.
- **Qwen3 4B locale è stato realmente eseguito due volte sul Surface** sui primi due articoli. Prima prova: nel caso turismo, nessuna riscrittura dei quattro paragrafi, solo modifica del titolo. Seconda prova: prosa parzialmente nuova, ma campi JSON non ammessi, lessico improprio e indebita inferenza sul comportamento dei clienti. **Entrambe le proposte sono state respinte a seguito di revisione.**
- Le anomalie delle prove reali hanno generato test automatici di regressione e correzioni alla generazione. Il nuovo JSON Schema Ollama e il controllo semantico euristico devono essere **riprovati sul modello reale**: il superamento dei test di simulazione non è una convalida della qualità del modello.

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
**Qwen3 4B ha mostrato errori reali nella scrittura ed è stato disinstallato. Qwen3.5 9B è ora il modello locale di riferimento.** Ha superato una prova preliminare di due frasi con ragionamento disattivato, ma deve ancora sostenere la valutazione degli articoli completi. La Fase 2 non è ancora validata sul piano della qualità giornalistica.

Il punto 2 non deve essere presentato come “AI eccellente validata sul campo” finché mancano la prova con Ollama locale e la valutazione di riscritture reali. Un modello da 4B può fornire spunti di stile utili, ma non va trasformato nell'arbitro della verità statistica.

Il successivo **PULSE Fact Checker** potrà ampliare questa architettura ad altre tipologie di frasi, senza rimuovere il divieto di pubblicazione non verificata.

## Registro delle prove reali — 10 ottobre 2026

**Prova 1 (Qwen3 4B, turismo):** 4 paragrafi pressoché identici al testo di partenza. Il precedente controllo li considerava pronti solo per revisione; il nuovo controllo li respinge per `insufficient_editorial_transformation`. Titolo nuovo ma privo dell'esplicito riferimento ai clienti residenti.

**Prova 2 (Qwen3 4B, turismo):** riscrittura più autonoma, ma aggiunge `lead` alle due chiavi richieste e contiene «i clienti residenti si verifichino» e «stanzialità». Inoltre la frase sull'«evoluzione del comportamento dei clienti residenti» è un'inferenza non documentata. Il rifiuto automatico dovuto al campo aggiuntivo era corretto; è stato migliorato affinché restituisca contemporaneamente anche le motivazioni stilistiche/semantiche.

**Patch di revisione:** JSON Schema inviato a Ollama; istruzioni di prosa naturale e fedeltà statistica; controlli indipendenti su anomalie emerse; regressioni dedicate. È proibita la promozione automatica del testo libero, anche quando tutti i controlli automatici passano.

**Limite del metodo:** non esiste ancora un correttore capace di certificare integralmente la grammatica e la veridicità semantica di una prosa libera. Queste regole intercettano esempi riconoscibili ma non tutti gli errori possibili. Serve revisione umana con la fonte originale.

## Migrazione a Qwen3.5 9B — 11 ottobre 2026

L'utente ha disinstallato `qwen3:4b-instruct` dal proprio Surface Pro 8 (RAM 16 GB) e ha installato `qwen3.5:9b` tramite Ollama. Alla prima richiesta la modalità predefinita con ragionamento ha generato un lunghissimo testo intermedio anziché una risposta breve. La successiva prova locale con `ollama run qwen3.5:9b --think=false` ha prodotto in italiano due frasi corrette sul rapporto tra arrivi, presenze e permanenza media per arrivo, senza cifre inventate: **esito preliminare promettente, non sostitutivo della valutazione editoriale**.

**Modifiche sul solo branch sperimentale dei dati:** `MODEL_DEFAULT` ora è `qwen3.5:9b` nel client `scripts/pulse_editorial_ai.py`, ripreso dai moduli `pulse_editorial_local_writer.py`, `pulse_editorial_publication.py` e `pulse_editorial_pairs.py`. Ogni richiesta Ollama locale in questi moduli usa `"think": false` **come campo principale della richiesta**, non dentro `options`, per evitare il consumo di token nel ragionamento interno. Rimangono JSON Schema per le riscritture, 4 paragrafi, divieto di inserire fatti non supportati e revisione umana obbligatoria. La fase attuale opera esclusivamente sui JSON dei workbench, non modifica la produzione Android e non pubblica articoli.

**Prossimo test necessario:** rieseguire la riscrittura dopo i controlli di qualità rafforzati, conservando lo storico delle prove. La valutazione umana resta obbligatoria e non si può assegnare un giudizio definitivo al 9B sulla sola prova del turismo.


## Prima prova articolo completo con Qwen3.5 9B — 11 ottobre 2026

**Contesto:** l'utente ha utilizzato `scripts/pulse_editorial_local_writer.py` su `workbench/edizione_editoriale_3_5.json` con `--limit 1` e un file di output autonomo `workbench/riscritture_qwen35_9b_v1.json`. Generata una proposta con `headline` e quattro stringhe `paragraphs` nel JSON richiesto; nessuna pubblicazione. Il modello ha conservato i quattro valori principali del turismo alberghiero per i residenti nel II trimestre 2026 (arrivi 12.464.038, -4,3%; presenze 32.162.873 notti, +1,7%), la comparazione annua e la permanenza media per arrivo, circa 2,58 notti (elaborazione PULSE).

**Esito macchina pre-correzione:** `status: needs_human_semantic_review`, `failures: []`, quattro paragrafi riscritti, con l'avvertenza che il titolo era identico all'originale. **La revisione umana ha evidenziato tre criticità:** «dai ospiti» anziché «dagli ospiti», «il totale delle notti aumentato» invece di una costruzione corretta, e «i clienti residenti hanno prolungato la propria permanenza media» che può attribuire a persone o scelte individuali una variazione misurata soltanto sul rapporto aggregato presenze/arrivi.

**Giudizio editoriale preliminare:** circa **6,5/10** su questa singola prova (valutazione umana orientativa, non PULSE Score). Il nuovo modello è più promettente del precedente, ma **non idoneo alla pubblicazione automatica**. Sono state aggiunte regole di controllo grammaticali mirate, un controllo conservativo sulla confusione fra media aggregata e scelte individuali e test di regressione basati sui paragrafi realmente prodotti dal 9B. Le regole non garantiscono una correzione linguistica universale. Il modello deve superare nuove prove su turismo e sugli altri ambiti senza falsi positivi significativi, e comunque con revisione umana.


## Seconda prova articolo completo con Qwen3.5 9B — 11 ottobre 2026

**Dati prova locale sul Surface:** output preservato in `workbench/riscritture_qwen35_9b_v2.json`, un articolo turismo su clienti residenti nel secondo trimestre 2026; nessuna pubblicazione. Quattro paragrafi rielaborati. Valutazione editoriale umana indicativa **6/10**, inferiore alla V1 (6,5/10), perché le correzioni istruzionali da sole non hanno eliminato gli errori di significato.

**Esito del controllore precedente:** `status: rejected`, solo `core_lead_numeric_claims_omitted:2025`. Correttamente mancava l'anno esplicito del periodo di confronto rispetto al II trimestre 2025. L'articolo conteneva però altri quattro problemi: «gli arrivi indicano il numero di persone» senza chiarire che si contano ingressi/check-in e non persone uniche; «2,58 notti per ospite» invece di «per arrivo»; «notti offerte» al posto delle presenze effettive; «i clienti residenti hanno prolungato la propria permanenza» confonde una media aggregata con azioni di singoli clienti.

**Migliorie del controllore:** estesi i pattern di controllo per le attribuzioni individuali e introdotti tre indicatori di errore specifici per definizioni ISTAT dei flussi alberghieri e media per arrivo. Aggiunto un test di regressione con **i paragrafi esatti prodotti nella V2**, per pretendere che il controllore segnali le **cinque** criticità anziché solo quella sull'anno, più un test positivo su formulazioni aggregate corrette. Rafforzato il prompt per mantenere entrambi gli anni di confronto, distinguere notti effettive da capacità offerta e evitare spiegazioni generiche. Queste regole non possono sostituire il controllo editoriale umano né garantiscono qualità linguistica universale. **Prossimo passo: validare test automatici e provare V3 in un nuovo file JSON senza sovrascrivere V1/V2.**
