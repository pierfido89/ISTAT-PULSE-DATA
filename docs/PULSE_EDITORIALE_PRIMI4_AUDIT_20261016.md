# PULSE — verifiche problemi editoriali 1–4 (16 ottobre 2026)

Questa nota accompagna il ramo di sviluppo isolato creato da `feat/pulse-editorial-revisions-withdraw-rollback-20261012`. **Non modifica `main`** e non autorizza pubblicazioni.

## Evidenza di partenza
Il repository privato `ISTAT-PULSE-EDITORIAL-RESULTS` contiene un benchmark di 10 bozze (86–105 parole), 0 testi lunghi nel limite 250–400 parole, 0 revisioni semantiche certificate, 0 articoli pubblicabili nel report dell'11/10/2026. Il motore di ricerca differenzia 27 fonti catalogate e 6 PDF ufficiali precedentemente verificati: le due quantità non sono intercambiabili.

## Implementazione nuova (pacchetto esterno di sviluppo, non ancora incorporato in questo branch)
- `quality.py`: controllo 250–400 parole, 4–5 paragrafi, ripetizioni, causalità e prompt di riscrittura con prove per ogni frase.
- `factcheck.py`: controllo per singola frase, confronto indicatori, periodi, luoghi, unità, numeri, variazioni e revisione indipendente.
- `sources.py` e `adapters.py`: 27 profili e lettura rigorosa di file CSV, Excel, JSON, GeoJSON, PDF tabellari, NetCDF opzionali.
- `attest.py`: due firme HMAC separate di fonte e revisione semantica.
- `gate.py`: quarantena automatica e uscita atomica **solo verso anteprima protetta**. Pubblicazione remota disattivata.
- Test: **51/51 test offline**, senza fonti esterne, API o dati pubblicati.

## Stato onesto
**I primi quattro problemi non sono risolti in produzione.** Le 10 riscritture genuine richiedono i PDF originali; nessuna delle 27 fonti e' stata certificata live da questa esecuzione; gli attestati veri richiedono due verifiche indipendenti. I 51 test dimostrano che i moduli di controllo funzionano con fixture sintetiche, non che i dati reali siano stati verificati.

Per integrare il codice, utilizzare il pacchetto esterno `PULSE-EDITORIALE-PROBLEMI-1-4-CODICE-TEST-BIBBIA-20261016.zip` sul PC, che crea un **altro ramo locale** e lancia i test senza push automatico. Non dichiarare attivo il servizio prima di una prova end-to-end su file veri e client Android.

Nessuna APK, Worker, `main` o feed pubblico e' stata alterata.
