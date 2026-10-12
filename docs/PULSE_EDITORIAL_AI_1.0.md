# PULSE Editorial AI 1.0 — Workbench locale, zero API a pagamento

**Stato:** prima implementazione sperimentale nel ramo feat/pulse-editorial-ai-1.0. Non è nell'APK e non è collegata alla pubblicazione automatica.

## Obiettivo

Dal motore PULSE Deep Reading l'AI riceve solo evidenze già strutturate:
indicatore, unità, segmento, periodo, valore, variazione dichiarata,
URL della fonte primaria, hash SHA-256 e posizione nel documento.
Scrive una BOZZA originale. Il controllo meccanico cerca numeri non
presenti nell'evidenza, dichiarazioni arbitrarie di record e causalità,
ma NON sostituisce una revisione umana.

## Costi

- Software e API AI: **0 euro**.
- Ollama locale su 127.0.0.1:11434; nessun endpoint cloud selezionabile.
- Modello iniziale Qwen3 4B Instruct, circa 2,5 GB di download, Apache-2.0.
- Sul Surface Pro 8 da 16 GB RAM è una prova tecnica: velocità da misurare.
- Alternative a consumo minore: qwen3:1.7b (qualità ancora da confrontare).
- Energia elettrica e banda per il download rimangono costi ordinari.

## Avvio Windows — PowerShell

1. Installa Ollama gratis: https://ollama.com/download/windows
2. Apri PowerShell ed esegui:

       ollama pull qwen3:4b-instruct
       ollama list

3. Scarica il ramo di sviluppo:

       git clone -b feat/pulse-editorial-ai-1.0 https://github.com/pierfido89/ISTAT-PULSE-DATA.git
       cd ISTAT-PULSE-DATA
       py -m pip install pdfplumber

4. Prepara un workbench dal PDF ufficiale ISTAT del II trimestre 2026:

       py scripts/pulse_editorial_sample.py --output workbench/turismo_q2_2026.json

5. Conta i fenomeni verificabili senza avviare Ollama:

       py scripts/pulse_editorial_ai.py --input workbench/turismo_q2_2026.json --inspect

6. Controlla la disponibilità del modello:

       py scripts/pulse_editorial_ai.py --check-model

7. Genera le prime 3 bozze private (potrebbe richiedere tempo su CPU):

       py scripts/pulse_editorial_ai.py --input workbench/turismo_q2_2026.json --output workbench/bozze_q2_2026.json --limit 3

Apri il JSON delle bozze: quality.status indica "review_required" o
"rejected". Anche una bozza che supera l'audit numerico deve essere
letta, corretta e approvata da una persona prima di un futuro rilascio.
Non inserirla in data/news/articles.json.

## Regole vincolanti

1. Solo documenti con fonte statistica primaria HTTPS ed evidenze
   complete (URL coerente, hash SHA-256, pagina/riga, metodo, periodo).
2. Più indicatori da uno stesso documento diventano candidati distinti,
   ma senza produrre articoli automaticamente nel Radar.
3. In ingresso al modello si invia solo un oggetto dati ristretto,
   NON l'intero HTML o PDF contenente istruzioni non affidabili.
4. Numeri, periodi e percentuali non supportati vengono rigettati.
5. Le parole di causa certa, record storico o previsione non verificata
   fanno fallire l'audit. Serve anche controllo semantico umano.
6. I pattern statistici certificati restano un compito del Quality Gate.
   La AI non assegna pattern né un PULSE Score da sola.
7. Classificazione: riuso della Tassonomia 1.0 con stati provvisori,
   senza attribuire all'AI una certificazione dei temi.
8. Il file di origine resta invariato, e l'output è un archivio isolato
   di sole bozze: publication_status = draft_only.
9. Un errore di Ollama non attiva un servizio a pagamento.
10. L'esecuzione può avvenire quando il Surface è acceso, senza
    influire sul funzionamento delle schede Android.

## Metodo di valutazione

