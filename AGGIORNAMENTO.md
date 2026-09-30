# Linea del saldo, barre delle sottocategorie e guida GitHub — 30 settembre 2026

Questo ZIP contiene **solo i file modificati** rispetto a `Wallet_budget_totali_tooltip_solo_file_modificati.zip`, che deve essere già applicato insieme agli aggiornamenti precedenti. Non è il progetto completo e non contiene database.

## Installazione

1. Arresta Wallet.
2. Estrai lo ZIP nella cartella che contiene `manage.py`, mantenendo i percorsi e sostituendo i file corrispondenti. Copia anche `.gitignore`, incluso per la preparazione del repository.
3. Se usi asset raccolti in produzione, esegui `python manage.py collectstatic --noinput`; in Docker ricostruisci l’immagine.
4. Riavvia Wallet e ricarica completamente la pagina per usare JavaScript e CSS aggiornati.

Questa patch non richiede nuove dipendenze o migrazioni. La migrazione `0008_subcategory_budget` dei precedenti aggiornamenti deve essere già applicata.

## Modifiche

- **Andamento del saldo:** linea verticale sottile e tratteggiata sul giorno indicato nel tooltip. Attraversa tutta l’area del grafico, segue il punto evidenziato e scompare uscendo dal grafico. È gestita da Plotly e mantiene l’allineamento dopo il ridimensionamento.
- **Budget per sottocategoria:** ogni voce ha una barra di utilizzo, percentuale e stato. Le stesse regole delle categorie: blu sotto l’85%, ambra dall’85% al limite, rosso oltre il limite. Il riempimento si ferma al 100%, mentre la percentuale può superarlo. I calcoli si aggiornano mentre scrivi e sono coerenti dopo il salvataggio. Budget zero, campo vuoto e importo invalido mantengono indicazioni distinte.
- **README, sezione 25:** guida per caricare il progetto completo su GitHub con GitHub Desktop o Git, e per inviare gli aggiornamenti successivi. Spiega la differenza fra repository, backup dei dati e deploy dell’applicazione.
- **Esclusioni Git:** aggiunti file di ambiente specifici, ZIP e cartelle di backup/caricamento ai dati già esclusi. `.env.example`, tassonomia e workflow rimangono inclusi. Le regole non rimuovono file eventualmente già presenti in una precedente cronologia Git.

## Verifiche

- **110 test Django superati su SQLite.**
- Chromium a 1440, 390 e 360 px: tooltip del saldo e linea verticale allineati, linea rimossa all’uscita; barre delle sottocategorie verificate a 50%, vicino al limite, al 200%, con limite zero, campo vuoto e importo non valido.
- Percorso completo di modifica, salvataggio e ricaricamento dei budget eseguito; nessun errore JavaScript, risposta HTTP di errore o overflow della pagina. Schermate controllate visivamente.
- Django check, sintassi JavaScript e Ruff superati.
- Regole `.gitignore` controllate con Git in una cartella di prova: database, credenziali e archivi esclusi; esempio di configurazione, CSV della tassonomia e workflow inclusi.
- Database personale e demo originali invariati. Nessun caricamento su GitHub o deploy remoto eseguito.
