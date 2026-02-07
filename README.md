# Path Optimization 

Questo progetto implementa un sistema di ottimizzazione per la pianificazione di percorsi per droni all'interno di edifici tridimensionali. L'obiettivo è visitare una serie di punti di interesse (nodi) minimizzando i costi, tenendo conto di vincoli energetici e temporali.

## Descrizione del Progetto

Il software calcola il percorso ottimale per visitare un insieme predefinito di punti in uno spazio 3D. Le funzionalità principali includono:
- Caricamento delle coordinate dei nodi da file CSV.
- Identificazione automatica della posizione ottimale per la base di partenza/ricarica (calcolata in base al centroide dei nodi).
- Generazione del grafo dei collegamenti possibili tra nodi.
- Calcolo dei costi di attraversamento basati su:
  - **Distanza Euclidea**
  - **Energia**: Costi differenziati per movimenti orizzontali, di ascesa e di discesa.
  - **Tempo**: Velocità differenziate per le tre tipologie di movimento.
- Risoluzione del problema di ottimizzazione (Mixed Integer Programming via `mip`).
- Visualizzazione grafica dei percorsi risultanti.

## Struttura del Repository

### Codice Sorgente
- **`main.py`**: Lo script principale. Esegue l'intera pipeline: caricamento dati, preprocessing, ottimizzazione e visualizzazione.
- **`Big_project.ipynb`** / **`Big_project copy.ipynb`**: Notebook Jupyter contenenti l'analisi esplorativa, la logica di modellazione e test interattivi.

### Dati di Input
- **`Edificio1.csv`**, **`Edificio2.csv`**: File contenenti le coordinate (x, y, z) dei punti da visitare nell'edificio.

### File Generati / Output
- **`building.csv`**: Dataset preprocessato che include i nodi originali più la posizione calcolata per la base.
- **`pairs.csv`**: File contenente tutte le possibili connessioni (archi) tra le coppie di nodi, con relativi costi (distanza, dx, dy, dz).
- **`solution.txt`**: File contenente i dettagli della soluzione ottima trovata.
- **`model.lp`**: Il modello matematico generato in formato Linear Programming.
- **`model.tex`**: Rappresentazione LaTeX del modello matematico.
- **`optimization_results/`**: Cartella contenente i log e i risultati delle ottimizzazioni di test (JSON, TXT).

## Requisiti

Il progetto richiede Python e le seguenti librerie:
- `pandas`
- `numpy`
- `matplotlib`
- `networkx`
- `mip` (Python-MIP per l'ottimizzazione lineare intera mista)

Puoi installare le dipendenze con:
```bash
pip install pandas numpy matplotlib networkx mip
```

## Come Eseguire

Per avviare l'ottimizzazione per uno specifico edificio, eseguire lo script `main.py` passando il nome del file CSV come argomento.

Esempio:
```bash
python main.py Edificio2.csv
```

Se non viene fornito alcun argomento, lo script potrebbe cercare di usare un file di default o terminare (verificare la logica in `main.py`).

## Parametri di Configurazione

I parametri di simulazione (velocità, costi energetici, capacità batteria) sono definiti all'inizio di `main.py` e possono essere adattati in base alle esigenze:

- `ASCENDING_SPEED`, `DESCENDING_SPEED`, `HORIZONTAL_SPEED`
- `ASCENDING_ENERGY`, `DESCENDING_ENERGY`, `HORIZONTAL_ENERGY`
- `BATTERY_CAPACITY`
- `MAX_SECONDS` (Tempo massimo della missione)

## Autore

De Matteo Michele
Crippa Davis
Compagnoni Andrea