Il primo esperimento serve a misurare tre articoli generati davvero
dal modello e la qualità dei controlli. Il successivo confronto sarà
su 20 PUBBLICAZIONI DIFFERENTI, non su 20 righe dello stesso prospetto.
Metriche: percentuale di bozze scartate, falsi positivi nell'audit,
correttezza editoriale valutata da persona, pertinenza delle categorie,
tempo e memoria consumati e costo API (0 euro).

I test GitHub Actions sostituiscono la risposta di Ollama con un mock,
per evitare chiamate AI e costi. Non dimostrano che Qwen sia già
installato sul PC dell'utente, né che la sua qualità sia soddisfacente.

## Correzione dopo il primo test Qwen3 (10 ottobre 2026)

Il primo testo generato sul Surface, sul turismo Q2 2026, aveva un titolo
adeguato ma deduceva, senza prove, un «maggiore utilizzo del servizio da
parte di soggetti residenti o di gruppi più stabili» dai soli aggregati.
Aveva inoltre descritto i dati come «disponibili per ISTAT PULSE»,
formulazione che può confondere il prototipo con la fonte primaria.

**Modifica applicata:** prompt interno v1.1, con divieto esplicito di
inferenze su popolazioni, gruppi, durata media, comportamenti, cause e
titolarità delle rilevazioni non documentate. Il modulo
`scripts/pulse_editorial_inference.py` esegue un secondo controllo
deterministico, contestuale ai dati forniti al modello:

- Reiezione delle affermazioni su residenti/non residenti se non coerenti
  con il segmento statistico della singola evidenza.
- Reiezione delle ipotesi su «gruppi più stabili» o altre categorie
  demografiche non presenti nella fonte strutturata.
- Reiezione della «permanenza media» se non esiste un confronto omogeneo
  verificato di arrivi e presenze.
- Divieto di trasformare gli arrivi in numero di persone/turisti unici.
- Nessuna possibilità di introdurre un indicatore secondario non incluso
  nello specifico candidato editoriale.
- Divieto di attribuire a ISTAT PULSE il ruolo della fonte che rileva
  o produce le statistiche.

I test di regressione riproducono l'errore realmente osservato, verificano
che venga respinto e che i riferimenti ai residenti **restino ammessi**
quando le tabelle li documentano esplicitamente.

**Limite dichiarato:** è un controllo lessicale mirato, NON una verifica
semantica infallibile. Frasi nuove, sinonimi imprevisti, correlazioni
spurie e sfumature linguistiche possono sfuggire al filtro: le bozze
restano `review_required` anche quando non vengono rilevati errori.
La prossima prova con Qwen3 reale va eseguita sul Surface aggiornando il
repository; i test in GitHub Actions NON avviano un modello Qwen.

## Diagnosi delle prime tre bozze locali: correzione v1.2

Il file `bozze_q2_2026.json` generato realmente sul Surface ha prodotto
3 bozze respinte. Non era solo un problema del modello: il controllo v1.1
aveva falsi rifiuti su tre casi legittimi, ma ometteva altri errori reali.

**Errori rilevati e rimedi verificabili:**

- `4,3%` / `0,9%` dopo «calo del» sono magnitudini corrette per
  variazioni ufficiali negative. Corretto il parser dei numeri italiani
  e aggiunta una verifica INDIPENDENTE della direzione: «aumento del
  4,3%» continua a essere respinto per una variazione ufficiale -4,3%.
- Il riferimento al 2025, quando l'evidenza ufficiale indica una
  variazione tendenziale del Q2 2026, è ammesso. Non vengono però
  fabbricati valori assoluti 2025.
- Un articolo che scrive «arrivi, non presenze» non viene più respinto
  come se avesse riportato un secondo indicatore, mentre una vera
  affermazione su «arrivi in calo e presenze in crescita» senza due
  evidenze separate continua a essere bloccata.
- **Quadrimestre** al posto di **trimestre** produce ora un rifiuto
  esplicito, indipendentemente dal fatto che i numeri siano corretti.
