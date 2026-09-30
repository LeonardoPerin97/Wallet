# Revisione tecnica — Wallet

Revisione aggiornata il 30 settembre 2026 sul progetto allegato, mantenendo Django e l'immagine fornita come riferimento generale per colori, gerarchia e navigazione mobile.

## Mantenuto

- Modelli finanziari e relativo storico, UUID, vincoli, migrazioni precedenti e registro cronologico con `Decimal`.
- Django server-side, form, ORM, autenticazione del proprietario, CSRF, SQLite locale e configurazione PostgreSQL di produzione.
- Plotly locale, importazione CSV/XLSX con revisione, backup JSON, budget e URL delle funzioni esistenti.
- Database originale invariato byte per byte. SHA-256 di `wallet.sqlite3`: `0dfa315f6ed1840f2311cc57d897112cd47baa2832718767e95580a4d314d01e`.

## Refactoring e comportamento

Il precedente modulo servizi è stato diviso per responsabilità: registro/saldi, filtri, analytics, movimenti, budget, importazione, tassonomia e formattazione. Dashboard, Overview e Movimenti usano la stessa interpretazione dei filtri. Le aggregazioni dei grafici sono nei servizi; i template ricevono dati già preparati. Il flusso a più passaggi dell'importazione e le operazioni di backup rimangono coordinati da `views/data_management.py`, mentre lettura, analisi e revisione sono estratte nei servizi.

Il JavaScript è separato in shell, grafici, filtri, form e visibilità della password; i template condividono navigazione, icone SVG, filtri e riepiloghi. Il CSS usa token per colori, spaziature, raggi e ombre. I dati dei grafici sono serializzati con `json_script`, senza interpolazione di testo utente in JavaScript.

La revisione iniziale includeva soltanto la nuova migrazione `0007_account_type`: aggiunge il tipo di conto con un valore predefinito. Non riscrive o elimina dati finanziari. Il database originale non è stato migrato durante la lavorazione; le prove hanno usato database separati. Gli aggiornamenti CSV/prestazioni e la prima revisione dell’interfaccia non aggiungono migrazioni. L’aggiornamento del 30 settembre modifica la validazione di `Transaction.kind` per consentire la scelta Necessaria/Extra sul singolo movimento, senza cambiare i campi delle transazioni. Il successivo aggiornamento Budget aggiunge `0008_subcategory_budget`, che crea soltanto la tabella dei limiti per sottocategoria e i suoi vincoli; i precedenti budget di categoria restano invariati fino a una modifica esplicita nell’app.

## Funzioni migliorate

