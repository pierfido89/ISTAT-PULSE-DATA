# ISTAT PULSE — Politica permanente del dossier tecnico

**Documento vivo di riferimento:** `ISTAT_PULSE_Bibbia_Tecnica_v4.3.6_Logo_Originale`, copertina con logo originale fornito dall'ideatore Ludovico Fiori. L'edizione iniziale è basata sulla release Android 4.3.6; integrazioni posteriori devono sempre indicare data, stato e versione applicativa. Non attribuire retroattivamente alla release 4.3.6 funzioni introdotte dopo.

## URL stabile per l'app

`https://raw.githubusercontent.com/pierfido89/ISTAT-PULSE-DATA/main/docs/ISTAT_PULSE_Bibbia_Tecnica.pdf`

Il file `docs/ISTAT_PULSE_Bibbia_Tecnica.pdf` dovrà essere caricato sul ramo `main` **prima di rilasciare la prossima APK**. Tale nome è stabile: aggiornare il PDF a ogni rilascio significativo senza modificare l'URL nell'app. Conservare, se utile, una copia immutabile di ciascuna edizione con nome che includa data/versione.

**Blocco pre-release:** non pubblicare un APK con pulsante di download finché l'URL non restituisce HTTP 200/206 e un documento che inizia con `%PDF`. Un test manuale di download su Android deve verificare che il file salvato sia apribile e completo.

## Processo a ogni modifica dell'app

1. Analizzare il codice effettivamente modificato e i relativi contratti dati.
2. Aggiornare la Bibbia tecnica senza sostituire la base storica con spiegazioni approssimative.
3. Indicare implementato, operativo allo snapshot, parziale oppure roadmap.
4. Verificare logo, impaginazione, indice, capitoli, tabelle e pagine del PDF.
5. Pubblicare il PDF aggiornato al percorso stabile su `main`.
6. Verificare download e apertura dalla sezione **ALTRO > Bibbia tecnica**.
7. Nella descrizione della release segnalare gli aggiornamenti documentali.

## Tassonomia ufficiale 1.0

- Dizionario autorevole: `data/taxonomy/pulse_taxonomy_v1.json`.
- Copia distributiva per l'app: `ISTAT-PULSE/app/src/main/assets/pulse_taxonomy_v1.json`.
- **7 macroaree / 57 sottocategorie**, codici stabili; un tema principale, fino a due secondari.
- Territorio, pattern statistico, fonte e PULSE Score sono dimensioni distinte.
- Censimenti sono tipologie documentali; Focus sono percorsi trasversali, non macroaree.
- Le attribuzioni deterministiche su testo parziale restano **provvisorie** e, nei casi ambigui, **NON_CLASSIFICATO**.
- PULSE Editorial AI può suggerire e arricchire; non può alterare valori numerici o sostituire verifiche dati.

## Tracciabilità editoriale

Ogni classificazione: `taxonomy_version`, `primary_category`, `secondary_categories`, `classification_method`, `classification_status`, `classification_reason`, territori distinti, source URL. Qualunque cambio di dizionario che modifichi i codici richiede migrazione esplicita.

**Identità:** prototipo indipendente di Ludovico Fiori, con assistenza allo sviluppo e alla documentazione di ChatGPT di OpenAI. Non è un prodotto ufficiale, sponsorizzato o approvato dall'ISTAT.
