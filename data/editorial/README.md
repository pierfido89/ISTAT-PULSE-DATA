# PULSE — canale editoriale approvato (prototipo)

Questa cartella è un **feed pubblico sperimentale**, separato dal repository PRIVATO `pierfido89/ISTAT-PULSE-EDITORIAL-RESULTS` e dal radar Notizie.

- `approved_articles.json` resta **vuoto** fino ad approvazione umana esplicita di un articolo.
- Le bozze ChatGPT restano in `drafts/` del repository privato e **non** vanno esposte in URL pubblici, APK o GitHub Actions logs.
- Non ci sono chiavi API OpenAI né collegamenti diretti ai repository privati dall'app.
- Un articolo approvato richiede fonte HTTPS primaria, minimo due riferimenti di evidenza, data di riferimento, 3–5 paragrafi, approvazione umana documentata, e revisione dei contenuti fattuali.
- Lo script `scripts/pulse_editorial_publication_gate.py` prepara un file **solo su comando locale esplicito**, non pubblica né modifica GitHub da solo. Il file risultante è da riesaminare prima di essere copiato nel canale pubblico.
- Il modulo Android del ramo sperimentale `pulse-rebrand-2026` mostra esclusivamente `approved_for_pulse`, mai i draft.

**Esito del primo esperimento**: due articoli ChatGPT sul lavoro e i prezzi in `drafts/chatgpt-direct-pilot-20261011.json` nel repository privato, **non approvati** e **non distribuiti**.

Nota: l'approvazione redazionale non è garanzia assoluta d'assenza di errori. I dati continuano a essere attribuiti alle fonti ufficiali.