- Cinque sezioni distinte: Dashboard (ex Home), Overview (ex Dashboard), Movimenti, Budget, Account e impostazioni; navigazione responsive e azione Nuovo movimento. URL e nomi delle rotte allineati: `/dashboard/` e `/overview/`; template e chiavi delle preferenze mantengono i nomi storici.
- Selezione Nessuno distinta da Tutti, persistita anche nelle preferenze della Dashboard. Invio sulle date mantiene il periodo custom; i preset sono pulsanti espliciti, senza submit implicito sul primo.
- Filtri automatici con breve attesa, date validate, Ripristina e chiusura al clic esterno/Escape; una risposta in ritardo non riapre i pannelli già chiusi.
- Titolo Account e impostazioni comune a ogni area, menu e titolo della sezione sotto; uscita con conferma.
- Font di sistema condiviso in tutta l’app e nei grafici; importo del movimento in evidenza e schede colorate per categoria/sottocategoria, anche nei filtri.
- Necessaria/Extra proposto dalla sottocategoria e modificabile per il singolo movimento. La validazione impedisce cambi fra entrate, spese e investimenti; modifica, backup JSON e CSV Wallet preservano la scelta.
- Dashboard con saldo attuale indipendente dal periodo, filtri Periodo/Conto subito sotto, riconciliazione iniziale/finale e flussi mensili coerenti fra modalità. Il netto compare nel proprio grafico, senza una seconda linea nei flussi.
- Login ridisegnato con comando accessibile per la password; intestazione con il solo nome Wallet, titoli privi di frasi introduttive, icone condivise e Nuovo movimento nel flusso della pagina.
- Registro tabellare esteso anche su mobile, con scorrimento confinato al pannello e indicatori di categoria colorati; nella lista cambia soltanto il formato delle date rispetto al riferimento Bilance, mantenendo struttura e spaziatura. Il verso del giroconto appare accanto alla categoria. I riepiloghi della lista non riportano la parola Netto; il riepilogo mensile condivide lo sfondo con quello giornaliero.
- Palette condivisa più vivace in `services/colors.py`; la resa dei colori delle categorie conserva la tonalità senza modificare il valore nel database.
- Tooltip HTML bianchi condivisi da ciambella, istogrammi e Andamento del saldo, con testo e valori su righe separate; linea verticale nativa Plotly sul giorno del tooltip del saldo; nessuna etichetta con numero di mesi nel titolo Andamento netto mensile.
- Overview con distribuzione delle spese, tooltip HTML bianco a righe distinte per nome/importo/percentuale/conteggio, serie selezionabili, mese rapido e medie comprensive dei mesi vuoti. Il riepilogo segue il livello Categoria/Sottocategoria delle barre mensili.
- Registro con ricerca e filtri condivisi, ordinamento e paginazione SQL, saldi progressivi calcolati prima dei filtri di visibilità; totali giornalieri/mensili aggregati per la lista.
- Aggregazioni di Dashboard, Overview e Budget nel database, in centesimi interi e con risultati `Decimal`; Python completa soltanto gruppi e punti dei grafici.
- CSV Wallet v2 reimportabile: UUID, conti collegati, orario, ordine e saldi iniziali; giroconto ricostruito una sola volta anche con due gambe o una singola gamba filtrata. La nuova colonna facoltativa `Tipo predefinito sottocategoria` conserva separatamente il tipo della tassonomia e quello del movimento; i precedenti CSV v2 a 20 colonne restano importabili.
- Import con verifica dei duplicati riferita al file, validazione dei campi/regole del modello in memoria e inserimenti `bulk_create` a blocchi, tutti nella stessa transazione. Il limite resta 10.000 righe.
- Giroconti visualizzati come due gambe dell'unica operazione persistita: cancellazione/modifica coerenti, annullamento nel consolidato, flussi solo al confine dei conti selezionati, esclusione dai budget.
- Gestione di conti e categorie con archiviazione che mantiene lo storico; protezione del tipo contabile delle sottocategorie già utilizzate.
- Budget esplicitamente riferito a tutti i conti, con cinque schede iniziali: Entrate, Uscite, Budget totale, Differenza netta e Residuo (budget meno uscite). Quando il residuo è negativo viene mostrato come Sforamento, in valore assoluto; stessa convenzione nelle categorie e nello storico.
- Budget per sottocategoria tramite categorie espandibili, in alternativa al limite unico. Somme in Decimal, anteprima in centesimi interi, salvataggio atomico e validazione dei due livelli come alternative; nessun doppio conteggio. Storico e JSON includono i nuovi limiti; compatibilità con backup precedenti verificata. Totali di categoria e mese, residui e barre di categorie e sottocategorie aggiornati durante la digitazione, con avviso delle modifiche da salvare; zero, vuoti e importi invalidi gestiti distintamente. Mese evidenziato e riga TOT in Spese per tipo, senza colonna Precedente.
- README con guida GitHub Desktop e Git; esclusioni del repository estese a file di ambiente, ZIP e cartelle di caricamento. Nessuna pubblicazione remota eseguita.
- README con inventario verificato di tutte le 18 directory principali e dei 110 file del progetto.
- Database demo distinto e avvio con `prova_demo.py`, senza credenziali predefinite.

## Difetti corretti

