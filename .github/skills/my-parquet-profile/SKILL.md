---
name: my-parquet-profile
description: Profila un file parquet o CSV in sola lettura con DuckDB (tipi, null, valori distinti, min/max, anteprima, valori frequenti, indizi su date e importi salvati come testo) e permette di provare una SELECT sulla vista `dataset`. Da usare quando serve capire un dataset sconosciuto, per esempio per scrivere una mappa semantica o validare una query.
---
# My Parquet Profile

Script: [profile_parquet.py](./profile_parquet.py). Sola lettura, stampa Markdown. Il file è esposto come vista `dataset` (stesso nome usato dal server NETA Analytics).

## Requisiti

Un interprete Python con `duckdb`. Nel workspace NETA ce n'è uno nella `.venv` di `MCP_NetaAnalytics`
(`MCP_NetaAnalytics\.venv\Scripts\python.exe`). Se non esiste nessun interprete con `duckdb`, chiedere all'utente prima di installare qualcosa.

## Uso

```powershell
# profilo completo (prime 10 righe, statistiche su max 1.000.000 righe)
python profile_parquet.py "<file.parquet>" --rows 10

# con dati personali: nascondi le colonne indicate (anteprima, min/max e valori frequenti diventano ***)
python profile_parquet.py "<file.parquet>" --mask-columns NOME,COGNOME,CODICEFISCALE

# nessun valore di testo nell'output
python profile_parquet.py "<file.parquet>" --no-samples

# prova una SELECT/WITH sulla vista dataset (un solo statement, prime N righe)
python profile_parquet.py "<file.parquet>" --query "SELECT ... FROM dataset ..." --rows 10

# ipotesi sulla granularità: chiave candidata e livelli di ripetizione (usa fino a 3.000.000 di righe: su file grandi richiede diversi minuti)
python profile_parquet.py "<file.parquet>" --structure

# cosa è costante o variabile dentro i gruppi definiti da colonne scelte con l'utente (es. un documento)
python profile_parquet.py "<file.parquet>" --level "COL_A,COL_B,COL_C"

# esegue la SQL di ogni few-shot (PromptExamples/<DOMINIO>.txt) sul parquet e mostra errori e copertura
python profile_parquet.py "<file.parquet>" --check-examples "<PromptExamples/DOMINIO.txt>"
```

## Come leggere l'output

- **Hint**: `date in text` e `decimal in text (amount?)` indicano colonne di testo che contengono date ISO o numeri (servono `TRY_CAST` nelle query e una dichiarazione di formato); `numeric code (leading zeros)` indica un codice da non formattare come numero; `has 0001-01-01 sentinel` indica una data "nessun valore".
- **Distinct** è approssimato. **Null %** conta solo i NULL: le stringhe vuote compaiono nei valori frequenti come `''`.
- Gli indizi sono euristiche: vanno confermati con l'utente.
- `--structure` e `--level` stampano solo nomi di colonna e conteggi (nessun valore). La chiave candidata è trovata in modo greedy e i livelli sono prefissi di quella chiave: sono ipotesi, spesso non coincidono con le entità di business (es. può scegliere un codice quasi univoco invece dell'identificativo del documento). Usa `--level` con le colonne che l'utente conferma come identificativo di un'entità.
- Con "Numeric columns repeated on every row of the group" gli importi si ripetono su ogni riga del gruppo: sommarli per riga li moltiplica (serve una CTE che deduplica a quel livello). Se compare `WARNING: only N of M rows analysed` i gruppi sono spezzati: alza `--max-rows`.
- `--check-examples` legge le coppie `Input:` / `Output:` (JSON su una riga), esegue la SQL (solo conteggio righe) e segnala: SQL che fallisce, colonne di `column_formats` o del grafico che la SQL non produce, e la copertura (colonne mai usate, tipi di grafico, `table_style`, uso di `CURRENT_DATE`). Le date relative sono valutate rispetto a oggi.

## Regole

- L'output contiene dati reali: con colonne anagrafiche (nomi, codici fiscali, indirizzi, e-mail, IBAN) usare sempre `--mask-columns` o `--no-samples`, e non riportare quei valori in file o documenti.
- `--query` accetta solo `SELECT`/`WITH`.