- **Bed & breakfast** non può essere sostituito agli «esercizi
  alberghieri» della fonte; il nome della struttura viene controllato.
- Il totale Q2 2026 **15.184.700** è errato rispetto al dato ufficiale
  **15.184.702**: anche il minimo arrotondamento dei totali resta
  respinto.
- La categoria `POP-01` risultava dal termine «residenti» nel
  testo generato. Il segmento ufficiale alberghiero con indicatori
  `Arrivi` / `Presenze` è ora associato alla sottocategoria
  turistica `SOC-04`, con classificazione comunque provvisoria.
- Corretto il prompt per scrivere «clienti residenti negli esercizi
  alberghieri», evitando «alberghi residenti», strutture per soli
  non residenti e formulazioni ripetitive.

**Tentativo correttivo locale:** con l'impostazione predefinita,
una bozza respinta può essere riscritta una sola volta da Qwen3, usando
come feedback esclusivamente i codici degli errori del controllo.
`quality.attempt_history` conserva le criticità delle generazioni,
`generator.attempts` indica quanti tentativi sono stati effettuati.
Il secondo tentativo NON aggira le regole: se resta scorretto viene
respinto. Il comportamento si disattiva con `--max-retries 0`.
Un tentativo in più può richiedere minuti sul Surface ma non comporta
addebiti per API o servizi cloud.

**Aggiornamento della copia Windows già presente:**

    cd C:\Users\fiori\ISTAT-PULSE-AI-TEST
    git pull origin feat/pulse-editorial-ai-1.0
    py -m unittest discover -s tests -p "test_pulse_editorial*.py" -v
    py scripts/pulse_editorial_ai.py --input workbench/turismo_q2_2026.json --output workbench/bozze_q2_2026_v12.json --limit 3

Al termine allegare il nuovo file `bozze_q2_2026_v12.json`.
Il precedente file rimane intatto per confrontare risultati.
**Nessuna bozza è pubblicabile automaticamente**; `review_required`
significa solo che non sono emersi errori nei controlli implementati,
NON che sia stato dimostrato il rigore semantico completo. La qualità
linguistica e statistica del nuovo prompt su Qwen3 reale va ancora
verificata con il test sul Surface.

## Secondo test reale sul Surface: v1.2 -> proposta v1.3

Il test del 10 ottobre 2026 ha generato **3 bozze, 1 da revisionare,
2 respinte**. Dal JSON utente `bozze_q2_2026_v12.json` risultano:

- **Residenti, arrivi:** 12.464.038 (-4,3%), segno e quantità corretti,
  ma Qwen ripeteva i numeri, usava "un'abbassamento" (errore
  grammaticale) e aggiungeva un elenco di gruppi e strutture escluse.
- **Residenti, presenze:** 32.162.873 (+1,7%): il gate statistico
  non segnalava errori ma il testo era burocratico, ridondante e
  stilisticamente modesto. `review_required` NON è un'approvazione
  editoriale.
- **Non residenti, arrivi:** 15.184.702 (-0,9%): numeri corretti, ma
  titolo e lead attribuivano erroneamente i dati ai "residenti".
  Il Quality Gate li aveva giustamente respinti.

**Radice del problema:** il prompt v1.2 elencava numerosi esempi
negativi (gruppi, categorie e alloggi da non menzionare). Il modello
finiva per citarli nei testi anche quando la tabella non ne parlava.

### Modifiche v1.3

1. `scripts/pulse_editorial_brief.py`: prepara da evidenze
   strutturate una scheda POSITIVA con soggetto canonico, popolazione,
   struttura ricettiva, periodo corrente/comparativo, totale e variazione
   nello stesso verso del dato. Esempio concreto: "arrivi dei clienti
   non residenti negli esercizi alberghieri".
2. Prompt riscritto: usare soltanto la scheda, non fare elenchi di
   esclusioni o frasi sui "dati senza arrotondamenti"; limitare i testi
   a una micro-notizia compatibile con **una sola serie**. Non attribuire
   a un solo indicatore una conclusione su altri dati.