- Il totale dei budget dettagliati ora aggiorna immediatamente anche la riga della categoria e i riepiloghi coerenti; prima cambiava soltanto la somma dentro i dettagli. Nomi delle categorie nei flussi mensili senza i suffissi entrate/uscite, mantenendo separati i due versi.
- URL coerenti con le sezioni: Dashboard su `/dashboard/`, Overview su `/overview/`, inclusi nomi delle rotte, viste, navigazione e destinazione del login. `/` e il vecchio endpoint dei dati reindirizzano conservando la query; le chiavi delle preferenze rimangono stabili.
- Il preset Tutto ignora le vecchie date personalizzate e si estende dalla prima operazione (o giroconto) a oggi; le date esplicite senza preset restano utilizzabili.
- Le etichette accessibili assolute delle intestazioni sono contenute nel pannello della tabella, evitando overflow della pagina sui dispositivi mobili.
- Separazione fra saldo corrente e saldo finale del periodo; disponibilità dei giorni senza operazioni e ordinamento stabile delle operazioni.
- Importi italiani nei form e modifica delle categorie; rifiuto degli importi malformati senza conversioni monetarie in `float`.
- Importazione: righe invalide bloccano l'intero salvataggio mantenendo le correzioni; descrizione facoltativa; note preservate; importi zero non persi nella lettura; orari e saldi iniziali invalidi rifiutati.
- Inferenza del saldo iniziale coerente quando il file riporta il saldo soltanto su alcune righe. Identificativi esterni duplicati riconosciuti anche con note diverse.
- Riduzione delle query nell'analisi e nella revisione dell'importazione tramite lookup precaricati e `Exists`; dati correlati caricati con `select_related`.
- Ripristino dei backup con budget: ordine corretto delle cancellazioni, validazione dei modelli e rollback atomico. Autenticazione esclusa dai backup portabili.
- Export testuale protetto dalle formule di foglio di calcolo; JSON dei grafici sicuro.
- Asset locali di sviluppo e selettori SVG corretti per evitare il ridimensionamento accidentale dei grafici Plotly.

## Verifiche eseguite

| Verifica | Risultato |
| --- | --- |
| Suite originale, prima delle modifiche | 48 test superati. |
| Suite finale | **110 test superati** su SQLite; regressioni contabili mantenute; otto casi della precedente UI più undici nuovi casi per selezione Nessuno, budget dettagliati, somme, mesi, zero/vuoti, rollback, backup e tassonomia. |
| Configurazione Django | `manage.py check`: nessun problema. |
| Coerenza migrazioni | `makemigrations --check --dry-run`: nessuna migrazione mancante; `0008` applicata a una copia demo, con dati delle tabelle preesistenti invariati. |
| Analisi Python | Ruff, selezione F: nessun errore. |
| Browser reale | Chromium: login e visibilità password; creazione/modifica/eliminazione di movimento e giroconto; filtri, passaggio Custom/Tutto, grafici senza netto duplicato, ordinamento mobile, lista e date; filtri automatici con chiusura durante la richiesta, selezioni colorate, scelta Necessaria/Extra persistita, logout annullato/confermato, valori effettivi nei tooltip della ciambella, delle barre e del saldo, linea verticale allineata al punto e rimossa all’uscita, barre delle sottocategorie regolari/vicine al limite/superate, riepilogo Categoria/Sottocategoria, Nessuno/Tutti e Invio custom, aggiornamento del totale di categoria e mese prima del salvataggio, zero/vuoti/errori, salvataggio budget per sottocategoria e ritorno al limite unico; export, cancellazione e reimportazione di un giroconto tramite CSV v2. |
| Responsive | 13 schermate, compreso il login, e anteprima CSV a 1440, 390 e 360 px. Nuovo form di spesa verificato anche alle tre larghezze. Nessun overflow della pagina; le tabelle Movimenti e CSV scorrono all’interno del pannello su mobile. Verificati ordine dei filtri e pulsante Nuovo movimento nel contenuto. |
| Console e asset nel browser | Nessun errore JavaScript o risposta HTTP di errore rilevata durante il percorso verificato. |
| Asset di produzione | `collectstatic` e risposte 200 dei otto asset versionati, inclusi `js/auth.js` e `js/budget.js`, tramite WhiteNoise con `DEBUG=False`. |
| Query | Analytics stabili nel numero di query; revisione di 100 righe con 2 query nel caso senza storico; test di `LIMIT/OFFSET` prima del caricamento dei modelli e import generico di 200 operazioni con meno di 35 query. |
| CSV e integrità | Export/import su archivio finanziario vuoto con stessi UUID, saldi e collegamenti; doppia importazione senza duplicati; conflitti e guasti in scrittura annullano l’intero gruppo. |
| Avvio demo | Su una copia isolata: impostazione della prima password, avvio del server e accesso autenticato alla Dashboard riusciti. |
| Integrità dati originali | Hash SHA-256 invariato; database demo fisicamente separato. |

