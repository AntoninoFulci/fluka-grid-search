Ho bisogno di progettare un framework Python per eseguire grid search di simulazioni FLUKA.

L’obiettivo è avere un sistema generale e modulare che:

* legga un file di configurazione
* generi tutte le combinazioni di parametri
* lanci simulazioni FLUKA
* gestisca esecuzioni parallele
* analizzi automaticamente gli output binari FORTRAN prodotti da FLUKA
* sia facilmente estendibile in futuro per esecuzione su farm/HPC cluster

Per ora voglio concentrarmi SOLO sull’esecuzione locale.

# Requisiti principali

## Linguaggio

Tutto deve essere scritto in Python.

## Input principale

Il programma deve ricevere un file di configurazione.

Esempio:

```bash
python run_grid.py config.yaml
```

## Nel file di configurazione devono essere specificati:

* file input FLUKA (`example.inp`)
* cartella output
* parametri da variare nella grid search

  * il nome cambia in genere da file a file, quindi va verificato che i parametri definiti nel config esistano realmente nel file input
* numero massimo di processi paralleli
* eventuale numero di job contemporanei per combinazione
* eseguibili di analisi dei file binari
* mapping tra estensione file binario e tool da usare

## File di input FLUKA di esempio

Nella cartella del progetto includerò anche un file `.inp` reale di FLUKA da usare come esempio/reference.

Questo file deve essere utilizzato per:

* capire la struttura tipica dell’input FLUKA
* capire come identificare e sostituire i parametri della grid search
* progettare il parser/template system
* capire eventuali criticità di formatting dell’input FLUKA

Quindi considera che avrai accesso a un esempio concreto di input FLUKA durante la progettazione del framework.

## Esecuzione FLUKA

Il comando da usare è:

```bash
/pathtofluka/bin/rfluka -M 1 -e ./myfluka example.inp
```

Vincoli:

* `-M` deve essere sempre fissato a `1`
* l’eseguibile `rfluka` deve essere trovato automaticamente tramite:

```bash
fluka-config --bin
```

che restituisce la cartella contenente `rfluka`.

Nel file di config voglio comunque poter overrideare il path manualmente.

Voglio anche poter specificare l’eseguibile custom da passare a `-e`.

## Parametri della grid search

Voglio poter definire nel file di config parametri con liste di valori.

Esempio:

```yaml
parameters:
  beame: [0, 1, 2]
  mat: [GALLIUM, TUNGSTEN]
```

Il framework deve generare automaticamente tutte le combinazioni.

Per ogni combinazione voglio:

* una working directory separata
* file input modificato
* output separati
* nuovo seed nel file input

  * vedi `/Users/tonyf/Work/FlukaQueueSub/scripts`

## Gestione seed

Ho già implementato una logica per cambiare seed FLUKA qui:

```text
/Users/tonyf/Work/FlukaQueueSub
```

Il nuovo framework dovrebbe essere compatibile con questa logica o riutilizzarla.

# Sistema di esecuzione locale

Sul mio Mac installerò `task-spooler` (`ts`).

Vorrei quindi che il framework locale utilizzi `task-spooler` come backend di scheduling invece di implementare un scheduler Python custom.

Obiettivi:

* usare `ts` per limitare automaticamente il numero massimo di job paralleli
* mettere in queue le simulazioni FLUKA
* monitorare stato e completion dei job
* raccogliere exit status
* mantenere il framework semplice e robusto

Vorrei una proposta architetturale basata su:

* Python come orchestratore
* `subprocess`
* `task-spooler` come execution backend locale

In futuro il backend dovrebbe essere sostituibile con:

* SLURM
* HTCondor
* backend custom HPC

Quindi idealmente vorrei un’astrazione tipo:

```text
ExecutionBackend
 ├── TaskSpoolerBackend
 ├── SlurmBackend
 └── CondorBackend
```

# Parte critica: analisi output FLUKA

Quando FLUKA termina produce file binari FORTRAN con estensioni:

```text
.21
.22
.23
...
.99
```

Questi file devono essere processati usando utility presenti nella cartella `bin` di FLUKA.

Problema importante:

* NON è possibile capire automaticamente quale utility usare leggendo il file binario
* bisogna specificarlo manualmente nel config file

Quindi nel config voglio qualcosa tipo:

```yaml
postprocessing:
  ".21":
    executable: usbsuw
  ".22":
    executable: usbrea
```

## Modalità di utilizzo dei tool FLUKA

Questi tool funzionano in maniera interattiva.

Tipicamente:

* chiedono il path dei file da analizzare
* si inserisce un file per riga
* un invio vuoto termina la lista e avvia il processing

Esempio concettuale:

```text
/path/file1
/path/file2
/path/file3

```

(doppio invio finale)

Quindi il framework deve essere in grado di:

* lanciare questi eseguibili
* inviare input via stdin
* raccogliere output/stdout/stderr
* salvare eventuali file generati

Vorrei una proposta robusta per implementare questa parte.

# Obiettivo architetturale

Il progetto deve essere:

* modulare
* facilmente estendibile
* backend-agnostic per l’esecuzione job
* facilmente migrabile verso cluster/HPC

Per ora però implementazione SOLO locale con `task-spooler`.

# Vorrei da te

1. proposta architetturale completa
2. struttura delle classi/moduli
3. formato config consigliato
4. integrazione robusta con `task-spooler`
5. strategia di gestione run/output
6. strategia di post-processing
7. possibili problemi/concurrency pitfalls
8. esempio minimo funzionante
9. suggerimenti su librerie Python utili
10. roadmap di implementazione