3. Controllo titolo/lead: l'indicatore e la popolazione devono essere
   coerenti con la tabella, non soltanto nella sezione `body`.
4. Errore grammaticale concreto `un'abbassamento` esplicitamente
   respinto.
5. `scripts/pulse_editorial_style.py`: riporta separatamente
   `quality.editorial_warnings` per burocratese, ridondanza di totali
   e percentuali espresse in forme grammaticalmente poco naturali.
   Questi rilievi stilistici NON certificano la qualità, ma indicano
   gli aspetti da rileggere.
6. Una sola riscrittura locale, eventualmente anche per gli avvisi
   stilistici. Se il tentativo successivo peggiora o introduce errori,
   il generatore conserva la bozza più sicura. Sono registrati
   `generator.attempts`, `generator.selected_attempt` e
   `quality.attempt_history`.
7. Test di regressione riproducono gli errori del primo e secondo
   test reale. La CI usa finte risposte Ollama, non il modello vero.

### Riprova su Windows senza reinstallare

Da PowerShell:

    cd C:\Users\fiori\ISTAT-PULSE-AI-TEST
    git pull origin feat/pulse-editorial-ai-1.0
    py -m unittest discover -s tests -p "test_pulse_editorial*.py" -v
    py scripts/pulse_editorial_ai.py --input workbench/turismo_q2_2026.json --output workbench/bozze_q2_2026_v13.json --limit 3

Caricare `bozze_q2_2026_v13.json` nella conversazione per una
**verifica editoriale umana**. Non confondere miglioramento dei test
automatici con prova reale di miglioramento linguistico. Nessuna
integrazione nell'APK, nessuna pubblicazione autonoma e costo API 0 €.

## Terzo test reale sul Surface: v1.3 e aggiornamento v1.4