Gli screenshot di `preview/` appartengono alla revisione iniziale. Le nuove acquisizioni sono state usate per la verifica dell’interfaccia; lo ZIP di aggiornamento contiene soltanto i file applicativi e la documentazione modificati. Le prove browser modificano soltanto una copia di test della demo. I test HTML esistenti sono stati adattati alle nuove pagine e resi indipendenti dagli a-capo negli attributi, mantenendo le verifiche sulle selezioni effettive.

## Misure prima/dopo

Misure effettuate il 29 settembre 2026, prima dell’ultimo intervento all’interfaccia; non ripetute per l’aggiornamento del 30 settembre. Stesso ambiente e stessi dati sintetici, tre conti e tre anni di operazioni. Python 3.12.14, Django 5.2.17, SQLite. Il tempo riguarda i servizi, esclude HTTP/template/browser e include l’overhead di `tracemalloc`. Il picco misura allocazioni Python, non memoria del database. Una misura per caso: risultati comparativi, non un SLA.

| Dati | Funzione | Prima → dopo (secondi) | Picco Python prima → dopo (MiB) |
| --- | --- | ---: | ---: |
| 10.000 movimenti + 1.000 giroconti | Registro, 25 righe e totali | 8,86 → 0,35 | 36,88 → 0,69 |
| 10.000 movimenti + 1.000 giroconti | Dashboard con saldi | 7,66 → 0,45 | 31,85 → 0,72 |
| 50.000 movimenti + 5.000 giroconti | Registro, 25 righe e totali | 31,45 → 1,37 | 184,87 → 0,68 |
| 50.000 movimenti + 5.000 giroconti | Dashboard con saldi | 30,05 → 1,81 | 152,28 → 0,72 |

Conteggi e valori contabili coincidono. Per ripetere le misure: `python scripts/benchmark_wallet.py --sizes 10000 50000 --output risultato.json`. Lo script usa solo database temporanei nuovi e dati fittizi. Risultati completi: `docs/benchmark_sqlite.json`. Non si estrapolano prestazioni PostgreSQL da queste misure SQLite.

## Limiti residui reali

- Non è stata eseguita una pubblicazione online né una prova con un server PostgreSQL reale in questa sessione. La pipeline consegnata prevede PostgreSQL 16 e test browser separati; va eseguita nell'ambiente di rilascio.
- Wallet personale a proprietario unico, in euro; nessun sistema multivaluta o multiutente con portafogli separati.
- Il database continua a leggere/ordinare lo storico necessario ai saldi. La memoria Python delle pagine dipende soprattutto dalla pagina e dai gruppi aggregati, ma «tutti», export CSV, cursori e serie con moltissimi giorni crescono con l’output. Nessuna dichiarazione di prestazioni su milioni di righe o sotto carico concorrente.
- Importazione sincrona limitata a 10.000 righe per file, verificata già durante la lettura CSV/XLSX. Le validazioni individuali in memoria rimangono; le scritture sono a blocchi e i controlli di identità sono mirati. Non sono introdotte code in background. `bulk_create` non esegue `save()` o segnali: nuove regole future devono essere riportate anche nel percorso di importazione.
- Il CSV Wallet v2 ricostruisce movimenti e giroconti, ma non è un backup completo: mancano budget, preferenze, anagrafiche non rappresentate e metadati di conti/tassonomia. Un export filtrato non ricrea lo storico escluso. I CSV precedenti vanno riesportati per acquisire i collegamenti; il JSON rimane il formato di ripristino completo.
- SQLite usa somme in centesimi interi a 64 bit: cumulati oltre circa 9,22 × 10¹⁸ centesimi non sono supportati. L’ordinamento testuale segue la collazione del database.
