# Wallet personale

Applicazione Django per gestire conti, carte, entrate, uscite, giroconti e budget mensili. Le pagine sono renderizzate dal server; Plotly è incluso nel progetto e non richiede una CDN. L'interfaccia è in italiano, con navigazione superiore su desktop e cinque sezioni fisse in basso su mobile.

La revisione mantiene il progetto e le migrazioni esistenti. **Il file `wallet.sqlite3` allegato è stato conservato senza modifiche.** La migrazione `0007_account_type` aggiunge il tipo di conto; `0008_subcategory_budget` aggiunge i budget per sottocategoria. Entrambe vengono applicate, se mancanti, con `python manage.py migrate`; i budget di categoria esistenti vengono conservati. Il database dimostrativo si trova in `demo/wallet_demo.sqlite3` ed è indipendente.

## Come usare questa guida

La prima parte spiega come avviare e usare il Wallet. La seconda accompagna nella lettura del codice, con esempi numerici e collegamenti fra le parti. Non è necessario conoscere già Django per seguire le spiegazioni: i termini tecnici sono introdotti quando servono e raccolti nel glossario finale.

| Se vuoi… | Parti da… |
| --- | --- |
| Provare subito l'applicazione | [1. Demo](#1-avvio-rapido-della-demo). |
| Usare il tuo database e configurare l'ambiente | [2. Avvio personale](#2-avvio-del-proprio-wallet). |
| Capire pagine, filtri e giroconti | [3. Sezioni](#3-le-cinque-sezioni), [4. Filtri](#4-filtri-importi-e-nuovi-movimenti), [5. Giroconti](#5-come-funzionano-i-giroconti). |
| Importare o mettere al sicuro i dati | [6. Importazione](#6-importazione-csv--xlsx), [7. Backup](#7-backup-e-ripristino). |
| Sapere cosa fa ogni directory e ogni file | [8.1–8.14. Mappa completa](#81-mappa-completa-delle-directory-e-dei-file). |
| Orientarti nei file e avviare i controlli | [8. Struttura](#8-struttura-e-manutenzione), [9. Test](#9-test-e-controlli). |
| Preparare il rilascio o risolvere un errore | [10. Produzione](#10-produzione-con-postgresql), [11. Problemi comuni](#11-risoluzione-dei-problemi). |
| Capire come funziona il progetto internamente | [12. Architettura](#12-architettura-spiegata-come-collaborano-le-parti), [13. Database](#13-il-database-modello-per-modello). |
| Seguire i calcoli, passo per passo | [14. Saldi](#14-come-si-ricostruiscono-i-saldi), [15. Filtri e query](#15-filtri-query-e-preferenze-nel-dettaglio), [16. Grafici](#16-grafici-e-indicatori-origine-di-ogni-numero). |
| Approfondire le procedure di modifica | [17. Form e tassonomia](#17-form-modifiche-e-gestione-della-tassonomia), [18. Import/export e backup](#18-importazione-export-e-backup-percorso-interno), [19. Budget](#19-budget-formule-e-scelte-di-calcolo). |
| Comprendere interfaccia e infrastruttura | [20. Template e JavaScript](#20-interfaccia-template-css-javascript-e-icone), [21. Configurazione e sicurezza](#21-configurazione-sicurezza-e-distribuzione-spiegate). |
| Caricare il progetto su GitHub | [25. Pubblicazione del repository](#25-caricare-il-progetto-su-github). |
| Lavorare sul codice | [22. Test spiegati](#22-test-cosa-verificano-e-come-usarli-durante-lo-sviluppo), [23. Mappa delle modifiche](#23-come-modificare-il-progetto-senza-perdere-lorientamento), [24. Glossario](#24-glossario-e-punti-da-ricordare). |

## 1. Avvio rapido della demo

Requisiti: Python 3.12 consigliato, un terminale e un browser aggiornato. Esegui i comandi dalla cartella che contiene `manage.py`. Internet serve per installare le dipendenze; l'applicazione usa poi asset locali.

### Windows — PowerShell

```powershell
py -3.12 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe prova_demo.py
```

### macOS / Linux

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
python prova_demo.py
```

Al primo avvio scegli una password di almeno 12 caratteri per l'utente **`demo`**. Non è distribuita alcuna password predefinita. Apri **http://127.0.0.1:8000/** e accedi con le credenziali appena impostate. Ferma il server con `Ctrl+C`; i dati rimangono nel database demo. Il server di sviluppo resta accessibile soltanto dal computer locale.

Il comando `prova_demo.py` seleziona esplicitamente il database demo, applica le migrazioni e ignora eventuali connessioni PostgreSQL dell'ambiente. Non apre il database personale. Puoi usare una porta diversa o cambiare nuovamente la password:

```bash
python prova_demo.py --port 8001
python prova_demo.py --reset-password
```

La demo allegata contiene 3 conti, 84 movimenti, 12 giroconti e 78 budget distribuiti da aprile a settembre 2026. È composta esclusivamente da dati fittizi. Per ricrearla con date relative al giorno corrente, ferma il server, conserva o rinomina la sola copia `demo/wallet_demo.sqlite3` e avvia di nuovo `prova_demo.py`: il comando genera un nuovo database separato.

## 2. Avvio del proprio Wallet

Dopo l'installazione delle dipendenze, per usare il database originale:

```bash
python manage.py migrate
python manage.py runserver
```

Accedi con il proprietario già presente. L'aggiornamento non cambia username, password o dati. Se hai dimenticato il nome utente, puoi elencare i superuser locali:

```bash
python manage.py shell -c "from django.contrib.auth import get_user_model; print(list(get_user_model().objects.filter(is_superuser=True).values_list('username', flat=True)))"
python manage.py changepassword NOME_UTENTE
```

Per partire da un database nuovo, scegli un percorso separato tramite `WALLET_DB_PATH`, poi:

```bash
python manage.py migrate
python manage.py inizializza_wallet
python manage.py createsuperuser
python manage.py runserver
```

`inizializza_wallet` carica la tassonomia soltanto se mancano tutte le categorie e crea il conto iniziale soltanto se non esistono conti. Non reimposta i dati già presenti. Il saldo iniziale e il nome del conto sono modificabili in **Account e impostazioni**.

### Variabili d'ambiente

Il file `.env.example` documenta le variabili, ma **Django non carica automaticamente un file `.env`**. Impostale nel terminale, nell'IDE o nella piattaforma di hosting.

Esempio di database alternativo:

```bash
# macOS / Linux
export WALLET_DB_PATH=/percorso/assoluto/wallet-test.sqlite3
```

```powershell
# PowerShell
$env:WALLET_DB_PATH = "C:\Wallet\wallet-test.sqlite3"
```

Se `DATABASE_URL` o `POSTGRES_URI` sono impostate, hanno precedenza su `WALLET_DB_PATH`. Rimuovile dall'ambiente quando vuoi tornare a SQLite. `prova_demo.py` gestisce questa separazione automaticamente.

| Variabile | Uso |
| --- | --- |
| `WALLET_ENV` | `local` per sviluppo; `production` per produzione. |
| `WALLET_DEBUG` | `1` abilita debug e asset del server locale; in produzione è sempre disattivato. |
| `WALLET_DB_PATH` | Percorso SQLite alternativo; predefinito: `wallet.sqlite3`. |
| `DATABASE_URL` | Connessione PostgreSQL; in alternativa viene letto `POSTGRES_URI`. |
| `WALLET_SECRET_KEY` | Segreto Django obbligatorio in produzione. |
| `WALLET_OWNER_USERNAME` | Username del superuser proprietario; obbligatorio in produzione. |
| `WALLET_ALLOWED_HOSTS` | Host separati da virgole, senza schema o percorso. |
| `WALLET_CSRF_TRUSTED_ORIGINS` | Origini HTTPS autorizzate, separate da virgole. |
| `WALLET_DB_CONN_MAX_AGE` | Durata delle connessioni PostgreSQL in secondi; predefinito 60. |
| `WALLET_HSTS_SECONDS` | Durata HSTS; in produzione predefinito 3600. |
| `WALLET_BUILD_STATIC` | `1` per creare anche in locale il manifest degli asset di produzione. |

Il Wallet è personale: l'accesso richiede un superuser attivo. Quando `WALLET_OWNER_USERNAME` è configurato, soltanto quel superuser può accedere. Non è un sistema di contabilità con portafogli distinti per più utenti.

## 3. Le cinque sezioni

### Indirizzi delle sezioni

| Sezione | URL | Nome della rotta Django |
| --- | --- | --- |
| Dashboard | `/dashboard/` | `dashboard` |
| Overview | `/overview/` | `overview` |
| Movimenti | `/movimenti/` | `transactions` |
| Budget | `/budget/` | `budget` |
| Account e impostazioni | `/configurazione/` | `settings` |

L’indirizzo iniziale `/` reindirizza alla Dashboard conservando i parametri dei filtri, inclusi conti multipli e selezioni vuote. Dopo l’accesso, in assenza di una destinazione richiesta, si apre `/dashboard/`. Logo Wallet, menu desktop/mobile e collegamenti di ritorno usano i nuovi percorsi.

Nella revisione precedente erano state rinominate soltanto le etichette: `/` mostrava Dashboard e `/dashboard/` mostrava Overview. Ora **`/dashboard/` mostra la Dashboard**; se avevi salvato un segnalibro per l’analisi delle categorie, aggiornalo a `/overview/`. Lo stesso vecchio indirizzo non può rappresentare entrambe le pagine. L’endpoint dati delle spese è `/overview/categorie-dati/`, con nome `overview_expense_data`; il precedente `/dashboard/categorie-dati/` reindirizza al nuovo conservando i parametri. I reindirizzamenti sono temporanei (HTTP 302).

Le preferenze e i filtri salvati mantengono il proprio significato e non richiedono migrazioni per questo cambio di URL.

### Dashboard

La Dashboard risponde alla domanda «quanto ho e come sta cambiando il mio saldo?».

- **Saldo attuale**: saldo dei conti selezionati alla data di oggi; non dipende dalla data finale del periodo storico scelto.
- **Entrate, uscite e saldo finale**: valori del periodo filtrato. Il dettaglio espandibile mostra saldo iniziale del periodo, variazione netta e numero di operazioni.
- **Saldo nel tempo**: serie giornaliera che include anche i giorni senza operazioni.
- **Flussi mensili**: modalità Totale, Per tipo e Per categoria, tutte basate sugli stessi dati; il netto compare nel grafico dedicato subito sotto.
- **Netto mensile**: differenza fra entrate e uscite del mese.

I controlli temporali sopra il grafico del saldo sono sincronizzati con i filtri della pagina. Il saldo iniziale del periodo è quello prima del primo giorno selezionato; vale sempre la relazione `saldo finale = saldo iniziale + entrate − uscite`.

### Overview

La Overview analizza le categorie senza ripetere i grafici di saldo della Dashboard. Offre filtri per periodo, conti, categorie e sottocategorie, una ciambella delle uscite con totale centrale, legenda con importo/percentuale/numero di movimenti, selezione rapida del mese e barre mensili impilate per categoria o sottocategoria. Le serie possono essere mostrate o nascoste mediante la legenda.

Il riepilogo segue la scelta **Categoria / Sottocategoria** delle barre mensili: titolo, righe e medie cambiano insieme al grafico. È ordinabile per nome, totale o media mensile. Passando il cursore sulla ciambella appare una scheda bianca con il nome e tre righe distinte per importo, percentuale e numero di movimenti. La media divide per tutti i mesi toccati dall'intervallo, **compresi quelli senza spese**; un mese parzialmente selezionato conta come un mese, senza proiezioni su giorni mancanti. Gli investimenti sono uscite di liquidità e partecipano all'analisi.

### Movimenti

La vista **Tabella** consente ordinamento, modifica ed eliminazione confermata. La tabella rimane estesa anche su smartphone: tutte le colonne sono accessibili con scorrimento orizzontale all’interno del pannello; resta disponibile il selettore per l’ordinamento. Ogni categoria ha un indicatore del proprio colore e il tipo è testo semplice. La vista **Lista** mantiene il raggruppamento e la spaziatura per mese e giorno, con date nel formato «Martedì, 29 settembre» e totali giornalieri/mensili. La differenza fra entrate e uscite appare come importo con segno, senza la parola «Netto»; riepilogo mensile e giornaliero condividono lo stesso sfondo. Il formato della data è il solo riferimento a Bilance. Sotto gli importi non compare più il tipo di spesa; per i giroconti il verso appare accanto a «Giroconto», nella stessa posizione delle sottocategorie. Le azioni di modifica restano nella Tabella.

Ricerca e filtri comprendono data, conto, categoria, sottocategoria e tipo contabile. La ricerca considera descrizione, categoria, sottocategoria e riferimento esterno; per i giroconti considera anche i nomi dei conti. La paginazione permette 25, 50, 100 o tutte le righe. I totali di giorno/mese riguardano l'intero insieme filtrato, anche quando il gruppo attraversa più pagine.

**CSV** esporta tutti i risultati filtrati, non soltanto la pagina visibile. Il file usa separatore `;`, UTF-8 con BOM, date italiane e virgola decimale. Il saldo dopo operazione è quello del singolo conto, calcolato sull'intero registro, anche se altri movimenti sono nascosti dai filtri.

### Budget

Imposta un limite mensile per ciascuna categoria di uscita. Cliccando sulla categoria apri i dettagli e scegli **Limite unico** oppure **Per sottocategoria**. In quest’ultima modalità inserisci i singoli importi: la somma forma il budget della categoria, senza aggiungere il vecchio limite unico. Mentre scrivi, la somma aggiorna subito il totale sulla riga della categoria, i residui, le barre di categoria e sottocategoria e le schede Budget totale e Residuo/Sforamento del mese. Un avviso indica le modifiche da salvare; **Salva budget del mese** le conferma nel database. Il mese selezionato appare in una fascia evidenziata. In **Spese per tipo**, la riga **TOT** somma la spesa del mese; la percentuale è il totale delle spese diviso per le entrate del mese. Il perimetro è sempre **Tutti i conti**, indicato accanto al titolo e indipendente dai filtri delle altre pagine. Le cinque schede iniziali mostrano Entrate, Uscite, Budget totale, Differenza netta e **Residuo = budget − uscite**. Se il residuo è negativo, la scheda prende il nome **Sforamento** e mostra quanto hai speso oltre il budget, come importo positivo evidenziato. La stessa convenzione si applica alle categorie e allo storico. Sono presenti percentuale utilizzata, stato, barra di avanzamento, riepilogo per tipo e storico dei 12 mesi precedenti.

I budget sommano le uscite dei conti, compresi gli investimenti. **I giroconti non consumano mai budget.** Un limite di zero con spesa positiva risulta superato. L'archiviazione di una categoria non cancella i budget né nasconde le spese storiche già registrate.

### Account e impostazioni

Qui trovi conti e carte, categorie, importazione, backup, cambio password e uscita. Il titolo **Account e impostazioni** rimane sopra il menu in tutte le aree; sotto il menu compare il titolo della sezione o del passaggio corrente. Il pulsante **Esci** chiede conferma: Annulla mantiene la sessione, mentre la conferma invia il POST di logout. Ogni conto ha nome, tipo, saldo iniziale, stato e saldo attuale. L'archiviazione lo rimuove dalle scelte per nuovi movimenti, ma conserva lo storico; i conti archiviati rimangono disponibili nei filtri.

Le categorie hanno nome, colore e stato. Le sottocategorie aggiungono tipo contabile e identificatore dell'icona. Gli identificatori disponibili sono in `wallet/icon_config.py`; per un nome non riconosciuto viene usata l'icona generica. Il tipo e la categoria di una sottocategoria già utilizzata sono protetti per evitare di reinterpretare i movimenti passati: crea una nuova sottocategoria quando cambia il significato contabile.

## 4. Filtri, importi e nuovi movimenti

I pannelli **Periodo** e **Conto** sono separati e richiudibili, con una sintesi delle selezioni. Nella Dashboard si trovano sotto il saldo attuale e sopra le schede Entrate/Uscite/Saldo finale; Overview e Movimenti aggiungono le classificazioni in un pannello dedicato. I preset **1M, 3M, 6M e 1A** sono intervalli mobili rispetto a oggi; **Tutto** va dalla prima operazione registrata, includendo i giroconti, a oggi. Selezionarlo sostituisce anche eventuali date personalizzate precedenti; la data finale continua ad avanzare nei giorni successivi. Se non esistono operazioni passate, l’intervallo coincide con oggi. Per includere date future imposta un intervallo personalizzato. Le date sono inclusive. Il browser attende date valide e una fine non precedente all’inizio; se un URL inviato direttamente contiene un intervallo invalido, il server mostra un messaggio e ripristina tutto lo storico.

Puoi selezionare più conti. **Nessuno** lascia tutti i conti deselezionati: schede e saldi valgono zero, grafici e registro non contengono movimenti. La selezione vuota resta tale dopo l’aggiornamento e, per la Dashboard, anche quando viene recuperata dalle preferenze. **Tutti** e **Ripristina** ripristinano la vista consolidata. Anche per categorie, sottocategorie e tipi, deselezionare tutto produce un insieme vuoto. Le selezioni si applicano **automaticamente**, dopo una breve pausa che permette di modificare più opzioni. Anche ricerca e date si aggiornano senza pulsanti di conferma; durante la digitazione le date incomplete o invalide non vengono inviate. Premere **Invio** nei campi delle date applica l’intervallo personalizzato; i preset cambiano soltanto se attivati direttamente. **Ripristina** resta disponibile. Un clic fuori dal pannello o Escape lo chiude, anche durante un aggiornamento in corso. Categorie e sottocategorie sono selezionabili con schede colorate. Dashboard e Overview conservano filtri distinti nella sessione; le preferenze storiche della Dashboard continuano a essere lette e aggiornate.

Il pulsante **Nuovo movimento** rimane nell’intestazione del contenuto e scorre con la pagina su desktop e mobile. Apre la scelta fra Entrata, Uscita e Giroconto. Il form evidenzia l’importo nella parte superiore e propone categorie e sottocategorie compatibili con il flusso, mediante schede colorate. Le schede si usano anche con tastiera; senza JavaScript restano i selettori nativi. Per le spese **Necessaria / Extra**, la sottocategoria propone il valore iniziale, che puoi cambiare per quel singolo movimento senza modificare la classificazione delle altre operazioni. La scelta resta salvata anche riaprendo il movimento. Entrate e investimenti mantengono il proprio tipo. Gli importi nei form sono positivi: il segno viene determinato dal tipo, senza richiedere un meno per le spese. Sono accettati `1234,56`, `1.234,56` e `1234.56`; dati ambigui o malformati vengono rifiutati. Il calcolo monetario usa `Decimal` e due cifre decimali. Le date dei form e della tabella sono `gg/mm/aaaa` e il fuso applicativo è Europe/Rome.

Il saldo iniziale del conto rappresenta la disponibilità **prima del primo movimento registrato**. Non è un'entrata e non ha una propria data contabile. Modificarlo cambia di conseguenza tutti i saldi storici del conto: per aggiungere una nuova entrata usa un movimento.

## 5. Come funzionano i giroconti

Un giroconto è una sola operazione persistita, con conto di origine, destinazione, importo positivo, data, eventuale ora e descrizione. La riga in uscita e quella in entrata sono derivate dalla stessa operazione; modificare o eliminare una delle due azioni agisce sull'unico giroconto. Non vengono create due transazioni indipendenti.

Esempio: trasferisci **100 € da Conto A a Carta B**.

| Perimetro selezionato | Effetto sul saldo | Entrate / uscite nei grafici |
| --- | --- | --- |
| Solo A | −100 € | Uscita da giroconto di 100 €. |
| Solo B | +100 € | Entrata da giroconto di 100 €. |
| A e B | 0 € | Nessun flusso economico: il denaro rimane nel perimetro. |
| Tutti i conti | 0 € | Nessuna entrata o uscita aggiuntiva. |

Con più conti selezionati, soltanto i trasferimenti che attraversano il confine della selezione entrano nei flussi. Nel registro Movimenti si vedono comunque le due gambe pertinenti ai conti selezionati, con tipo **Trasferimento in uscita** / **Trasferimento in entrata**, categoria **Giroconto**, controparte e saldo dopo operazione. Il totale netto consolidato delle due gambe è zero.

L'ordine del registro è deterministico per data, ora e indice d'ordine; gli indici delle migrazioni esistenti sono mantenuti. Le due gambe non possono essere salvate separatamente. Origine e destinazione devono essere diverse.

## 6. Importazione CSV / XLSX

L'importazione si trova in **Account e impostazioni → Importa**. Non scrive movimenti prima della conferma finale. I CSV esportati da questa versione di Wallet vengono riconosciuti automaticamente e passano direttamente alla revisione delle operazioni, compresi i giroconti. Il percorso seguente riguarda invece gli estratti generici di banche o fogli di calcolo.

1. **Carica** un CSV o XLSX. Per CSV il separatore viene rilevato e può essere indicato esplicitamente; sono gestiti UTF-8/BOM e, come fallback, Windows-1252. Per XLSX viene letto il foglio attivo.
2. **Controlla l'anteprima** e associa le colonne. Sono necessari data, importo oppure colonne separate entrate/uscite, e un conto indicato nel file o come predefinito. Descrizione, orario, note e identificativo sono facoltativi.
3. **Rivedi le righe**. Associa la sottocategoria, correggi data/importo/conto e controlla gli avvisi. Il tipo contabile deriva dalla sottocategoria: una colonna tipo nel file è usata come verifica.
4. **Controlla i saldi iniziali** dei nuovi conti. Se mappi il saldo dopo operazione, il sistema lo confronta con il cumulato delle righe, anche quando il saldo manca in alcune di esse. Non sovrascrive automaticamente il saldo iniziale di un conto con storico. Le incoerenze vengono segnalate.
5. **Conferma**. Se una riga è ancora invalida, nessuna riga viene salvata e la revisione resta disponibile. Un errore di database annulla l'intera transazione. Il riepilogo indica aggiunte e duplicati ignorati.

L'identificativo esterno, quando presente, è univoco per conto. Un identificativo già importato viene ignorato anche se cambia la nota. In sua assenza, stessa data, conto, descrizione e importo segnalano un possibile duplicato: puoi includerlo esplicitamente nella revisione se si tratta di un'operazione distinta. Il riepilogo rende visibili gli scarti.

I limiti sono 10 MB per CSV/XLSX e 10.000 righe per importazione. Dividi estratti molto grandi. Le righe vuote vengono ignorate; le altre devono essere corrette, non vengono perse silenziosamente. Per ripartire con un file nuovo usa **Annulla importazione**. I dati di revisione rimangono nella sessione sul server, quindi non sono condivisi fra browser diversi.

**Il CSV Wallet v2 è reimportabile e ricostruisce i giroconti.** Mantiene le colonne leggibili e aggiunge versione, tipo di operazione, UUID, conti collegati, orario, ordine, saldi iniziali dei conti e tipo predefinito della sottocategoria. Conserva separatamente il tipo scelto sul movimento e quello predefinito, quindi una spesa impostata come Extra non cambia la sottocategoria Necessaria durante la reimportazione. Sono accettati anche i precedenti CSV v2 a 20 colonne. Due righe con lo stesso UUID descrivono un unico giroconto; una seconda importazione dello stesso file non duplica le operazioni. Un UUID già presente con dati diversi blocca l'intero import: non sovrascrive lo storico.

Un giroconto esportato con il filtro di un solo conto conserva i dati necessari per ricostruire anche l'altro lato: l'anteprima lo segnala prima della conferma. I saldi iniziali nel CSV sono usati per i conti nuovi; quelli dei conti esistenti restano invariati e un'eventuale differenza viene mostrata.

**Il backup completo rimane il JSON.** Il CSV contiene soltanto i risultati del filtro, non budget, preferenze, conti senza operazioni, tipo/archiviazione dei conti o colori/icone/stato di tutta la tassonomia. Su un archivio vuoto, un CSV parziale non ricostruisce lo storico escluso né garantisce gli stessi saldi progressivi. I CSV esportati prima di questo aggiornamento non contengono i nuovi collegamenti: per reimportare i giroconti riesporta il file con la versione aggiornata, oppure usa il backup JSON. Dettagli del formato nella sezione 18.6.

## 7. Backup e ripristino

In **Account e impostazioni → Backup** puoi scaricare un JSON portabile con conti, categorie, sottocategorie, movimenti, giroconti, budget di categoria e sottocategoria e preferenze. I backup precedenti, privi dei budget per sottocategoria, rimangono importabili dopo la migrazione. Il file non contiene password, sessioni Django o chiavi segrete.

Il ripristino richiede la selezione del file e una conferma esplicita. **Sostituisce tutti i dati finanziari attuali**, non li unisce a quelli del backup. Username e password del proprietario restano quelli dell'installazione di destinazione. La procedura carica e valida i dati in una transazione: se il file non è compatibile o viola i vincoli, il database precedente viene mantenuto.

Prima di un ripristino scarica un backup dello stato corrente. Per spostarti su un'altra installazione: prepara il database, esegui le migrazioni, crea il proprietario, accedi e ripristina il JSON. Lo stesso procedimento consente il passaggio da SQLite a PostgreSQL.

Una copia fisica di `wallet.sqlite3` contiene anche l'autenticazione ed è legata al database; per una copia fisica coerente ferma prima il server. Il database originale presente in questo archivio è stato mantenuto come richiesto, mentre il backup scaricato dall'interfaccia comprende soltanto i modelli finanziari.

## 8. Struttura e manutenzione

| Percorso | Responsabilità |
| --- | --- |
| `wallet/models.py` | Modelli, vincoli e invarianti contabili. |
| `wallet/forms.py` | Form Django, validazione degli importi, scelte dinamiche e account proprietario. |
| `wallet/services/ledger.py` | Registro cronologico, saldi e gambe dei trasferimenti. |
| `wallet/services/filters.py` | Unica interpretazione di date, conti, categorie, sottocategorie e tipi. |
| `wallet/services/analytics.py` | Aggregazioni, saldi giornalieri e dati per Plotly. |
| `wallet/services/colors.py` | Palette dei tipi e resa più vivace dei colori delle categorie. |
| `wallet/services/movements.py`, `movement_query.py` | Registro unificato, saldi progressivi SQL, ordinamento e paginazione nel database, raggruppamento giorno/mese. |
| `wallet/services/amounts.py` | Conversione in centesimi e aggregazioni SQL esatte al centesimo. |
| `wallet/services/csv_wallet.py`, `import_duplicates.py` | CSV Wallet v2, validazione per import a blocchi e ricerca mirata dei duplicati. |
| `wallet/services/budget.py` | Calcoli dei budget mensili e storico. |
| `wallet/services/importing.py`, `tabular.py`, `taxonomy.py` | Lettura file, analisi import, controllo saldi e tassonomia. |
| `wallet/services/formatting.py` | Importi Decimal, valuta italiana e parsing delle date. |
| `wallet/views/` | Endpoint delle pagine, form e coordinamento di importazione/backup. |
| `wallet/templates/wallet/components/` | Navigazione, filtri, riepiloghi e azioni condivise. |
| `wallet/static/wallet/app.css` | Token di design, componenti e layout responsive. |
| `wallet/static/wallet/app.js` | Navigazione, dialogo nuovo movimento e comportamento condiviso. |
| `wallet/static/wallet/js/` | Moduli per grafici, filtri, form e visibilità della password nel login. |
| `wallet/static/wallet/plotly.min.js` | Plotly locale. |
| `wallet/migrations/` | Intera cronologia delle migrazioni, senza sostituzioni distruttive. |
| `wallet/tests/` | Regressioni e test di accettazione contabili/funzionali. |
| `scripts/browser_smoke.py` | Verifiche con un browser Chromium reale. |
| `demo/wallet_demo.sqlite3` | Dati fittizi separati. |
| `prova_demo.py` | Avvio locale della demo e impostazione password. |
| `Dockerfile`, `.github/workflows/ci.yml` | Build di produzione e pipeline PostgreSQL/browser. |

La **Dashboard** si trova su `/dashboard/` e la **Overview**, dedicata all’analisi per categorie, su `/overview/`; `/` reindirizza alla Dashboard. I nomi delle rotte e delle funzioni di vista sono allineati alle sezioni. I template conservano i nomi storici `home.html` e `dashboard.html`, e le chiavi di sessione restano invariate per conservare i filtri già salvati. La tabella degli indirizzi è nella sezione 3. Rimangono disponibili gli URL precedenti per movimenti, giroconti, importazione, configurazione, categorie, backup e autenticazione. I filtri aggiornano il contenuto senza salto all'inizio della pagina; form e link continuano a usare endpoint Django protetti da CSRF. I dati dei grafici passano da `json_script`, con serializzazione sicura.

Per aggiornare il progetto: conserva un backup, installa i requisiti e applica `python manage.py migrate`. Non occorre eliminare il database o rigenerare le migrazioni. La migrazione `0007` assegna `Conto corrente` ai conti esistenti, modificabile dall’interfaccia. La `0008` aggiunge una tabella vuota per i nuovi limiti: non distribuisce o riscrive automaticamente i budget già salvati.

### 8.1 Mappa completa delle directory e dei file

La **radice del progetto** è la cartella che contiene `manage.py`. I percorsi sotto partono da quella cartella. Una directory raggruppa file con la stessa responsabilità; i file Python eseguono la logica, gli HTML definiscono le pagine, CSS e JavaScript ne curano stile e interazioni. Il database conserva i dati e non va confuso con il codice.

| Directory | Cosa contiene e perché esiste |
| --- | --- |
| `wallet_project/` | Configurazione dell’intero progetto Django e collegamento fra URL e applicazione. |
| `wallet/` | App finanziaria: dati, validazioni e funzionalità del Wallet. |
| `wallet/views/` | Richieste HTTP, form e composizione del contesto per le pagine. |
| `wallet/services/` | Calcoli e procedure riutilizzabili, separati dall’HTML. |
| `wallet/templates/wallet/` | Pagine HTML del Wallet. |
| `wallet/templates/wallet/components/` | Parti HTML condivise, incluse categorie del budget. |
| `wallet/templates/registration/` | Pagine di accesso e cambio password. |
| `wallet/static/wallet/` | Asset serviti al browser: stile, shell JavaScript e Plotly. |
| `wallet/static/wallet/js/` | Moduli JavaScript delle singole funzionalità. |
| `wallet/templatetags/` | Filtri e tag personalizzati usati nei template. |
| `wallet/management/commands/` | Comandi aggiuntivi eseguiti tramite manage.py. |
| `wallet/migrations/` | Passaggi ordinati con cui Django aggiorna lo schema del database. |
| `wallet/tests/` | Test applicativi con dati isolati. |
| `scripts/` | Test browser e benchmark eseguibili da terminale. |
| `demo/` | Database dimostrativo, separato dai dati personali. |
| `docs/` | Risultati e documentazione tecnica di supporto. |
| `preview/` | Acquisizioni della revisione iniziale, non necessariamente aggiornate all’ultima interfaccia. |
| `.github/workflows/` | Configurazione della pipeline GitHub. |

### 8.2 File nella radice

| File | Che cos’è e cosa fa |
| --- | --- |
| `README.md` | Guida all’avvio, all’uso e alla manutenzione; descrive architettura, contabilità, file e procedure di verifica. |
| `AGGIORNAMENTO.md` | Istruzioni specifiche per applicare l’ultimo ZIP di aggiornamento, compresa la migrazione richiesta. |
| `TECHNICAL_REVIEW.md` | Resoconto delle modifiche, verifiche eseguite, benchmark e limiti effettivamente noti. |
| `manage.py` | Avvia i comandi Django: server locale, migrazioni, utenti, test e raccolta degli asset. È il punto da cui eseguire i comandi del README. |
| `prova_demo.py` | Prepara e avvia il Wallet usando il database dimostrativo separato; gestisce anche la password iniziale della demo. |
| `requirements.txt` | Elenco delle dipendenze Python necessarie per eseguire l’applicazione. |
| `requirements-test.txt` | Aggiunge gli strumenti necessari alle prove nel browser, includendo i requisiti dell’app. |
| `Dockerfile` | Descrive la build dell’immagine di produzione, la raccolta degli asset e l’avvio con Gunicorn. |
| `.dockerignore` | Esclude dalla build Docker database locali, file d’ambiente e altri contenuti che non devono entrare nell’immagine. |
| `.gitignore` | Indica a Git quali file generati, database e configurazioni locali non versionare. |
| `.env.example` | Esempio delle variabili di configurazione: contiene segnaposto, da sostituire nell’ambiente di esecuzione. |
| `wallet.sqlite3` | Database personale SQLite, con dati finanziari, utente e sessioni. Non è codice e non viene incluso negli ZIP incrementali. |

### 8.3 Configurazione del progetto Django

Tutti i file di questa tabella sono relativi a `wallet_project/`.

| File | Che cos’è e cosa fa |
| --- | --- |
| `__init__.py` | Identifica il package Python della configurazione del progetto. |
| `settings.py` | Legge le variabili d’ambiente; configura database, app, middleware, template, asset, lingua, fuso orario e protezioni. |
| `urls.py` | Associa gli URL alle viste. Collega /dashboard/, /overview/, /budget/ e gli altri percorsi alle viste; reindirizza / alla Dashboard e conserva i parametri nei redirect di compatibilità. |
| `wsgi.py` | Espone l’applicazione WSGI caricata dal server di produzione Gunicorn. |

### 8.4 Nucleo dell’applicazione

Tutti i file di questa tabella sono relativi a `wallet/`.

| File | Che cos’è e cosa fa |
| --- | --- |
| `__init__.py` | Identifica il package Python dell’applicazione Wallet. |
| `apps.py` | Registra l’app Wallet nel sistema delle applicazioni Django. |
| `models.py` | Definisce conti, tassonomia, movimenti, giroconti, preferenze e i due modelli di budget; contiene validazioni e vincoli dei dati. |
| `forms.py` | Trasforma e valida gli input delle pagine: importi, date, classificazioni, conti, password, upload e scelta Necessaria/Extra. |
| `access.py` | Stabilisce se un utente è il proprietario autorizzato del Wallet. |
| `middleware.py` | Applica il controllo del proprietario alle richieste autenticate. |
| `icon_config.py` | Associa gli identificatori delle icone delle sottocategorie ai glifi disponibili e fornisce il fallback. |
| `categorie_movimenti.csv` | Tassonomia iniziale italiana, letta dal comando di inizializzazione e dalla creazione della demo. |

### 8.5 Viste: collegamento fra richieste e pagine

Tutti i file di questa tabella sono relativi a `wallet/views/`.

| File | Che cos’è e cosa fa |
| --- | --- |
| `__init__.py` | Rende importabili le viste dai moduli separati, mantenendo gli import usati dagli URL. |
| `common.py` | Contiene healthz, il controllo essenziale di raggiungibilità del database. |
| `dashboard.py` | Contiene le viste dashboard(), overview() e overview_expense_data(): gestisce le due pagine, i filtri salvati e la risposta dati delle spese. |
| `movements.py` | Gestisce registro, tabella/lista, paginazione e form per creare, modificare ed eliminare movimenti e giroconti. |
| `budget.py` | Richiede al servizio budget i dati del mese e renderizza la pagina oppure restituisce il redirect dopo il salvataggio. |
| `configuration.py` | Coordina conti, categorie, sottocategorie, archiviazione e importazione della tassonomia. |
| `data_management.py` | Coordina i passaggi di importazione, esporta il registro e gestisce download/ripristino dei backup JSON. |

### 8.6 Servizi: regole, calcoli e lettura dei dati

Tutti i file di questa tabella sono relativi a `wallet/services/`.

| File | Che cos’è e cosa fa |
| --- | --- |
| `__init__.py` | Espone le funzioni comuni mantenendo compatibili gli import precedenti; non duplica le implementazioni. |
| `formatting.py` | Legge date e importi, formatta gli euro e genera gli intervalli/etichette mensili. |
| `amounts.py` | Converte gli importi in centesimi per aggregazioni SQL precise e riconverte i risultati in Decimal. |
| `ledger.py` | Ricostruisce eventi contabili, saldi iniziali/finali/correnti e contributi dei giroconti al perimetro dei conti. |
| `filters.py` | Interpreta periodo, date e selezioni; distingue Tutti da Nessuno; costruisce query e riepiloghi dei filtri. |
| `analytics.py` | Aggrega flussi e spese per mese/tipo/categoria/sottocategoria, prepara schede, tabelle e dati Plotly. |
| `colors.py` | Definisce la palette dei tipi e rende più vivaci i colori delle categorie nella presentazione. |
| `movement_query.py` | Compone il registro SQL unificato, calcola saldi per conto con funzioni finestra e applica filtri, ordinamento e paginazione. |
| `movements.py` | Prepara righe e gruppi giornalieri/mensili del registro per i template, usando MovementQuery. |
| `budget.py` | Valida e salva i limiti del mese, sceglie limite unico o sottocategorie, calcola le somme senza duplicazioni, spese, residui, totale per tipo e storico. |
| `tabular.py` | Legge CSV/XLSX, riconosce separatori e propone le associazioni delle colonne, con limiti di dimensione e righe. |
| `importing.py` | Analizza e prepara le righe degli estratti generici, risolve classificazioni e verifica saldi iniziali e progressivi. |
| `import_duplicates.py` | Valida i modelli preparati per inserimenti a blocchi e cerca duplicati pertinenti alle righe del file. |
| `csv_wallet.py` | Definisce il CSV Wallet v2 e il suo export/import: UUID, collegamenti dei giroconti, saldi e tipo effettivo/predefinito. |
| `taxonomy.py` | Importa la tassonomia dai CSV italiani o bilingui, archivia le voci assenti e protegge quelle già usate in movimenti o budget. |

### 8.7 Template delle pagine Wallet

Tutti i file di questa tabella sono relativi a `wallet/templates/wallet/`.

| File | Che cos’è e cosa fa |
| --- | --- |
| `base.html` | Struttura comune: asset locali, barra Wallet, navigazioni, messaggi, contenuto e dialogo Nuovo movimento. |
| `home.html` | Pagina chiamata Dashboard: saldo attuale, filtri, schede del periodo, andamento saldo, flussi e netto mensile. |
| `dashboard.html` | Pagina chiamata Overview: ciambella, barre delle uscite e riepilogo per categoria/sottocategoria. |
| `transactions.html` | Registro Movimenti, vista tabella o lista, raggruppamenti, ordinamento, paginazione e azioni sulle righe. |
| `transaction_form.html` | Form dei movimenti ordinari, importo in evidenza, scelte colorate e tipo Necessaria/Extra. |
| `transfer_form.html` | Form dei giroconti, con conto di origine/destinazione e anteprima degli effetti. |
| `budget.html` | Pagina del mese di budget: periodo evidenziato, cinque schede, categorie espandibili, totale per tipo e storico. |
| `settings.html` | Conti e carte, relativo form di creazione/modifica e stato dei conti. |
| `categories.html` | Gestione di categorie/sottocategorie e importazione della tassonomia. |
| `backup.html` | Download del JSON e form di ripristino con conferma esplicita. |
| `import_upload.html` | Caricamento iniziale del CSV/XLSX e opzioni di lettura. |
| `import_map.html` | Anteprima e associazione delle colonne di un estratto generico. |
| `import_review.html` | Revisione e correzione dei movimenti generici prima della scrittura. |
| `import_wallet.html` | Anteprima dedicata ai CSV Wallet v2, con operazioni, giroconti, duplicati e avvisi. |
| `import_done.html` | Riepilogo dell’importazione completata e collegamenti per proseguire. |

### 8.8 Componenti HTML riutilizzabili

Tutti i file di questa tabella sono relativi a `wallet/templates/wallet/components/`.

| File | Che cos’è e cosa fa |
| --- | --- |
| `nav.html` | Le cinque destinazioni della navigazione, riutilizzate su desktop e mobile. |
| `icons.html` | Simboli SVG condivisi per l’identità Wallet e le azioni strutturali. |
| `filters.html` | Pannelli Periodo, Conto e classificazioni, ricerca e Ripristina. I pulsanti dei preset non inviano il form implicitamente. |
| `kpis.html` | Schede del periodo e dettaglio espandibile con saldo iniziale, variazione e numero di operazioni. |
| `new_button.html` | Comando Nuovo movimento nella pagina; propone il conto selezionato quando univoco. |
| `settings_header.html` | Titolo Account e impostazioni, uscita confermata, menu e titolo della sottosezione. |
| `settings_nav.html` | Menu fra conti, importazione, categorie, backup e password, con stato della voce attiva. |
| `budget_category.html` | Una categoria espandibile del budget: riepilogo aggiornato durante la digitazione, scelta limite unico/sottocategorie, campi e somma dei limiti. |

### 8.9 Template di autenticazione

Tutti i file di questa tabella sono relativi a `wallet/templates/registration/`.

| File | Che cos’è e cosa fa |
| --- | --- |
| `login.html` | Pagina di accesso con etichette italiane e visibilità temporanea della password. |
| `password_change_form.html` | Cambio password nell’area Account e impostazioni. |
| `password_change_done.html` | Conferma dell’avvenuto cambio password, mantenendo la stessa struttura dell’area Account. |

### 8.10 CSS, JavaScript e grafici locali

Tutti i file di questa tabella sono relativi a `wallet/static/wallet/`.

| File | Che cos’è e cosa fa |
| --- | --- |
| `app.css` | Token di stile, font condiviso, componenti, tabelle, lista, form, tooltip e adattamenti responsive. |
| `app.js` | Inizializza i moduli della pagina, apre/chiude il dialogo Nuovo movimento e cambia le modalità dei flussi. |
| `plotly.min.js` | Libreria Plotly distribuita localmente; disegna i grafici senza scaricarla da una CDN. È un file di libreria, non il codice da modificare per cambiare i tooltip. |
| `js/charts.js` | Configura Plotly, legende, selezione delle serie e tooltip HTML bianchi di ciambella e istogrammi. |
| `js/filters.js` | Applica filtri automatici e Invio, valida le date, gestisce richieste annullabili, cronologia, focus e pannelli. |
| `js/forms.js` | Gestisce schede colorate e tastiera, sottocategorie dinamiche, tipo di spesa, anteprima giroconto e conferme. |
| `js/budget.js` | Mostra i campi della modalità scelta e aggiorna totali, residui e barre in centesimi interi; segnala le modifiche da salvare. Il salvataggio e le validazioni definitive restano sul server. |
| `js/auth.js` | Mostra/nasconde la password nella pagina di accesso con nome accessibile e stato del pulsante. |

### 8.11 Tag per i template e comandi di gestione

Tutti i file di questa tabella sono relativi a `wallet/`.

| File | Che cos’è e cosa fa |
| --- | --- |
| `templatetags/__init__.py` | Identifica il package dei tag e filtri Django personalizzati. |
| `templatetags/wallet_tags.py` | Fornisce formattazione degli euro, colori e costruzione di URL che mantengono gli altri filtri. |
| `management/__init__.py` | Identifica il package dei comandi di gestione dell’app. |
| `management/commands/__init__.py` | Permette a Django di trovare i comandi aggiuntivi. |
| `management/commands/inizializza_wallet.py` | Prepara categorie e conti iniziali quando assenti, usando la tassonomia inclusa. |
| `management/commands/crea_demo.py` | Genera operazioni e budget fittizi soltanto su un database demo esplicitamente selezionato e vuoto. |

### 8.12 Migrazioni: cronologia dello schema

Tutti i file di questa tabella sono relativi a `wallet/migrations/`.

| File | Che cos’è e cosa fa |
| --- | --- |
| `__init__.py` | Identifica il package delle migrazioni Django. |
| `0001_initial.py` | Crea lo schema iniziale dei modelli finanziari e delle preferenze. |
| `0002_userpreference_accounts_userpreference_categories_and_more.py` | Aggiunge selezioni multiple di conti/categorie alle preferenze e rende facoltativa la descrizione del movimento. |
| `0003_userpreference_no_accounts_selected_and_more.py` | Aggiunge flag per distinguere selezioni vuote di conti e categorie. |
| `0004_userpreference_category_selection.py` | Aggiunge selezione di tutte le categorie e inclusione dei trasferimenti, preservando le precedenti preferenze. |
| `0005_categorybudget_subcategory_icon.py` | Introduce i budget di categoria e l’identificatore dell’icona delle sottocategorie. |
| `0006_rename_wallet_tran_date_86aaa0_idx_wallet_tx_ledger_order_and_more.py` | Rinomina gli indici del registro mantenendo la loro funzione per l’ordinamento cronologico. |
| `0007_account_type.py` | Aggiunge il tipo di conto, con Conto corrente come valore iniziale per i conti esistenti. |
| `0008_subcategory_budget.py` | Crea la tabella dei budget per sottocategoria con unicità mese/sottocategoria e importi non negativi; non riscrive i budget di categoria esistenti. |

### 8.13 Test e strumenti di verifica

| File | Che cos’è e cosa fa |
| --- | --- |
| `wallet/tests/__init__.py` | Identifica il package delle suite di test Django. |
| `wallet/tests/test_regressions.py` | Protegge le regole storiche di movimenti, giroconti, importazione, budget, accesso e tassonomia. |
| `wallet/tests/test_application.py` | Verifica pagine, filtri, conti, periodi, aggregazioni, import atomico, archivi, sicurezza e limiti delle query. |
| `wallet/tests/test_improvements.py` | Verifica registro SQL, centesimi, paginazione, import a blocchi e reimportazione CSV v2 con giroconti. |
| `wallet/tests/test_ui_workflows.py` | Verifica la scelta Necessaria/Extra e la conservazione in CSV/JSON, il residuo consolidato e il riepilogo per sottocategoria. |
| `wallet/tests/test_budget_allocations.py` | Verifica Nessuno, preferenze, somme per sottocategoria, cambio modalità, mesi indipendenti, zero/vuoti, rollback, backup vecchi/nuovi e protezione della tassonomia. |
| `scripts/browser_smoke.py` | Prova l’app con Chromium, compresi i tasti Invio, Nessuno, i tooltip reali e i budget espandibili; usa un database di test separato. |
| `scripts/benchmark_wallet.py` | Misura servizi e allocazioni Python su database SQLite temporanei di dimensione scelta; non usa il database personale. |
| `.github/workflows/ci.yml` | Definisce la pipeline di test applicativi PostgreSQL e browser SQLite per il repository GitHub. |

### 8.14 Dati dimostrativi, misure e immagini di riferimento

| File | Che cos’è e cosa fa |
| --- | --- |
| `demo/wallet_demo.sqlite3` | Database di esempio fisicamente separato dal personale, con operazioni fittizie. |
| `docs/benchmark_sqlite.json` | Risultati delle misure SQLite salvate il 29 settembre 2026; non costituiscono una garanzia di prestazioni. |
| `preview/home-desktop.png` | Acquisizione desktop della pagina di sintesi nella revisione iniziale. |
| `preview/home-mobile.png` | Acquisizione mobile della pagina di sintesi nella revisione iniziale. |
| `preview/dashboard-desktop.png` | Acquisizione desktop dell’analisi per categorie nella revisione iniziale. |
| `preview/dashboard-mobile.png` | Acquisizione mobile dell’analisi per categorie nella revisione iniziale. |

Le directory generate durante l’esecuzione, come `staticfiles/` dopo `collectstatic`, `test-results/` per le acquisizioni e `__pycache__/` per Python, non sono sorgenti da modificare. Una cartella `.venv/`, se creata, contiene le dipendenze locali. Il pacchetto di aggiornamento include soltanto i file cambiati: per orientarti nell’intero progetto usa questa mappa, non l’elenco parziale dello ZIP.

Per seguire una funzione dall’inizio alla fine: parti dall’URL in `wallet_project/urls.py`, apri la vista indicata in `wallet/views/`, segui i servizi o i form chiamati, poi il template passato a `render()`. Per il comportamento del browser cerca il relativo modulo in `wallet/static/wallet/js/`; per i dati persistenti e i vincoli torna a `models.py` e alle migrazioni.

## 9. Test e controlli

```bash
python manage.py check
python manage.py makemigrations --check --dry-run
python manage.py test
```

Django crea un database di test isolato. La suite copre saldi, segni, perimetri dei giroconti, intervalli e mesi vuoti, medie, budget, ordinamento, paginazione, export, importazione, backup atomico, accesso del proprietario e CSRF. Include controlli sul numero di query per analytics e revisione dell'importazione.

Per testare l'interfaccia con Chromium:

```bash
python -m pip install -r requirements-test.txt
python -m playwright install chromium
```

Seleziona **una copia eliminabile del database demo**, configura una password di test per `demo` e poi esegui lo script. Esempio macOS/Linux:

```bash
cp demo/wallet_demo.sqlite3 demo/browser.sqlite3
export WALLET_DB_PATH="$PWD/demo/browser.sqlite3"
export WALLET_ENV=local
export WALLET_DEBUG=1
export WALLET_OWNER_USERNAME=demo
python manage.py changepassword demo
export DJANGO_SUPERUSER_USERNAME=demo
# Imposta nella variabile seguente la password scelta per questa copia.
export DJANGO_SUPERUSER_PASSWORD='la-password-scelta-per-il-test'
python scripts/browser_smoke.py --start-server
```

Per PowerShell usa `$env:NOME_VARIABILE = "valore"` e `Copy-Item` al posto di `cp`. Rimuovi `DATABASE_URL` e `POSTGRES_URI` se puntano a un altro database. Lo script crea, modifica ed elimina operazioni dimostrative: non eseguirlo sul database personale. Produce screenshot in `test-results/` e controlla pagine, errori JavaScript, risposte HTTP errate, asset, larghezza dei grafici e overflow mobile. Se il server è già avviato, ometti `--start-server`; `WALLET_BASE_URL` permette di indicarne l'URL.

La pipeline inclusa esegue i test applicativi su PostgreSQL 16 e i test Chromium su SQLite separato. La configurazione della pipeline è consegnata, ma la sua esecuzione su GitHub dipende dal repository in cui il progetto verrà pubblicato. I risultati effettivamente verificati durante questa revisione sono in `TECHNICAL_REVIEW.md`.

## 10. Produzione con PostgreSQL

La produzione richiede PostgreSQL, HTTPS, una chiave segreta e il nome esplicito del proprietario. Non usare `runserver` per servire l'applicazione pubblica. Un esempio di ambiente è:

```text
WALLET_ENV=production
WALLET_SECRET_KEY=<chiave-casuale-segreta>
WALLET_OWNER_USERNAME=<nome-del-superuser>
WALLET_ALLOWED_HOSTS=wallet.example.com
WALLET_CSRF_TRUSTED_ORIGINS=https://wallet.example.com
DATABASE_URL=postgresql://utente:password@host:5432/wallet
```

Genera una chiave, ad esempio con `python -c "import secrets; print(secrets.token_urlsafe(64))"`, e salvala fra i segreti della piattaforma. Non inserirla nel repository. Configura TLS della connessione al database secondo il servizio PostgreSQL usato; quando richiesto, aggiungi `?sslmode=require` all'URL.

Con le variabili già impostate:

```bash
python -m pip install -r requirements.txt
python manage.py migrate --noinput
python manage.py collectstatic --noinput
python manage.py createsuperuser
python manage.py check --deploy
gunicorn wallet_project.wsgi:application --bind 0.0.0.0:8000 --workers 2 --timeout 120
```

Crea il proprietario soltanto alla prima installazione. Su un database vuoto puoi usare `inizializza_wallet` oppure ripristinare un backup JSON dopo l'accesso. Esegui le migrazioni una sola volta nella fase di rilascio, prima di avviare i worker.

Gli asset sono serviti da **WhiteNoise** con nomi versionati e compressione; `collectstatic` è necessario dopo ogni modifica a CSS o JavaScript. La configurazione abilita redirect HTTPS, cookie sicuri, CSRF, protezione frame e HSTS. Il reverse proxy deve sovrascrivere in modo affidabile `X-Forwarded-Proto`, perché Django lo usa per riconoscere HTTPS. L'endpoint `/healthz/` è disponibile per il controllo del servizio.

Il `Dockerfile` installa le dipendenze, esegue `collectstatic` in fase di build e avvia Gunicorn come utente senza privilegi. I database SQLite, la demo e i file `.env` sono esclusi dall'immagine. Le variabili `PORT` e `WEB_CONCURRENCY` regolano porta e numero di worker. Su Northflank puoi collegare `POSTGRES_URI` dell'addon a `DATABASE_URL` tramite un Secret Group e usare un release job per `migrate`.

Sono conservati i vincoli e le query ORM compatibili con SQLite e PostgreSQL; la revisione non comprende una pubblicazione online o un collaudo su un server PostgreSQL reale. Consulta la pipeline per la verifica sul database di produzione prima del rilascio.

Riferimenti: [distribuzione degli asset Django](https://docs.djangoproject.com/en/5.2/howto/static-files/deployment/) e [integrazione WhiteNoise](https://whitenoise.readthedocs.io/en/stable/django.html).

## 11. Risoluzione dei problemi

| Sintomo | Controllo |
| --- | --- |
| Errore relativo a `account_type` | Esegui `python manage.py migrate` sul database selezionato. |
| Credenziali rifiutate | Verifica superuser attivo e `WALLET_OWNER_USERNAME`; per la demo usa `demo`. |
| CSS o grafici assenti in locale | Usa `WALLET_ENV=local`, `WALLET_DEBUG=1` e controlla di avviare dalla cartella del progetto. |
| Asset assenti in produzione | Ripeti `collectstatic`; verifica `/static/` e la build dell'immagine. |
| Errore CSRF dietro proxy | Controlla origine HTTPS, `WALLET_CSRF_TRUSTED_ORIGINS` e header del proxy. |
| Demo senza dati nel periodo | Scegli **Tutto** o aprile–settembre 2026, oppure ricrea la sola demo. |
| Importazione bloccata | Correggi tutte le righe evidenziate; nessuna è stata salvata parzialmente. |
| Saldo diverso dall'estratto | Verifica saldo iniziale, date, conti selezionati, duplicati e giroconti al confine della selezione. |
| Porta 8000 occupata | Usa `python prova_demo.py --port 8001` oppure `runserver 8001`. |

La valuta gestita è l'euro e non è prevista conversione tra valute. La pagina budget riguarda tutti i conti. Le aggregazioni monetarie, l'ordinamento e la paginazione del registro lavorano nel database. Python prepara soltanto le righe richieste, i gruppi aggregati e i punti dei grafici. Il database deve comunque leggere e ordinare lo storico necessario ai saldi: non si dichiara un costo costante né una capacità su milioni di righe. Sono disponibili misure riproducibili su 10.000 e 50.000 movimenti nella sezione 22.5. La scelta «tutti», gli export CSV e intervalli con moltissimi giorni continuano a crescere con l'output richiesto.

## 12. Architettura spiegata: come collaborano le parti

Il progetto si può leggere a partire da tre elementi concreti: **dati**, **regole** e **interfaccia**. I dati sono conti, operazioni e categorie. Le regole stabiliscono come validare un importo, attribuire un segno, applicare un filtro e ricavare un saldo. L'interfaccia permette di consultare e modificare questi dati attraverso pagine Django.

### 12.1 Progetto Django e applicazione Wallet

`wallet_project/` contiene la configurazione dell'intero sito: database, lingua, autenticazione, indirizzi e modalità di esecuzione. `wallet/` contiene l'applicazione finanziaria vera e propria. Questa distinzione consente di cambiare, per esempio, l'indirizzo del database senza riscrivere i calcoli dei saldi.

| Parte | Domanda a cui risponde | Esempio nel progetto |
| --- | --- | --- |
| Configurazione | In quale ambiente sto lavorando e quali componenti devo attivare? | `wallet_project/settings.py` seleziona SQLite o PostgreSQL. |
| URL | Quale funzione deve gestire questo indirizzo? | `/movimenti/` richiama la vista `transactions`. |
| Vista | Che cosa ha chiesto il browser e quale risposta devo preparare? | La vista legge filtri, chiede le righe al servizio e applica la paginazione. |
| Form | I dati inviati sono validi e coerenti? | `TransactionForm` controlla categoria, sottocategoria e importo. |
| Modello | Quali dati conservo e quali relazioni devono rispettare? | `Transaction` collega un movimento a un conto e a una sottocategoria. |
| Servizio | Come applico una regola finanziaria o un'elaborazione? | `period_balances` aggrega i saldi; `MovementQuery` ricostruisce i saldi dopo operazione. |
| Template | Come organizzo i dati nella pagina HTML? | `transactions.html` costruisce tabella o lista. |
| CSS e JavaScript | Come presento la pagina e come reagisce ai comandi? | CSS dispone le schede; JavaScript aggiorna filtri e grafici. |

Una *vista* Django è quindi una funzione Python che prepara una risposta, non il file grafico della pagina. Un *template* è il file HTML con le istruzioni per mostrare i dati. Un *servizio* è una funzione riutilizzabile che esegue calcoli o una procedura senza dover duplicare il lavoro in più pagine.

L'applicazione resta renderizzata dal server: Django produce l'HTML completo. JavaScript migliora l'interazione con aggiornamenti parziali, form dinamici, dialoghi e Plotly. Non esiste un secondo backend con API REST generiche, né una copia autonoma dei saldi mantenuta nel browser.

### 12.2 Cosa succede quando apri la Dashboard

1. Il browser richiede `/dashboard/` e invia, se esiste, il cookie della sessione. Se parte da `/`, riceve prima un reindirizzamento che conserva i parametri dei filtri.
2. Django identifica l'utente. Il middleware del proprietario verifica che possa accedere; un utente anonimo viene indirizzato al login dalla protezione della vista.
3. `urls.py` sceglie `dashboard` in `wallet/views/dashboard.py`.
4. `_page_filters` recupera i filtri della Dashboard e `Filters.parse` li converte in date e insiemi di identificativi.
5. `analytics(..., with_balance=True)` calcola riepiloghi e serie; `ledger_snapshot` ricostruisce i saldi.
6. `home.html`, attraverso `base.html` e i componenti condivisi, trasforma il contesto in HTML.
7. Il browser applica `app.css`; `charts.js` legge i dati JSON e disegna i grafici con Plotly locale.

Il *contesto* è semplicemente il dizionario passato al template: contiene, per esempio, `income`, `outgoing`, `closing` e `charts`. Il template deve mostrare questi valori, non ricostruire da solo la contabilità.

### 12.3 Cosa succede quando salvi un movimento

L'apertura del form è una richiesta `GET`; il salvataggio è una richiesta `POST`. Il browser invia data, importo, conto e classificazione insieme al token CSRF. La vista costruisce `TransactionForm`, che converte gli importi e controlla le scelte. Se manca un dato o la sottocategoria non è valida, il form viene mostrato di nuovo con gli errori e non salva il movimento.

Quando il form è valido, `clean()` assegna la sottocategoria e valida il tipo predefinito o la scelta Necessaria/Extra. `save()` conserva questa scelta e attribuisce un indice d’ordine al nuovo movimento. Il modello applica a sua volta le proprie regole prima della scrittura. La vista invia infine un redirect a Movimenti: così un semplice aggiornamento della pagina successiva non ripete il POST di creazione.

## 13. Il database, modello per modello

Un modello Django descrive una tabella e i suoi campi. Una *chiave esterna* collega una riga a un'altra tabella: un movimento contiene l'identificativo del conto, non una copia scollegata del suo nome. Se il nome del conto cambia, il collegamento rimane valido.

```mermaid
erDiagram
    direction TB
    Account ||--o{ Transaction : registra
    Category ||--o{ Subcategory : raggruppa
    Subcategory ||--o{ Transaction : classifica
    Account ||--o{ Transfer : origine
    Account ||--o{ Transfer : destinazione
    Category ||--o{ CategoryBudget : pianifica
    Subcategory ||--o{ SubcategoryBudget : dettaglia
```

Nel diagramma, un conto può avere molti movimenti; un movimento appartiene a un solo conto. Un giroconto ha due collegamenti distinti a `Account`, uno per origine e uno per destinazione. `UserPreference`, descritto sotto, conserva le preferenze e non rappresenta un'operazione finanziaria.

### 13.1 `Account`: conti, carte, risparmi e contanti

| Campo | Significato |
| --- | --- |
| `name` | Nome univoco visualizzato nell'interfaccia. |
| `account_type` | `conto`, `carta`, `risparmio` oppure `contanti`; classifica il contenitore del denaro. |
| `initial_balance` | Disponibilità iniziale precedente alle operazioni registrate. |
| `active` | Stabilisce se il conto è disponibile per nuovi inserimenti. |
| `created_at` | Momento di creazione della riga nel database. |

Il tipo di conto non cambia le formule: una carta e un conto corrente seguono le stesse regole di saldo. Un saldo iniziale negativo è ammesso. Il saldo attuale non è un campo da aggiornare manualmente: viene ricalcolato a partire dal saldo iniziale e dalle operazioni.

### 13.2 `Category` e `Subcategory`: classificazione

`Category` conserva `name`, `color` e `active`. `Subcategory` conserva il collegamento `category`, il proprio `name`, il tipo contabile `kind`, l'identificatore `icon` e lo stato `active`.

Il tipo contabile **predefinito** appartiene alla **sottocategoria**. Un movimento che usa una sottocategoria Necessaria o Extra può conservare una scelta diversa fra questi due tipi; non sono ammesse deroghe fra entrate, spese e investimenti. Questa scelta permette, per esempio, di avere all'interno di una categoria sia sottocategorie necessarie sia extra. La combinazione categoria–nome della sottocategoria è univoca, mentre nomi come «Altro» possono comparire in categorie differenti.

La categoria di un movimento si ricava dalla sua sottocategoria. Non viene memorizzato un secondo collegamento indipendente che potrebbe diventare incoerente. L'archiviazione modifica lo stato, mantenendo le relazioni storiche.

### 13.3 `Transaction`: entrate e uscite

| Campo | Significato |
| --- | --- |
| `id` | Identificativo numerico interno gestito dal database. |
| `uid` | UUID univoco usato negli URL di modifica ed eliminazione. |
| `date` | Giorno dell'operazione finanziaria. |
| `operation_time` | Orario facoltativo, utile per ordinare operazioni dello stesso giorno. |
| `order_index` | Criterio aggiuntivo per stabilizzare l'ordine del registro. |
| `description` | Testo facoltativo, fino a 250 caratteri. |
| `amount` | Importo positivo, con al massimo due cifre decimali. |
| `subcategory` | Classificazione da cui si ricavano categoria e tipo predefinito. |
| `kind` | Tipo del singolo movimento: uguale al predefinito, oppure Necessaria/Extra per una sottocategoria di questi tipi. Se omesso alla creazione viene derivato dalla sottocategoria. |
| `account` | Conto sul quale l'operazione produce effetto. |
| `notes` | Note mantenute nel modello e supportate da importazione, export e backup; non sono un campo del form manuale corrente. |
| `external_id` | Identificativo della banca o della fonte, facoltativo e univoco per conto quando non vuoto. |
| `created_at` | Data e ora di inserimento nel sistema; distinta dalla data dell'operazione. |

L'importo memorizzato di una spesa di 40 € è `40.00`. La proprietà `signed_amount` restituisce `-40.00` quando occorre calcolarne l'effetto. Per un'entrata restituisce invece l'importo positivo.

### 13.4 `Transfer`: un solo record, due effetti

`Transfer` conserva `uid`, data, ora, indice d'ordine, `source`, `destination`, importo e descrizione. Il modello verifica che l'importo sia positivo e i conti siano differenti. Non ha sottocategoria: «Giroconto» è la classificazione assegnata alle sue righe di presentazione.

Le due righe visibili nel registro non sono due `Transaction` nascoste. Sono oggetti costruiti dal servizio Movimenti a partire dallo stesso `Transfer`, con segno, conto, controparte e saldo diversi. Per questo condividono lo stesso UUID e conducono alla modifica della medesima operazione.

### 13.5 `CategoryBudget` e `SubcategoryBudget`: limiti del mese

Ogni riga collega una categoria a un mese e a un limite `amount`. Il mese è memorizzato con il primo giorno, per esempio `2026-09-01`; non è la data in cui hai deciso il budget. La coppia mese–categoria è univoca. `SubcategoryBudget` contiene invece `month`, `subcategory`, `amount` e `updated_at`, con unicità mese–sottocategoria. In modalità dettagliata il totale della categoria viene calcolato sommando le righe delle sottocategorie; non è salvato una seconda volta in `CategoryBudget`.

Un limite pari a zero esiste ed esprime un vincolo di spesa nullo. Un campo vuoto, invece, rimuove il limite di quella categoria per quel mese. `updated_at` registra l’ultimo aggiornamento. Per la stessa categoria e lo stesso mese si usa un solo tipo di budget: il servizio sostituisce atomicamente il limite unico con le righe, o viceversa. I modelli e il ripristino JSON rifiutano la presenza contemporanea dei due livelli; le sottocategorie ammesse sono quelle di uscita, compresi gli investimenti.

### 13.6 `UserPreference`, utente e sessioni

`UserPreference` conserva periodo, date e selezioni ereditate dalle versioni precedenti. La Dashboard usa la riga con chiave `1` per mantenere le preferenze di periodo e conti. Il flag `no_accounts_selected` distingue esplicitamente Nessuno dal caso Tutti, anche senza la precedente sessione del browser. Il modello conserva anche campi relativi alle vecchie selezioni di categorie e giroconti per compatibilità; non tutti pilotano l'interfaccia attuale.

Le selezioni correnti di Dashboard e Overview sono inoltre separate nella sessione mediante, rispettivamente, `wallet_home_filters` e `wallet_dashboard_filters`. Queste chiavi storiche restano invariate quando cambiano gli URL, così i filtri già salvati continuano ad appartenere alla stessa pagina. Movimenti legge i parametri presenti nel proprio URL. Le preferenze non sono un sistema di autorizzazioni e non separano portafogli di più persone.

Django mantiene l'utente e le password nelle proprie tabelle di autenticazione. Le sessioni sono conservate sul server nel database; il cookie identifica la sessione. Questo è anche il motivo per cui una revisione d'importazione avviata in un browser non appare automaticamente in un altro.

### 13.7 Vincoli e protezione dello storico

I vincoli del database impediscono importi non positivi nei movimenti/giroconti, budget negativi e duplicazioni delle chiavi univoche previste. `clean()` e `full_clean()` aggiungono controlli applicativi, come la corrispondenza fra tipo e sottocategoria o la diversità dei conti di un trasferimento.

Le relazioni finanziarie usano `PROTECT`: il database applicativo non deve perdere la classificazione o il conto di un'operazione per una cancellazione accidentale del riferimento. L'interfaccia propone l'archiviazione per i dati anagrafici. Il ripristino completo segue invece una procedura esplicita e atomica che sostituisce i dati nell'ordine corretto.

## 14. Come si ricostruiscono i saldi

### 14.1 Il registro degli eventi

`wallet/services/ledger.py` trasforma ogni operazione in uno o più *eventi*: una variazione del saldo di un determinato conto. Un'entrata genera una variazione positiva, una spesa negativa, un giroconto una variazione negativa sull'origine e una positiva sulla destinazione.

`ledger_events()` legge separatamente movimenti e trasferimenti già ordinati dal database, poi li unisce con `heapq.merge`. La fusione scorre due sequenze ordinate senza dover prima creare e riordinare un'unica lista con tutto lo storico. Le query sono iterate a blocchi di 2.000 record; l'iterazione non equivale però a una garanzia di memoria costante dell'intera applicazione, perché altri servizi conservano risultati e indici.

L'ordine usa data, ora, indice d'ordine, priorità e identificativo. Un orario assente viene trattato come inizio giornata ai fini dell'ordinamento. A parità dei primi criteri, le gambe dei trasferimenti precedono i movimenti ordinari; uscita e ingresso del medesimo trasferimento hanno un ordine deterministico. Questo permette di ricostruire lo stesso saldo dopo operazione a ogni apertura della pagina.

### 14.2 Un esempio completo

Consideriamo Conto A con saldo iniziale di 1.000 € e Carta B con 100 €. Le operazioni sono:

| Data | Operazione | Effetto su A | Effetto su B | Saldo A | Saldo B | Totale |
| --- | --- | ---: | ---: | ---: | ---: | ---: |
| Prima delle operazioni | Saldi iniziali | — | — | 1.000 € | 100 € | 1.100 € |
| 02/09/2026 | Entrata su A | +500 € | — | 1.500 € | 100 € | 1.600 € |
| 03/09/2026 | Spesa su A | −40 € | — | 1.460 € | 100 € | 1.560 € |
| 04/09/2026 | Giroconto da A a B | −200 € | +200 € | 1.260 € | 300 € | 1.560 € |
| 05/09/2026 | Spesa su B | — | −25 € | 1.260 € | 275 € | 1.535 € |

Se selezioni entrambi i conti dal 2 al 5 settembre, la Dashboard mostra entrate di **500 €**, uscite di **65 €**, netto di **435 €** e saldo finale di **1.535 €**. Il giroconto cambia la distribuzione del denaro, mantenendo invariato il totale.

Se selezioni soltanto A, le uscite del perimetro sono **240 €**: 40 € di spesa e 200 € trasferiti al conto esterno alla selezione. Il saldo finale è 1.260 €. Se selezioni soltanto B, risultano 200 € in entrata e 25 € in uscita, con saldo finale di 275 €.

Per entrambi i conti, il registro contiene **cinque righe**: tre movimenti ordinari e le due gambe del giroconto. Il conteggio analitico della Dashboard è invece **tre operazioni rilevanti per i flussi**, perché quel trasferimento rimane interamente dentro il perimetro. Un diverso conteggio fra registro e riepilogo, in questo caso, è previsto.

### 14.3 Saldo iniziale, finale, attuale e saldo della riga

| Valore | Confine temporale | Funzione o dato principale |
| --- | --- | --- |
| Saldo iniziale del conto | Prima di tutte le operazioni registrate | `Account.initial_balance`. |
| Saldo iniziale del periodo | Operazioni con data precedente all'inizio | `LedgerSnapshot.opening` / `balance_before`. |
| Saldo finale del periodo | Operazioni fino alla fine inclusa | `LedgerSnapshot.closing` / `balance_at`. |
| Saldo attuale | Operazioni fino a oggi incluso | `LedgerSnapshot.current`. |
| Saldo dopo la riga | Operazioni del conto fino a quella posizione nel registro | Somma SQL con finestra per conto, prima dei filtri di visibilità. |

Nell'esempio, un filtro dal 2 al 4 settembre restituisce saldo finale di 1.560 €, mentre il saldo attuale, dopo la spesa del 5 settembre e in assenza di altre operazioni, è 1.535 €. Non sono due versioni incompatibili dello stesso dato: hanno date di riferimento differenti.

La ricerca per descrizione e i filtri di categoria riducono le righe visibili in Movimenti, ma non cancellano le altre operazioni dal calcolo del saldo del conto. Una riga filtrata deve mantenere il saldo reale che aveva nel registro completo.

### 14.4 `ledger_snapshot` e le funzioni di servizio

`ledger_snapshot()` percorre il registro mantenendo un totale complessivo e un saldo per conto. Nella stessa elaborazione prepara apertura, chiusura, saldo a una data e saldi dopo le singole operazioni. Restituisce un oggetto `LedgerSnapshot`, una struttura Python con questi risultati, non una nuova tabella.

Le pagine non costruiscono più una mappa Python di tutte le operazioni. `period_balances()` esegue aggregazioni SQL per apertura, chiusura e saldo attuale; anche `balance_before()` e `balance_at()` usano questa strada. `ledger_snapshot()` rimane disponibile per compatibilità e come calcolo indipendente nei test.

Per il registro, `MovementQuery` costruisce una `UNION ALL` di movimenti, uscite da giroconti ed entrate da giroconti. Una somma con finestra `SUM(...) OVER (PARTITION BY account_id ORDER BY ...)` calcola il cumulato di ciascun conto; il saldo iniziale del conto viene aggiunto a questo risultato. **Prima si calcolano i saldi sull'intero storico pertinente, poi si applicano i filtri di visibilità**, per evitare che una ricerca modifichi il saldo della riga. Infine il database ordina e applica `LIMIT/OFFSET`. Soltanto i modelli delle righe richieste vengono caricati e decorati per il template. I totali per giorno e mese sono aggregati separatamente sull'intero insieme filtrato.

I parametri dei filtri sono compilati dall'ORM e passati separatamente all'SQL; i campi d'ordinamento provengono da una lista chiusa. L'ordine dei testi segue la collazione del database, quindi alcuni nomi con accenti possono avere una posizione diversa fra SQLite e PostgreSQL. La cronologia e gli importi conservano gli stessi criteri contabili.

`initial_balance()` somma i saldi iniziali dei conti selezionati. `next_order_index()` prende il massimo indice già presente fra movimenti e trasferimenti e aggiunge uno. L'indice serve all'ordine, mentre l'unicità delle operazioni è affidata agli identificativi.

Una modifica retroattiva viene riflessa ai successivi caricamenti: i saldi dopo quella data vengono ricalcolati. Non occorre correggere manualmente una colonna di saldi già salvati.

### 14.5 Precisione e formato italiano

Nel codice Python i calcoli finanziari usano `Decimal`: ad esempio `Decimal("10.10") + Decimal("0.20")` produce `Decimal("10.30")`. Nel codice applicativo gli importi non vengono convertiti in `float` per sommare saldi, spese o budget.

`parse_money()` interpreta il testo inserito o importato, verifica che sia numerico e controlla grandezza e precisione. `money_it()` trasforma il valore in una stringa come `1.234,56 €`. La conversione di presentazione non modifica il dato salvato. Per un input senza ambiguità usa sempre due cifre decimali: per esempio `1.234,00` oppure `1234.00`.

Le aggregazioni SQL usano centesimi interi: ogni importo a due decimali viene moltiplicato per 100, arrotondato e convertito a intero prima della somma. Questo evita gli accumuli in virgola mobile di `SUM(amount)` su SQLite; il risultato viene riconvertito in `Decimal` al confine del servizio. La stessa espressione usa valori numerici nativi su PostgreSQL. In SQLite rimane il limite dell'accumulatore intero a 64 bit: un cumulato oltre circa 9,22 × 10¹⁸ centesimi produce un errore, non è un volume monetario supportato da questi benchmark.

Nei grafici, le somme arrivano dal database; Python completa mesi e giorni senza operazioni e serializza i valori come stringhe numeriche. Plotly le interpreta per disegnare le coordinate; il denaro non viene ricalcolato dal grafico. Una percentuale o una media può avere più decimali durante il calcolo, pur venendo mostrata arrotondata nell'interfaccia.

## 15. Filtri, query e preferenze nel dettaglio

### 15.1 `Filters` come interpretazione condivisa

`Filters` è una *dataclass*: un oggetto che riunisce l'intervallo, le opzioni disponibili, gli identificativi selezionati, i tipi, la ricerca e un eventuale errore. La costruzione avviene in `Filters.parse()`. Le funzioni `transactions()` e `transfers()` restituiscono query ORM coerenti con quella selezione; `context()` prepara valori e riepiloghi per il template.

Una *query* è una richiesta di dati al database. Un *QuerySet* Django descrive quali righe selezionare; normalmente la richiesta effettiva parte quando quelle righe vengono lette o iterate. Centralizzare questa costruzione riduce il rischio che una tabella e il suo CSV interpretino diversamente lo stesso filtro.

### 15.2 Parametri degli indirizzi

| Parametro | Esempio | Significato |
| --- | --- | --- |
| `periodo` | `3m`, `tutto`, `custom`, `mese:2026-09` | Preset, intervallo o mese selezionato. |
| `inizio`, `fine` | `01/09/2026`, `30/09/2026` | Estremi inclusivi dell'intervallo personalizzato. |
| `conto` | `conto=1&conto=2` | Più conti; `conto=` indica Nessuno e `conto=tutti` indica Tutti. Gli ID dipendono dal database. |
| `categoria` | `categoria=3&categoria=giroconto` | Categorie e, facoltativamente, trasferimenti. |
| `sottocategoria` | `sottocategoria=8` | Ulteriore restrizione dentro le categorie selezionate. |
| `tipo` | `Entrata`, `Uscita necessaria` | Tipi contabili in Movimenti; il browser codifica gli spazi nell'URL. |
| `q` | `supermercato` | Ricerca testuale nel registro. |
| `vista` | `tabella` oppure `lista` | Presentazione dei movimenti. |
| `sort` | `-date`, `amount`, `-balance` | Ordinamento del registro; il meno indica il verso decrescente. |
| `per_pagina`, `pagina` | `50`, `2` | Dimensione e numero della pagina del registro. |
| `dettaglio` | `categoria` o `sottocategoria` | Livello delle barre della Overview. |
| `ordine` | `name`, `-amount`, `average` | Ordinamento del riepilogo della Overview. |
| `mese` | `2026-09` | Mese della pagina Budget. |

Non è necessario scriverli a mano: li costruisce l'interfaccia. Conoscerli aiuta a capire gli URL, riprodurre un filtro e individuare il punto del codice da controllare.

### 15.3 Regole che evitano letture ambigue

I preset sottraggono mesi di calendario dalla data corrente, correggendo il giorno quando il mese di arrivo è più corto. «Un mese» non significa necessariamente 30 giorni. **Tutto** parte dalla più vecchia operazione o giroconto e arriva a oggi, ignorando date residue del filtro precedente; un mese scelto nella Overview copre il mese di calendario completo.

La Dashboard applica periodo e conti, mantenendo tutte le classificazioni per riconciliare i saldi. La Overview e Movimenti possono restringere categorie e sottocategorie. Un trasferimento non ha sottocategoria: una selezione che restringe davvero le sottocategorie lo esclude; per includerlo usa la voce Giroconto con una selezione di sottocategorie non restrittiva.

I conti archiviati vengono letti per lo storico. Una selezione esplicitamente vuota rimane vuota; soltanto un parametro assente senza preferenze salvate oppure `conto=tutti` indica il consolidato; un identificativo inesistente non viene trasformato in un conto valido. Gli ID validi sono verificati contro gli oggetti disponibili.

### 15.4 Aggiornamento senza ricaricare tutta la schermata

`filters.js` intercetta i comandi previsti, costruisce l'URL e chiede a Django il nuovo HTML. Della risposta sostituisce `.page-content`, mantenendo la cornice della pagina. Prima di ridisegnare i grafici elimina le istanze Plotly precedenti e poi richiama l'inizializzazione dei componenti.

Vengono conservati posizione di scorrimento e stato aperto/chiuso dei pannelli contrassegnati con `data-persist`; la ricerca riacquista il focus dopo l'aggiornamento. Le selezioni aspettano circa 180 ms, la ricerca 350 ms e le date valide 500 ms dopo la digitazione, evitando richieste intermedie. Lo stato dei pannelli viene letto immediatamente prima di sostituire il contenuto, quindi un pannello chiuso durante una richiesta non viene riaperto dalla risposta. Il focus e lo scorrimento delle opzioni vengono mantenuti quando ancora pertinenti. Una nuova richiesta annulla quella precedente, così una risposta più lenta non sovrascrive un filtro appena scelto.

L'indirizzo viene aggiornato anche nella cronologia del browser. Se l'aggiornamento parziale fallisce, il codice tenta una normale navigazione all'URL. Grafici, dialogo e selezioni dinamiche richiedono JavaScript; la produzione dell'HTML e le validazioni restano sul server.

## 16. Grafici e indicatori: origine di ogni numero

### 16.1 Un insieme di dati, più presentazioni

`analytics()` usa `flow_groups()` per ricevere somme e conteggi SQL raggruppati per mese, tipo, categoria e sottocategoria. `boundary_queries()` seleziona nel database soltanto i giroconti che attraversano il perimetro dei conti. Per la serie del saldo, `daily_flows()` restituisce i delta già raggruppati per giorno. Non vengono istanziati tutti i movimenti dello storico per preparare i grafici; Python lavora sui gruppi risultanti.

La funzione costruisce l'elenco completo dei mesi dell'intervallo prima di distribuire le somme aggregate. Un mese senza movimenti conserva quindi valori pari a zero. Da questo insieme ricava totali, aggregazioni per tipo/categoria, legenda della ciambella e dati delle barre: cambiare modalità del grafico non cambia la popolazione su cui sono state calcolate le somme.

| Elemento | Calcolo o contenuto |
| --- | --- |
| Entrate | Somma dei movimenti di tipo Entrata e dei trasferimenti in ingresso dal perimetro esterno. |
| Uscite | Somma delle uscite, degli investimenti e dei trasferimenti diretti fuori dal perimetro. |
| Differenza netta | Entrate meno uscite. |
| Saldo giornaliero | Saldo prima dell'intervallo più variazioni cumulate, giorno per giorno. |
| Flussi Totale | Per ogni mese, una serie entrate e una uscite. Il netto ha un grafico separato. |
| Flussi Per tipo | Stessi importi ripartiti secondo i tipi contabili. |
| Flussi Per categoria | Stessi importi ripartiti per categoria e verso del flusso; i nomi in legenda e tooltip mostrano soltanto la categoria, senza suffissi entrate/uscite. La separazione delle barre resta affidata a `offsetgroup`. |
| Ciambella | Ripartizione delle sole uscite del perimetro, con importi, percentuali e conteggi. |
| Barre spese | Uscite mensili raggruppate per categoria o per sottocategoria. |
| Media mensile | Totale della categoria o sottocategoria scelta diviso per il numero di mesi toccati dal filtro. |

La Dashboard e il Budget rispondono a domande differenti quando selezioni un solo conto: un giroconto in uscita riduce la disponibilità di quel conto nella Dashboard, ma non è una spesa da imputare a un budget.

### 16.2 Giorni vuoti e medie

La serie giornaliera aggiunge un punto per ogni data. Se il giorno non contiene movimenti, la variazione è zero e il saldo resta uguale al giorno precedente. La linea può essere visualizzata con una leggera interpolazione morbida; i valori dei punti rimangono quelli contabili calcolati.

Per una categoria con 60 € ad aprile, zero a maggio e 90 € a giugno, il totale è 150 € e la media mensile è **50 €**, non 75 €. Il denominatore comprende tutti e tre i mesi. Se il periodo inizia a metà aprile, aprile conta comunque come un mese; la media non è una stima della spesa mensile a parità di giorni osservati.

### 16.3 Colori e legende

| Tipo | Colore in `TYPE_COLORS` |
| --- | --- |
| Entrata | `#00C878` |
| Trasferimento in entrata | `#00BEEA` |
| Uscita necessaria | `#FF3B52` |
| Uscita extra | `#FF9500` |
| Trasferimento in uscita | `#FF4081` |
| Investimento | `#8354FF` |

La palette dei tipi è definita in `wallet/services/colors.py`. Il colore di una categoria parte da `Category.color` e viene reso più vivace da `vivid_category_color()`: conserva la tonalità, aumenta la saturazione e regola la luminosità, lasciando neutri i grigi. La trasformazione viene applicata in modo uniforme a grafici, indicatori, filtri, lista e budget; il valore salvato e il selettore colore restano quelli scelti dall’utente. Questa modifica è solo di presentazione e non richiede una migrazione dei dati. `charts.js` controlla dimensioni, margini, assi, separatori e legende. Nascondere una serie nella legenda cambia **la visualizzazione del grafico**, non i filtri, il totale delle schede o i dati nel database.

La formattazione dei tooltip degli importi viene preparata dal server. Questo mantiene i separatori italiani anche se il browser ha una lingua differente. Ciambella, istogrammi e Andamento del saldo condividono una scheda HTML bianca: la ciambella separa nome, importo, percentuale e conteggio; le barre separano nome della serie, mese e importo; il grafico del saldo mostra data italiana e saldo del giorno su righe distinte. Una linea verticale tratteggiata attraversa il grafico in corrispondenza del giorno evidenziato; segue il tooltip e scompare uscendo dal grafico. La stessa presentazione copre Totale/Tipo/Categoria, netto mensile e uscite Categoria/Sottocategoria. I testi vengono assegnati con `textContent`. Il numero di mesi resta utilizzato nei calcoli delle medie ma non compare accanto al titolo Andamento netto mensile.

## 17. Form, modifiche e gestione della tassonomia

### 17.1 Validazione su più livelli

Il controllo nel browser rende l'interazione più comoda: per esempio mostra soltanto le sottocategorie della categoria selezionata e segnala due conti uguali in un giroconto. Il form Django controlla comunque gli stessi dati quando arrivano al server. Le regole dei modelli e i vincoli del database completano la validazione.

`ItalianMoneyField` è un campo form personalizzato basato su `DecimalField`. `TransactionForm.clean()` verifica il rapporto categoria–sottocategoria e la scelta facoltativa `expense_kind`; `save()` conserva il tipo validato. Il modello usa `kind_matches_subcategory()` per ammettere soltanto l’uguaglianza o il cambio fra Uscita necessaria e Uscita extra. Il cambio riguarda il movimento, non la tassonomia; `full_clean()` applica la stessa regola nel ripristino JSON. `TransferForm` sceglie i conti ammessi e propone «Giroconto» quando la descrizione è vuota. La data dei nuovi inserimenti viene proposta come data odierna.

In modifica, il form può mantenere il conto o la classificazione storica già archiviati. Questo consente di correggere un vecchio movimento senza obbligare a riattivare tutte le sue anagrafiche.

### 17.2 Eliminazione e ricalcolo

Le azioni di eliminazione di movimenti e giroconti richiedono un POST e mostrano una conferma nell'interfaccia. Eliminare un giroconto rimuove il record `Transfer`; le due gambe derivate scompaiono insieme. I saldi e i grafici si aggiornano alla successiva lettura perché derivano dalle operazioni effettivamente persistite.

I form non assegnano direttamente un nuovo saldo finale al conto. È l'eliminazione o la modifica dell'operazione a cambiare il registro da cui quel saldo viene ricostruito.

### 17.3 Importare l'elenco di categorie

L'importazione della tassonomia in Categorie è una procedura diversa dall'importazione di movimenti. `import_taxonomy()` legge un CSV UTF-8 separato da virgole, fino al limite di 1 MB del form dedicato, con uno dei due schemi:

| Schema italiano | Schema bilingue: colonne utilizzate |
| --- | --- |
| `Categoria` | `Category_IT` |
| `Sottocategoria` | `Subcategory_IT` |
| `Colore` | `Color` |
| `Tipo` | `Type_IT` |

I nomi contenenti virgole devono essere racchiusi tra virgolette nel CSV. Le eventuali colonne inglesi del file bilingue non creano una seconda lingua dell'interfaccia: vengono usate le colonne italiane indicate.

Il file rappresenta **l'elenco attivo completo**. La funzione valida le righe, archivia le categorie e sottocategorie precedenti e riattiva o crea quelle presenti nel file. Le voci omesse restano nel database come archiviate. Caricare un file con una sola nuova voce, quindi, archivierebbe le altre: per aggiungere una singola voce puoi usare il form manuale.

Se una sottocategoria già usata cambierebbe tipo contabile, la procedura segnala l'errore. L'intera operazione è dentro una transazione: un errore non lascia metà elenco aggiornato e metà no. Rinominare una voce nel CSV può essere interpretato come nuova voce più archiviazione della precedente; per correggere il nome dello stesso oggetto usa il form di modifica.

## 18. Importazione, export e backup: percorso interno

### 18.1 Le fasi dell'importazione dei movimenti

| Fase | Componente | Dati prodotti o conservati |
| --- | --- | --- |
| Caricamento | `UploadForm`, `read_tabular` | Intestazioni e righe del CSV oppure del foglio XLSX attivo. |
| Mappatura | `guess_column`, `import_view` | Associazione fra campi Wallet e posizioni delle colonne. |
| Analisi | `_analyze_import` | Valori normalizzati, errori, avvisi e possibili duplicati per riga. |
| Revisione | `import_review_context` | Righe da correggere, nuovi conti e confronti sui saldi iniziali. |
| Conferma | `import_confirm` | Nuova validazione delle correzioni e scrittura atomica. |
| Riepilogo | `import_done.html` | Conteggio delle aggiunte, duplicati ignorati e avvisi di saldo. |

I passaggi intermedi degli estratti generici usano le chiavi di sessione `wallet_import_raw`, `wallet_import_mapping` e `wallet_import_rows`. Per il formato nativo, `wallet_import_native` seleziona il percorso di validazione e revisione CSV Wallet. Non sono ancora righe finanziarie: sono materiale di revisione. Annullare l'importazione rimuove questo stato senza cancellare i movimenti già presenti nel Wallet.

La scelta delle colonne può essere suggerita dal nome dell'intestazione, ma è l'associazione confermata dall'utente a stabilire quale dato leggere. Per le sottocategorie, un nome univoco può bastare al riconoscimento; se il nome si ripete in più categorie, la categoria aiuta a distinguerle. Una classificazione non risolta rimane da correggere nella revisione.

### 18.2 Errori bloccanti e avvisi

Una data non valida, un importo mancante o una classificazione non assegnata impediscono di confermare correttamente la riga. Se al momento della conferma una riga resta invalida, il salvataggio dell'intero gruppo viene bloccato e le correzioni inviate rimangono disponibili.

Un avviso richiede lettura ma non equivale sempre a un errore bloccante. Per esempio, un tipo nel file diverso dalla tassonomia viene segnalato e prevale il tipo della sottocategoria. Se un orario nel file non viene riconosciuto durante l'analisi, il sistema avvisa e mantiene l'ordine del file; se nella revisione si inserisce un orario non valido, la conferma viene bloccata. Un saldo progressivo non leggibile viene segnalato, senza inventare il valore mancante.

### 18.3 Ricostruzione del saldo iniziale da un estratto

Supponiamo di importare, per un conto nuovo, una spesa di 20 € seguita da una spesa di 30 €. Il file contiene un saldo di 950 € soltanto dopo la seconda operazione. Il cumulato delle due operazioni è −50 €; quindi il saldo prima delle operazioni è:

**950 € − (−50 €) = 1.000 €.**

Il calcolo deve includere anche la prima riga, benché non abbia un saldo progressivo. `import_review_context` segue questa logica e confronta le inferenze ottenute da più righe. Se non coincidono, mostra l'incoerenza. Un conto già utilizzato non vede automaticamente riscritto il proprio saldo iniziale in base a un nuovo estratto.

Questo controllo presuppone che le operazioni dell'intervallo siano complete e correttamente ordinate. La colonna «saldo» del file è un riferimento di verifica: non sostituisce il saldo ricalcolato dal registro.

### 18.4 Duplicati e transazione atomica

L'identificativo esterno è il confronto più forte: non possono esistere due movimenti dello stesso conto con il medesimo identificativo non vuoto. Il confronto per data, descrizione e importo è invece una segnalazione di possibile duplicato, perché due spese uguali nello stesso giorno possono essere reali.

La ricerca dei duplicati riguarda soltanto identificativi e firme presenti nel file, attraverso query a blocchi; non carica più tutta la tabella dei movimenti. Durante la scrittura vengono riconosciuti anche duplicati ripetuti nello stesso file. La conferma prepara le righe prima di scrivere e usa `transaction.atomic()` per il gruppo di modifiche.

Le righe sono ancora validate individualmente in memoria, ma vengono inserite con `bulk_create` in blocchi fino a 400 oggetti (Django può ridurre ulteriormente il blocco per i limiti del database). `validate_instance()` esegue i controlli dei campi e `clean()` del modello, compresi importi positivi, lunghezze e tipo della sottocategoria. I riferimenti vengono risolti da oggetti già letti; identità e duplicati sono verificati a blocchi; i vincoli SQL restano attivi. Non viene chiamato `save()` per ogni riga e non si ignorano errori di unicità con `ignore_conflicts`. Se in futuro aggiungi regole in `save()` o segnali, devi verificare anche il percorso di importazione: `bulk_create` non li esegue. *Atomico* significa che le scritture di quel gruppo vengono confermate insieme oppure annullate insieme quando la procedura incontra un errore. Non significa che il programma possa ricostruire da solo informazioni assenti nell'estratto.

### 18.5 Export CSV e backup JSON

`export_csv()` richiama lo stesso servizio delle righe di Movimenti, con ordine cronologico e gli stessi filtri, senza applicare la paginazione visuale. Scrive i saldi dopo operazione, gli importi con segno e i campi descrittivi. `safe_cell()` protegge i campi testuali che potrebbero essere interpretati come formule da un foglio di calcolo. Nel formato v2 anche gli apostrofi iniziali sono codificati in modo reversibile, così note e descrizioni vengono ricostruite senza aggiunte o perdite di caratteri.

`backup()` usa invece `dumpdata` limitato all'app `wallet`: salva i record e i collegamenti dei modelli finanziari. Il file è una *fixture*, cioè una rappresentazione JSON che Django può ricaricare con `loaddata`. Non contiene le tabelle dell'autenticazione o le sessioni d'importazione.

`restore_backup()` controlla conferma, estensione e limite di 100 MB, verifica che il JSON contenga soltanto modelli dell'app, sostituisce i dati in ordine compatibile con le relazioni e valida gli oggetti caricati. Qualunque errore nella transazione ripristina lo stato precedente. Il proprietario continua ad accedere con le credenziali dell'installazione di destinazione.

### 18.6 Formato CSV Wallet v2

Le prime dieci colonne restano `Data`, `Descrizione`, `Importo`, `Categoria`, `Sottocategoria`, `Tipo`, `Saldo dopo operazione`, `Conto o carta`, `Note`, `Identificativo`. Si aggiungono:

| Colonna | Significato |
| --- | --- |
| `Formato Wallet` | Versione del protocollo: `2`. Versioni sconosciute vengono rifiutate. |
| `Operazione` | `movimento` oppure `giroconto`. |
| `UUID operazione` | Identità stabile del movimento o del giroconto; condivisa dalle due gambe. |
| `Conto origine`, `Conto destinazione` | Collegamento completo del giroconto, anche esportando un solo conto. Vuoti per i movimenti ordinari. |
| `Orario` | Orario ISO locale, facoltativo, compresi eventuali microsecondi. |
| `Ordine` | `order_index` originale. |
| `Sequenza origine` | Identificativo numerico originale usato per stabilizzare le parità d'ordine durante la ricostruzione; non forza la chiave primaria del database di destinazione. |
| `Saldo iniziale conto` | Saldo iniziale originale del conto della riga. |
| `Saldo iniziale controconto` | Saldo iniziale dell’altro conto del giroconto; vuoto per i movimenti ordinari. |
| `Tipo predefinito sottocategoria` | Ventunesima colonna, facoltativa in lettura per compatibilità con i CSV v2 precedenti. Conserva il tipo della tassonomia separato dal `Tipo` scelto sul movimento; vuota per i giroconti. |

`import_wallet_csv()` usa lo stesso percorso di validazione per anteprima e conferma. La conferma ripete i controlli perché il database potrebbe essere cambiato dopo l'anteprima. Prima del pulsante **Conferma importazione** non vengono creati conti, classificazioni o operazioni. L'anteprima mostra le prime 100 operazioni e i conteggi dell'intero file, fino a 10.000 righe; una coppia di gambe conta come due righe del file e una sola operazione.

Le operazioni con lo stesso UUID e gli stessi dati vengono riconosciute come già presenti. Dati discordanti fra due gambe, conti coincidenti, segno incompatibile, UUID già usato con contenuto diverso o identificativo bancario assegnato a un altro UUID bloccano tutto il gruppo. Un conflitto non aggiorna né elimina record esistenti. Anche un errore nell'inserimento dei giroconti annulla eventuali movimenti ordinari già inseriti nella stessa transazione.

Le anagrafiche mancanti vengono create dai nomi del file. Il tipo della sottocategoria deriva da `Tipo predefinito sottocategoria`, mentre `Tipo` è il valore del movimento: possono differire soltanto fra Uscita necessaria e Uscita extra. Se la nuova colonna è presente, il suo valore deve coincidere con la sottocategoria esistente. Nei vecchi file a 20 colonne il tipo della riga fornisce il predefinito per le nuove sottocategorie; per quelle esistenti viene verificata la compatibilità. Gli altri metadati mancanti usano i valori predefiniti dell’applicazione. Conti e classificazioni già archiviati restano riconoscibili per mantenere lo storico. I saldi iniziali dei conti esistenti non vengono modificati automaticamente. `Saldo dopo operazione` è informativo: non viene usato per riscrivere i saldi e non sostituisce lo storico eventualmente escluso dal filtro.

Per una reimportazione fedele conserva tutte le colonne e non usare il CSV come sistema di modifica in massa. Per correggere operazioni esistenti usa i form dell'app. Un archivio esportato integralmente e importato in un database finanziario vuoto ricostruisce movimenti, giroconti, UUID e saldi dei conti rappresentati; il ripristino completo di budget, preferenze e metadati resta affidato al JSON.

## 19. Budget: formule e scelte di calcolo

Il servizio `budget_context()` interpreta il mese, valida gli eventuali limiti inviati e prepara i dati della pagina. Per il mese corrente considera le operazioni fino a oggi; per un mese passato usa il relativo periodo completo. La pagina mostra valori effettivamente registrati, non previsioni automatiche.

| Indicatore | Regola |
| --- | --- |
| Speso della categoria | Somma dei movimenti della categoria con tipo Uscita necessaria, Uscita extra o Investimento. |
| Residuo | Budget meno uscite di tutti i conti; per la singola categoria, limite meno speso. |
| Sforamento | Se il residuo è negativo, etichetta e importo assoluto della spesa oltre budget. |
| Percentuale usata | Speso diviso limite per 100, quando il limite è maggiore di zero. |
| Stato regolare | Spesa sotto l'85% del limite positivo. |
| Stato vicino al limite | Percentuale almeno 85%, senza aver superato il limite. |
| Stato superato | Spesa maggiore del limite impostato. |
| Larghezza della barra | Percentuale limitata fra 0 e 100 per la sola rappresentazione grafica. |

Esempio: limite 80 €, speso 65 €, residuo 15 € e utilizzo 81,25%. Con un limite di 60 €, gli stessi 65 € danno residuo contabile −5 €, presentato come **Sforamento 5 €**; la barra arriva al massimo della propria larghezza, mentre i numeri continuano a mostrare la spesa completa.

Con limite zero non si calcola una divisione per zero: viene mostrato «Limite zero» e qualunque spesa positiva risulta oltre budget. Senza limite, viene mostrata l'assenza di un budget. Il totale dei limiti comprende soltanto quelli impostati; il totale delle spese può includere anche categorie per cui non hai impostato un limite.

Spese per tipo mostra soltanto Tipo, Spesa e Sulle entrate, con la riga TOT del mese selezionato; la colonna Precedente è stata rimossa. Lo storico elenca i **12 mesi precedenti**, escluso quello selezionato, e aggrega uscite e limiti con `TruncMonth` e `Sum`.

I limiti non si copiano automaticamente al mese successivo. Ogni mese ha proprie righe `CategoryBudget` o `SubcategoryBudget`; questa scelta mantiene indipendenti decisioni e storico. Un giroconto non entra in queste somme perché il servizio legge i movimenti ordinari, non il modello `Transfer`.

### 19.1 Limite unico oppure somma delle sottocategorie

Esempio: Casa ha Affitto 600 €, Utenze 100 € e Condominio 50 €. Il budget Casa è **750 €**. Un eventuale vecchio limite Casa di 800 € viene sostituito, non aggiunto: il budget non diventa 1.550 €. Tornando a Limite unico e salvando 700 €, le righe dettagliate di quel mese vengono rimosse e il limite torna a essere 700 €.

Ogni sottocategoria ha una barra calcolata come **speso / budget × 100** e la stessa indicazione di stato della categoria: blu sotto l’85%, ambra dall’85% fino al limite, rosso oltre il limite. La barra si ferma visivamente al 100%, mentre l’etichetta mostra anche percentuali superiori. Le barre si aggiornano durante la digitazione e sono presenti anche nella pagina renderizzata dal server.

Un campo di sottocategoria vuoto significa limite non impostato; zero significa limite esplicito pari a zero. Se tutti i campi sono vuoti non rimane un budget per quella categoria nel mese. Le spese delle sottocategorie senza limite continuano a concorrere alla spesa effettiva della categoria e ai totali. Limiti e spese delle voci archiviate restano visibili.

Il salvataggio controlla prima tutti gli importi inviati, compresi formato, due decimali e valore non negativo. In caso di errore nessun budget viene scritto; gli importi da correggere restano nei dettagli aperti. La scrittura avviene in una transazione; sul database PostgreSQL le categorie interessate vengono bloccate durante la sostituzione, per serializzare modifiche concorrenti. Il calcolo di riepiloghi e storico usa entrambe le tabelle di budget, senza duplicare il totale della categoria.

`js/budget.js` usa centesimi interi `BigInt` per aggiornare durante la digitazione il totale della categoria (anche nella riga chiusa), i residui delle sottocategorie e della categoria, le relative barre di utilizzo, il totale del mese e il residuo complessivo. Cambiare modalità aggiorna anche la fonte del totale: Limite unico oppure Somma sottocategorie. Un avviso indica le modifiche non ancora salvate; il database cambia soltanto con Salva budget del mese. Se un importo è invalido, la categoria segnala l’errore e i totali interessati non mostrano una somma parziale. Zero rimane distinto da un campo vuoto. Le percentuali usano l’arrotondamento dei calcoli Python; soltanto la larghezza grafica della barra viene convertita in Number. Il browser non decide quali record scrivere; questo spetta a `services/budget.py`. I form e l’importazione della tassonomia impediscono di spostare o cambiare tipo a una sottocategoria che ha già budget, per preservare il significato dello storico.

## 20. Interfaccia: template, CSS, JavaScript e icone

### 20.1 Template condivisi e pagine

`base.html` definisce lingua, caricamento degli asset, struttura generale, messaggi, navigazione, dialogo per il nuovo movimento e area principale. Le singole pagine lo estendono e riempiono il blocco dei contenuti.

| Template o gruppo | Compito |
| --- | --- |
| `components/nav.html` | Cinque destinazioni e stato della sezione corrente, riutilizzati nelle navigazioni desktop/mobile. |
| `components/filters.html` | Periodo, date e selezioni; abilita categorie/tipi dove previsti dal contesto. |
| `components/kpis.html` | Riepilogo finanziario e dettagli espandibili. |
| `components/new_button.html` | Azione per aprire il dialogo di inserimento, con conto selezionato quando applicabile. |
| `components/settings_header.html` | Titolo Account e impostazioni, uscita confermata, menu condiviso e titolo della sezione sotto il menu. |
| `components/settings_nav.html` | Collegamenti fra conti, categorie, importazione, backup e account. |
| `home.html`, `dashboard.html` | Pagine di sintesi e analisi. |
| `transactions.html` | Tabella, lista e paginazione del registro. |
| `transaction_form.html`, `transfer_form.html` | Inserimento e modifica delle due famiglie di operazioni. |
| `budget.html`, `settings.html`, `categories.html` | Budget e anagrafiche. |
| `import_upload.html`, `import_map.html`, `import_review.html`, `import_done.html` | Passaggi visibili dell'importazione. |
| `backup.html` | Download e ripristino confermato. |
| `registration/` | Accesso e cambio password. |

I percorsi della tabella sono relativi a `wallet/templates/wallet/`, tranne `registration/`, che si trova sotto `wallet/templates/`.

`wallet_tags.py` registra filtri come `euro` e il tag `query_url`, che cambia determinati parametri mantenendo gli altri. Questo evita di costruire a mano in ogni template i collegamenti di ordinamento o paginazione.

### 20.2 Token CSS e responsive

All'inizio di `app.css`, il blocco `:root` contiene variabili condivise: `--primary` e `--primary-dark` per i blu, `--bg` e `--surface` per gli sfondi, `--ink` e `--muted` per il testo, raggi, ombra, spaziature e font. Cambiare un token aggiorna tutti i componenti che lo usano; non occorre cercare una stessa tinta in decine di regole.

Le regole successive definiscono pulsanti, campi, pannelli, badge, tabelle, grafici e stati vuoti. Le media query adattano disposizione, filtri e navigazione inferiore alle larghezze mobili; la tabella dei movimenti conserva tutte le colonne in un contenitore scorrevole. Un unico token `--font`, basato su `system-ui` e sui relativi fallback di sistema, governa tutta l’app: pulsanti, campi, tabella e lista Movimenti. Plotly legge la famiglia calcolata del corpo della pagina, così anche grafici e tooltip sono coerenti. Non viene scaricato un font remoto.

Le icone strutturali sono simboli SVG in `components/icons.html`, condivisi da `base.html` e dalla pagina di accesso. Comprendono il budget a settori, il saldo finale e le frecce di entrata/uscita con un tratto più marcato. I selettori CSS delle icone sono circoscritti ai componenti, per non alterare gli SVG di Plotly. Le icone delle sottocategorie passano invece da `icon_config.py`, che associa identificatori e nomi a glifi. Il progetto corrente non cerca automaticamente file SVG nominati categoria–sottocategoria: un eventuale sistema di asset SVG dedicati richiederebbe un'integrazione esplicita.

### 20.3 Responsabilità dei moduli JavaScript

| Modulo | Cosa controlla |
| --- | --- |
| `app.js` | Inizializzazione comune, dialogo, conto proposto e cambio della modalità dei flussi. |
| `js/filters.js` | Applicazione automatica, validità delle date, chiusura esterna/Escape, conservazione di focus e pannelli, richieste annullabili, mese, ordinamento e paginazione. |
| `js/charts.js` | Creazione/aggiornamento Plotly, font condiviso, tooltip HTML di ciambella e istogrammi e visibilità delle serie. |
| `js/budget.js` | Modalità limite unico/sottocategorie, aggiornamento immediato di somme, residui e barre con centesimi interi e avviso delle modifiche da salvare. |
| `js/forms.js` | Schede colorate accessibili, sottocategorie dinamiche, predefinito e scelta Necessaria/Extra, anteprima giroconto e conferme di eliminazione/uscita. |
| `js/auth.js` | Mostra/nasconde la password nel login con etichetta accessibile e stato `aria-pressed`; non richiede Plotly o la shell dell’app. |

Gli attributi `data-*` nei template collegano l'HTML al comportamento, per esempio `data-filter-form`, `data-chart` e `data-transaction-form`. Rinominare un attributo richiede di aggiornare anche il selettore JavaScript corrispondente.

`json_script` inserisce nel documento un blocco JSON leggibile dal JavaScript e protegge i caratteri che potrebbero interrompere il contesto HTML. I nomi di categorie o descrizioni non diventano così codice JavaScript eseguibile.

### 20.4 Accessibilità prevista

La barra superiore contiene l’icona e il solo nome **Wallet**, senza sottotitolo o iniziale del proprietario. I titoli di pagina e pannello sono privi delle frasi introduttive e descrittive precedenti; restano gli aiuti dei campi e i messaggi funzionali. Il login usa la stessa identità visiva, una scheda centrale e un comando per vedere temporaneamente la password.

Le pagine includono etichette dei campi, collegamento per saltare al contenuto, nomi delle navigazioni, stato della pagina corrente e messaggi di aggiornamento per i lettori di schermo. Il dialogo usa l'elemento nativo `dialog` e può essere chiuso con Escape. Questi accorgimenti aiutano l'uso con tastiera e tecnologie assistive; non equivalgono a una certificazione completa di accessibilità.

## 21. Configurazione, sicurezza e distribuzione spiegate

### 21.1 Quali file avviano il progetto

| File | Funzione |
| --- | --- |
| `manage.py` | Punto di ingresso per comandi Django come avvio, migrazioni e test. |
| `wallet_project/settings.py` | Configurazione letta all'avvio. |
| `wallet_project/urls.py` | Mappa fra indirizzi e viste. |
| `wallet_project/wsgi.py` | Espone l'applicazione a un server WSGI come Gunicorn. |
| `wallet/apps.py` | Configurazione dell'app Django Wallet. |
| `wallet/views/__init__.py` | Rende disponibili le viste dei moduli separati agli URL. |
| `wallet/services/__init__.py` | Mantiene un punto di importazione per le funzioni comuni già usate dal progetto. |
| `requirements.txt` | Dipendenze necessarie per l'applicazione. |
| `requirements-test.txt` | Dipendenze dell'app più Playwright per i test browser. |

Gli altri file `__init__.py` indicano i pacchetti Python o mantengono punti d'importazione. Non sono database, configurazioni segrete o copie dell'applicazione.

### 21.2 Perché il CSS funziona diversamente in locale e in produzione

I sorgenti si trovano in `wallet/static/wallet/`. La prima parte `wallet/static/` è la posizione dove Django cerca gli asset dell'app; il secondo `wallet/` è uno spazio di nomi che evita collisioni con eventuali altre app.

Il percorso del sorgente `wallet/static/wallet/app.css` diventa quindi l'URL **`/static/wallet/app.css`**. Gli altri asset seguono la stessa regola. Un URL che iniziasse con `/wallet/static/` non corrisponderebbe alla configurazione presente.

Con `runserver` e debug attivo, Django trova e serve i sorgenti. In produzione, `collectstatic` raccoglie gli asset nella directory `staticfiles/`, produce i nomi versionati e le versioni compresse. WhiteNoise serve questi file mentre Gunicorn esegue l'applicazione. Il nome versionato cambia quando cambia il contenuto, così il browser può conservare a lungo gli asset senza usare per errore il vecchio CSS dopo un rilascio.

`collectstatic` **non copia movimenti, conti o database**. Cambia soltanto la preparazione dei file dell'interfaccia. `staticfiles/` è una cartella generata, da ricreare in build; le modifiche si fanno ai sorgenti sotto `wallet/static/wallet/`.

### 21.3 Come viene limitato l'accesso

`WalletAuthenticationForm` chiama `is_wallet_owner()` durante l'accesso. Sono richiesti utente attivo e superuser; quando il nome del proprietario è configurato deve coincidere. `SingleOwnerMiddleware` applica nuovamente questa regola alle sessioni già aperte, così una sessione diventata non autorizzata viene chiusa.

Le viste finanziarie richiedono autenticazione. Le modifiche passano attraverso form POST protetti da CSRF. Il logout è anch'esso un'azione POST. Le password sono gestite dal sistema di autenticazione Django, mentre `WALLET_SECRET_KEY` è una chiave dell'installazione e non la password con cui accedi al Wallet.

L'architettura ha un solo spazio finanziario: i modelli `Account` e `Transaction` non hanno un campo proprietario. Aggiungere un normale utente Django non crea un secondo Wallet; trasformare il progetto in un servizio multiutente richiederebbe nuovi modelli o riferimenti di proprietà, filtri di accesso e test dedicati.

### 21.4 Ambiente locale e produzione

| Aspetto | Locale | Produzione |
| --- | --- | --- |
| Database abituale | SQLite su file. | PostgreSQL obbligatorio nella configurazione di produzione. |
| Processo web | `manage.py runserver`. | Gunicorn dietro l'infrastruttura HTTPS. |
| Debug | Attivo per impostazione locale predefinita. | Disattivato. |
| Asset | Serviti dai sorgenti durante lo sviluppo. | Raccolti con `collectstatic` e serviti da WhiteNoise. |
| Segreto e proprietario | Configurabili; la demo imposta il proprio utente. | Richiesti esplicitamente all'avvio. |
| Dati persistenti | File SQLite nella posizione scelta. | Database gestito separatamente dal processo web. |

`Dockerfile` prepara l'immagine, ma non pubblica da solo il servizio e non crea un database PostgreSQL. Le migrazioni, l'utente proprietario, i segreti, il dominio e il database vanno configurati nell'ambiente di destinazione secondo la procedura della sezione 10.

`/healthz/` esegue una piccola query `SELECT 1`: risponde `ok` se il database è raggiungibile oppure HTTP 503 se non lo è. È accessibile senza login ed esente dal redirect HTTPS per consentire le sonde dell'infrastruttura; non restituisce i dati finanziari e non è un collaudo completo di tutte le funzioni.

## 22. Test: cosa verificano e come usarli durante lo sviluppo

I test sono esempi controllati eseguiti automaticamente: preparano dati di cui si conosce il risultato, eseguono una funzione o una richiesta e confrontano il risultato ottenuto con quello atteso. Non leggono il database demo per decidere se il programma funziona: costruiscono un ambiente isolato con le situazioni necessarie.

Per esempio, un test può creare due conti, inserire un trasferimento di 100 € e controllare tre risultati: il primo conto diminuisce di 100 €, il secondo aumenta di 100 € e il totale non cambia. Un altro può produrre un backup invalido e verificare che il ripristino non abbia modificato i dati precedenti.

### 22.1 Le suite Python

| Suite | Scopo principale |
| --- | --- |
| `wallet/tests/test_regressions.py` | Proteggere i comportamenti già presenti: tipi e segni, ordine del registro, importazione, budget, backup, accesso e tassonomia. |
| `wallet/tests/test_application.py` | Verificare requisiti della revisione e difetti corretti: cinque pagine, perimetri, filtri, giorni/mesi vuoti, paginazione, archivi, importazione atomica, query e sicurezza. |
| `wallet/tests/test_improvements.py` | CSV v2 su archivio vuoto, giroconti con una/due gambe, duplicati e conflitti, rollback, centesimi, saldi SQL, ordinamento, paginazione e import a blocchi. |
| `wallet/tests/test_ui_workflows.py` | Otto casi per scelta Necessaria/Extra, vincoli e conservazione in modifica/CSV/backup, compatibilità CSV v2 precedente, residuo su tutti i conti e riepilogo per sottocategoria. |
| `wallet/tests/test_budget_allocations.py` | Undici casi per Nessuno, budget per sottocategoria, somma senza duplicazioni, mesi, importi invalidi, rollback, backup e tassonomia. |

`TestCase` e il test runner Django preparano un database di prova e isolano le modifiche dei test. Le fixture Python creano conti e movimenti fittizi; non occorre svuotare `wallet.sqlite3`. I test continuano a servire anche quando usi l'app con i dati reali: controllano il codice a ogni cambiamento, non la plausibilità delle tue spese personali.

Comandi mirati, oltre alla suite completa già indicata:

```bash
python manage.py test wallet.tests.test_application
python manage.py test wallet.tests.test_regressions
python manage.py test wallet.tests.test_improvements
python manage.py test wallet.tests.test_ui_workflows
python manage.py test wallet.tests.test_budget_allocations
python manage.py test wallet.tests.test_application.ApplicationTests.test_multi_account_perimeter_counts_only_boundary_transfers
```

Un test fallito indica quale aspettativa non è stata rispettata. Leggi il nome del test, i valori attesi/ottenuti e la traccia dell'errore. Se cambi deliberatamente una regola, aggiorna la specifica e il relativo test; non rimuovere un controllo solo per ottenere un risultato verde.

### 22.2 Perché esistono anche i test browser

I test Django verificano molte risposte e calcoli, ma non disegnano realmente i grafici e non eseguono tutta l'interazione JavaScript. Playwright apre Chromium e simula azioni reali: accesso, pulsanti, form, filtri, selezioni e download.

`scripts/browser_smoke.py` verifica filtri automatici e chiusura durante una richiesta in corso, schede colorate, salvataggio e modifica Necessaria/Extra, conferma e annullamento dell’uscita, struttura Account, residuo del budget, riepilogo per sottocategoria e valori effettivi del tooltip. Controlla inoltre Nessuno e Tutti, Invio sulle date custom, tutte le modalità degli istogrammi, apertura/somma/salvataggio dei budget per sottocategoria e ritorno al limite unico. Verifica anche il totale della categoria prima del salvataggio, i totali del mese, zero/vuoti/importi invalidi, il tooltip reale del saldo con la linea verticale allineata al giorno, la sua scomparsa all’uscita, le barre delle sottocategorie nei diversi stati e la rimozione dei suffissi dai nomi delle categorie. Verifica anche esportazione, eliminazione e reimportazione di un giroconto attraverso la nuova anteprima CSV, oltre a risposte HTTP errate, errori JavaScript, presenza degli SVG Plotly, navigazione mobile e larghezza della pagina a 1440, 390 e 360 px. Gli screenshot sono acquisizioni utili per l'ispezione; non costituiscono un confronto automatico pixel per pixel con un'immagine di riferimento.

Lo script lavora su una copia di test perché crea e modifica operazioni attraverso l'interfaccia. Con `--start-server` richiede un percorso SQLite separato e rifiuta connessioni PostgreSQL impostate nell'ambiente. La procedura operativa è nella sezione 9.

### 22.3 Quale verifica serve per ciascun cambiamento

| Cambiamento | Verifica utile |
| --- | --- |
| Regole di saldo o trasferimento | Test contabili con conti singoli, più conti e consolidato. |
| Filtri | Coerenza tra riepilogo, righe, grafici ed export. |
| Importazione o backup | File valido, righe invalide, duplicati e rollback. |
| Modello | Migrazione, vincoli e compatibilità dei record esistenti. |
| CSS o JavaScript | Browser e controllo visivo alle larghezze interessate. |
| Configurazione produzione | `check --deploy`, asset raccolti e prova nell'ambiente reale. |
| Documentazione | Coerenza con codice, comandi, collegamenti e file consegnati. |

La pipeline `.github/workflows/ci.yml` automatizza test applicativi su PostgreSQL e test browser su SQLite. La presenza del file definisce cosa verrà eseguito su GitHub; gli esiti della revisione già svolta sono riportati separatamente in `TECHNICAL_REVIEW.md`.

### 22.5 Benchmark riproducibile

```bash
python scripts/benchmark_wallet.py --sizes 10000 50000 --output risultato.json
```

Lo script crea automaticamente un database SQLite temporaneo nuovo per ciascuna dimensione, esclude connessioni PostgreSQL dell'ambiente e lo elimina al termine. I dati sono fittizi: tre conti, tre tipi contabili, tre anni di operazioni e un giroconto ogni dieci movimenti. Non modifica `wallet.sqlite3`. Le migrazioni e la generazione dei dati non sono incluse nei tempi.

Misure del 29 settembre 2026, Python 3.12.14 e Django 5.2.17, stesso ambiente prima/dopo. `tracemalloc` era attivo: i tempi includono il suo costo e non rappresentano la latenza HTTP di produzione. Una misura per caso, senza garanzie sul tempo massimo. Il picco è quello delle allocazioni Python, non la memoria totale del processo o del motore SQL.

| Dati | Calcolo | Prima (s) | Dopo (s) | Picco Python prima → dopo (MiB) |
| --- | --- | ---: | ---: | ---: |
| 10.000 movimenti + 1.000 giroconti | Registro, pagina da 25 righe e totali | 8,86 | 0,35 | 36,88 → 0,69 |
| 10.000 movimenti + 1.000 giroconti | Dashboard, aggregazioni e saldi | 7,66 | 0,45 | 31,85 → 0,72 |
| 50.000 movimenti + 5.000 giroconti | Registro, pagina da 25 righe e totali | 31,45 | 1,37 | 184,87 → 0,68 |
| 50.000 movimenti + 5.000 giroconti | Dashboard, aggregazioni e saldi | 30,05 | 1,81 | 152,28 → 0,72 |

Conteggi, entrate, uscite e saldi coincidono prima/dopo. I risultati completi, inclusi numero di query e valori di controllo, sono in `docs/benchmark_sqlite.json`. La riduzione riguarda soprattutto dati trasferiti e oggetti Python: SQL continua a elaborare lo storico. Queste misure non certificano PostgreSQL, carico concorrente o milioni di righe; per quei casi servono misure nell'ambiente reale. L'import resta sincrono con limite di 10.000 righe; non sono introdotte code o lavorazioni in background.

## 23. Come modificare il progetto senza perdere l'orientamento

### 23.1 Mappa delle modifiche più comuni

I percorsi della tabella sono relativi alla radice che contiene `manage.py`.

| Obiettivo | File principali da leggere o modificare | Collegamenti da controllare |
| --- | --- | --- |
| Cambiare colori, spaziature e stile | `wallet/static/wallet/app.css` | Token condivisi, media query e resa dei grafici. |
| Cambiare palette dei tipi nei grafici | `wallet/services/colors.py` | `TYPE_COLORS`, legenda e uso dei colori nei movimenti/budget. |
| Cambiare il contenuto della Dashboard | `wallet/views/dashboard.py`, `wallet/services/analytics.py`, `wallet/templates/wallet/home.html` | Riconciliazione fra saldo iniziale, netto e saldo finale. |
| Modificare un filtro | `wallet/services/filters.py`, `wallet/templates/wallet/components/filters.html`, `wallet/static/wallet/js/filters.js` | Dashboard, Overview, Movimenti ed export. |
| Cambiare una formula di saldo | `wallet/services/ledger.py`, `movement_query.py`, `amounts.py` | Conti singoli, consolidato, date e saldi dopo operazione. |
| Aggiungere un campo al movimento | `wallet/models.py`, `wallet/forms.py`, `wallet/templates/wallet/transaction_form.html` | Migrazione, importazione, export e compatibilità backup. |
| Modificare la tabella o la lista | `wallet/services/movements.py`, `movement_query.py`, `wallet/views/movements.py`, `wallet/templates/wallet/transactions.html` | Ordinamento, paginazione e due gambe dei giroconti. |
| Aggiungere un grafico | `wallet/services/analytics.py`, template interessato, `wallet/static/wallet/js/charts.js` | Filtri, valori zero, tooltip e dimensioni mobili. |
| Cambiare il budget | `wallet/models.py`, `wallet/services/budget.py`, `wallet/templates/wallet/budget.html`, `components/budget_category.html`, `wallet/static/wallet/js/budget.js` | Somma delle sottocategorie, modalità alternative, mese, storico, zero/vuoti, backup e trasferimenti esclusi. |
| Supportare una colonna d'importazione | `wallet/services/importing.py`, `wallet/views/data_management.py`, template `import_*.html` | Mappatura, revisione, conferma e messaggi d'errore. |
| Modificare tassonomia o icone | `wallet/services/taxonomy.py`, `wallet/icon_config.py`, pagina Categorie | Storico e sottocategorie già utilizzate. |
| Cambiare accesso e autorizzazioni | `wallet/access.py`, `wallet/middleware.py`, `wallet/forms.py` | Accesso iniziale e sessioni già aperte. |
| Aggiungere una pagina | Nuova vista, `wallet_project/urls.py`, template e navigazione | Autenticazione, stati vuoti, desktop/mobile. |

Per rinominare una categoria, cambiare un limite o aggiungere un conto non occorre modificare il codice: sono operazioni già esposte dall'interfaccia. Il codice va modificato quando cambia il comportamento dell'applicazione.

### 23.2 Le migrazioni non sono i dati

Una migrazione descrive un cambiamento dello **schema**: per esempio aggiungere `account_type` alla tabella dei conti. Il database contiene invece i record effettivi. `makemigrations` confronta modelli e cronologia delle migrazioni e genera un file Python; `migrate` applica le operazioni ancora mancanti al database selezionato.

Nella revisione iniziale, `0007_account_type` dipende da `0006` e aggiunge un campo con valore predefinito. `0008_subcategory_budget` dipende da `0007` e crea il nuovo modello dei limiti dettagliati; non contiene operazioni di riscrittura dei budget precedenti. Le migrazioni precedenti restano presenti per permettere a Django di ricostruire sia un database nuovo sia l'aggiornamento di uno esistente.

Dopo una modifica a un modello, un normale percorso di sviluppo è:

```bash
python manage.py makemigrations wallet
python manage.py migrate
python manage.py test
```

Eseguilo durante lo sviluppo su una copia appropriata e controlla il contenuto della nuova migrazione prima di applicarlo ai dati personali. Per verificare soltanto se manca una migrazione usa invece `makemigrations --check --dry-run`: non genera file.

### 23.3 Cosa contiene la cartella e cosa viene generato

| Elemento | Ruolo |
| --- | --- |
| Codice, template, CSS, JavaScript, migrazioni | Sorgenti da conservare e versionare. |
| `wallet.sqlite3` | Dati personali originali, mantenuti nell'archivio. |
| `demo/wallet_demo.sqlite3` | Dati fittizi separati per provare l'app. |
| `preview/` | Screenshot dimostrativi; non vengono caricati dall'applicazione. |
| `.venv/` | Ambiente Python creato localmente durante l'installazione; non è incluso nello ZIP. |
| `staticfiles/` | Asset raccolti e generati dalla build di produzione. |
| `__pycache__/` | Cache Python rigenerabile. |
| `test-results/` | Screenshot e log prodotti dai test browser. |
| `.env.example` | Elenco esemplificativo delle variabili, privo di segreti reali. |
| `.gitignore` | Esclusioni per il controllo di versione, inclusi database e file generati. |
| `.dockerignore` | Esclusioni dalla build Docker, inclusi database SQLite e demo. |

L'archivio completo precedente includeva i database originali e demo. **Lo ZIP di questo aggiornamento contiene soltanto file nuovi o modificati**, con percorsi relativi alla cartella di `manage.py`; esclude database, demo, cache e dipendenze. Vedi `AGGIORNAMENTO.md` per applicarlo. Questo aggiornamento CSV/prestazioni non modifica i modelli e non aggiunge migrazioni.

### 23.4 In quale ordine leggere il codice

Per una prima lettura tecnica: parti da `models.py` per capire i dati, poi leggi `ledger.py` per i saldi e `filters.py` per le selezioni. Segui quindi una sola pagina, per esempio `dashboard()` fino al suo template `home.html` e a `charts.js`. Solo dopo passa a Movimenti, importazione, budget e backup.

Questo percorso permette di collegare ogni funzione a una domanda concreta: «quali operazioni leggo?», «quale saldo devo calcolare?», «quali dati passo alla pagina?». I test sono esempi aggiuntivi: mostrano gli input e il risultato atteso delle regole più delicate.

## 24. Glossario e punti da ricordare

| Termine | Significato nel Wallet |
| --- | --- |
| Backend | Codice Python/Django che legge dati, valida e prepara le risposte. |
| Frontend | HTML, CSS e JavaScript eseguiti o mostrati nel browser. |
| ORM | Interfaccia Django per lavorare con tabelle e query usando modelli Python. |
| Modello | Definizione di un'entità persistita, per esempio un conto. |
| Vista | Funzione o classe che gestisce una richiesta web. |
| Template | File usato per comporre l'HTML della risposta. |
| Servizio | Funzione che raccoglie una regola o un'elaborazione riutilizzabile. |
| Registro / ledger | Sequenza ordinata delle variazioni di saldo. |
| Perimetro | Insieme dei conti selezionati per l'analisi. |
| Consolidato | Risultato complessivo dei conti considerati insieme. |
| Migrazione | Istruzione versionata per aggiornare la struttura del database. |
| Fixture | Dati serializzati che Django può caricare, come il backup JSON Wallet. |
| Transazione atomica | Gruppo di scritture confermate insieme o annullate insieme. |
| Query N+1 | Una query iniziale seguita da un'altra per ogni riga; può rendere lenta una pagina. |
| `select_related` | Carica relazioni singole insieme agli oggetti letti, evitando richieste ripetute. |
| `prefetch_related` | Precarica collezioni correlate, come le sottocategorie di più categorie. |
| CSRF | Protezione delle richieste di modifica contro invii non autorizzati da altri siti. |
| Asset statici | File dell'interfaccia come CSS, JavaScript e icone. |
| WSGI / Gunicorn | Interfaccia di esecuzione dell'applicazione Python e server usato per servirla in produzione. |

Il riferimento finanziario è sempre costituito da saldi iniziali e operazioni persistite. Schede, saldi dopo operazione e grafici sono calcoli derivati. Un filtro decide cosa osservare, un'archiviazione mantiene lo storico e un backup JSON consente di trasferire l'intero insieme dei dati finanziari. Queste distinzioni aiutano a usare il Wallet e a modificarne il codice mantenendo risultati coerenti.


## 25. Caricare il progetto su GitHub

### 25.1 Quale cartella usare

Usa **il progetto completo aggiornato**, cioè la cartella che contiene `manage.py`, `README.md`, `requirements.txt`, `wallet/` e `wallet_project/`. Applica prima tutti gli ZIP di aggiornamento, compreso l’ultimo: contengono soltanto una parte dei file e non sono repository completi.

Il file `.gitignore` esclude database SQLite, credenziali nei file `.env` e `.env.*`, backup Wallet, ZIP, ambiente virtuale, cache, caricamenti e risultati dei test. Il modello `.env.example` resta incluso perché contiene soltanto esempi. Prima di pubblicare, controlla l’elenco dei file da caricare: eventuali estratti conto o documenti aggiunti con altri nomi vanno tenuti fuori dal repository. Le regole non rimuovono file già registrati in una precedente cronologia Git.

Su GitHub non troverai né il database personale né quello demo. Dopo un clone, la procedura della sezione 2 prepara un Wallet nuovo; `prova_demo.py` ricrea invece i dati dimostrativi. Il codice su GitHub non sostituisce il backup JSON dei tuoi dati.

### 25.2 Procedura con GitHub Desktop

Per il primo caricamento puoi usare [GitHub Desktop](https://desktop.github.com/) e accedere al tuo account.

1. Scegli **File → New repository**, nome `wallet`, e una cartella di destinazione. Verrà creata al suo interno una nuova cartella `wallet`. Lascia disattivato il README iniziale e scegli None per Git ignore e License: copia le impostazioni già presenti nel progetto.
2. Copia nella nuova cartella **il contenuto del progetto completo aggiornato**. `manage.py` deve trovarsi direttamente nella cartella del repository. Includi anche `.gitignore` e `.github/`.
3. In **Changes**, controlla i file, scrivi un riepilogo come `Prima versione Wallet` e premi **Commit to main**; se il ramo ha un nome diverso, il pulsante riporta quel nome.
4. Premi **Publish repository**. Per il tuo account personale scegli None nel campo Organization, se presente. Mantieni **Keep this code private** per un repository privato e conferma.
5. Usa **Repository → View on GitHub** per aprire il risultato. Per gli aggiornamenti successivi: modifica gli stessi file, crea un commit e premi **Push origin**.

Riferimenti ufficiali: [creazione del repository con Desktop](https://docs.github.com/en/desktop/overview/creating-your-first-repository-using-github-desktop) e [pubblicazione su GitHub](https://docs.github.com/en/desktop/adding-and-cloning-repositories/adding-an-existing-project-to-github-using-github-desktop).

### 25.3 Alternativa con Git da terminale

Per un progetto non ancora gestito da Git, installa Git e crea su GitHub un repository vuoto chiamato `wallet`, senza generare README, gitignore o licenza. Apri il terminale nella cartella del progetto completo e imposta, se necessario, nome ed email per i commit con `git config user.name` e `git config user.email` dopo `git init`.

```bash
git init -b main
git add .
git status
git commit -m "Prima versione Wallet"
git remote add origin https://github.com/TUO_USERNAME/wallet.git
git push -u origin main
```

Sostituisci `TUO_USERNAME` con il tuo nome utente GitHub e configura l’autenticazione Git prima del push. Se la cartella è già un repository, usa la configurazione esistente: non aggiungere una seconda origine o un nuovo repository alla cieca. Le istruzioni complete e i metodi di autenticazione sono nella [guida ufficiale per il codice locale](https://docs.github.com/en/migrations/importing-source-code/using-the-command-line-to-import-source-code/adding-locally-hosted-code-to-github).

### 25.4 Dopo il caricamento

Il workflow presente in `.github/workflows/ci.yml`, se GitHub Actions è abilitato, esegue i test applicativi su PostgreSQL e il percorso browser su dati fittizi. L’esito remoto si controlla nella scheda Actions: le verifiche locali non garantiscono automaticamente l’esito del servizio remoto.

La pubblicazione del repository conserva il codice. Per usare Wallet tramite un indirizzo online serve anche il deploy Django, descritto nella sezione 10. I dati personali e le variabili segrete si configurano nell’ambiente di esecuzione.