Il JSON originale \`bozze_q2_2026_v13.json\` fornito dall'utente contiene
**3 bozze, tutte \`review_required\` e senza errori segnalati**. Le
evidenze primarie per i tre indicatori sono state conservate correttamente:

- Residenti, arrivi alberghieri Q2 2026: 12.464.038; -4,3% YoY.
- Residenti, presenze alberghiere Q2 2026: 32.162.873; +1,7% YoY.
- Non residenti, arrivi alberghieri Q2 2026: 15.184.702; -0,9% YoY.

**Esito editoriale umano: 0/3 pronti alla pubblicazione come articoli.**
Il primo testo ripeteva soltanto il calo degli arrivi, il secondo
scriveva «confermando una tendenza positiva» senza una serie storica
sufficiente, il terzo affermava «senza variazioni significative» per
la composizione delle strutture senza informazioni o test statistici.
Queste ultime due sono inferenze da bloccare, non semplici difetti
stilistici. Il numero 3/3 superato dal Quality Gate v1.3 NON
significava tre articoli scientificamente ed editorialmente validi.

**Correzioni v1.4:**

1. Controllo deterministico che blocca l'attribuzione di **trend
   pluriennali** non dimostrati, distinguendola correttamente
   dall'espressione tecnica «variazione tendenziale».
2. Blocco delle affermazioni sulla **significatività statistica**,
   positiva o negativa, senza prova specifica, e delle conclusioni
   non fondate sull'assenza di cambiamenti nella composizione delle
   strutture o categorie di clienti.
3. Avvisi separati per titoli che riportano solo un'etichetta
   dell'indicatore e testi che ripetono la variazione senza aggiungere
   informazioni. Gli avvisi non sono una certificazione stilistica.
4. In \`pulse_editorial_brief.py\` aggiunta una definizione
   controllata dell'indicatore (arrivi o presenze) affinché il
   modello possa spiegare un concetto corretto, anziché espandere
   il paragrafo con inferenze generiche.
5. I documenti generati da **una sola evidenza indipendente**
   ricevono \`editorial_format=single_finding_statistical_brief\`
   e \`full_article_evidence_status=requires_multiple_independent_findings\`.
   Restano bozze e non entrano automaticamente nell'app.
6. Test di regressione specifici riproducono le tre uscite effettive
   della v1.3; il modello vero dovrà essere rieseguito sul Surface
   per valutare la qualità linguistica v1.4.

**Decisione progettuale:** invece di inseguire solo punteggi
«3 su 3», la successiva capacità di maggior valore sarà riunire
in un'unica storia **due o più indicatori indipendenti e
comparabili** dallo stesso PDF (per esempio arrivi e presenze
per lo stesso territorio, categoria e trimestre) e controllare
numericamente tutte le affermazioni. Una singola variazione
resterà una scheda/flash statistica, non verrà falsamente
promossa ad articolo approfondito.

**Riprova Surface, senza costi API e senza APK:**

    cd C:\Users\fiori\ISTAT-PULSE-AI-TEST
    git pull origin feat/pulse-editorial-ai-1.0
    py -m unittest discover -s tests -p "test_pulse_editorial*.py" -v
    py scripts/pulse_editorial_ai.py --input workbench/turismo_q2_2026.json --output workbench/bozze_q2_2026_v14.json --limit 3


## Quarto test reale v1.4: diagnosi e regressioni

Il file effettivo generato dal Surface, `bozze_q2_2026_v14.json`,
ha prodotto 3 bozze tutte respinte, con due tentativi per bozza.
I valori di input ISTAT, i segmenti e la categoria SOC-04 sono rimasti
coerenti, ma il risultato NON è idoneo alla pubblicazione.

**Diagnosi precisa:**

- Arrivi residenti (-4,3%) e non residenti (-0,9%):
  titolo e lead numericamente e direzionalmente corretti ma il corpo
  erroneamente dice «periodo di due mesi». Un trimestre è tre mesi.
  La versione v1.4 non intercettava questa affermazione falsa.
- Il vecchio lessico del controllo non riconosceva `calano`:
  il codice `unqualified_yoy_direction` era un falso allarme.
  Il controllo stilistico non riconosceva `calano` / `aumentano`
  come verbi validi dei titoli, segnando erroneamente
  `headline_only_labels_indicator`.
- Presenze residenti (+1,7%): Qwen ha aggiunto un totale
  **31.738.000 notti nel 2025** assente dall'evidenza allegata.
  Il rifiuto `unsourced_numbers:31.738.000` era corretto.
  Non è consentito ricostruire un totale precedente da una
  percentuale pubblicata arrotondata.

**Correzioni dopo la diagnosi:** ampliato il riconoscimento dei
verbi coniugati (`calano` / `aumentano`), con protezione contro
segni invertiti; blocco di `periodo di due mesi` in un Q2,
oltre a `bimestre` e `quadrimestre`. Aggiunti test di
regressione esattamente basati sui tre testi dell'utente,
per dimostrare che i **falsi allarmi scompaiono ma i veri
errori restano bloccanti**.

Non chiedere di rigenerare subito le stesse tre righe per
ottenere artificialmente uno stato "review_required". La
loro natura rimane `single_finding_statistical_brief` e il
problema sostanziale non è stato risolto da più prompt:
per articoli giornalistici serviranno raggruppamenti
coerenti di evidenze statistiche indipendenti, non un
testo inventato per riempire il paragrafo.

## Rapporto con la Bibbia tecnica

Il documento ufficiale e vivo
ISTAT_PULSE_Bibbia_Tecnica_v4.3.6_Logo_Originale deve registrare la AI
come modulo in sperimentazione, documentare requisiti e Quality Gate e
mantenere separata la v4.3.6 storica dalla prossima APK. Non creare
nuove versioni incompatibili della Bibbia: integrare sempre il dossier.
Prototipo indipendente, non prodotto ufficiale ISTAT.

Autoria progettuale: Ludovico Fiori. Assistenza: ChatGPT di OpenAI.
