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

## Rapporto con la Bibbia tecnica

Il documento ufficiale e vivo
ISTAT_PULSE_Bibbia_Tecnica_v4.3.6_Logo_Originale deve registrare la AI
come modulo in sperimentazione, documentare requisiti e Quality Gate e
mantenere separata la v4.3.6 storica dalla prossima APK. Non creare
nuove versioni incompatibili della Bibbia: integrare sempre il dossier.
Prototipo indipendente, non prodotto ufficiale ISTAT.

Autoria progettuale: Ludovico Fiori. Assistenza: ChatGPT di OpenAI.
