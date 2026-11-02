import json
import sys

OUT_DIR = sys.argv[1]
P = "parquet_scan('{parquet_path}')"

RATE = (
    "WITH rate AS (SELECT CODICESEZIONALE, ANNODOCUMENTO, NUMERODOCUMENTO, PROGRESSIVORATA, "
    "ANY_VALUE(CODICESOGGETTO) AS CODICESOGGETTO, "
    "ANY_VALUE(COALESCE(RAGIONESOCIALE, TRIM(COALESCE(COGNOME, '') || ' ' || COALESCE(NOME, '')))) AS cliente, "
    "ANY_VALUE(DESCRIZIONETIPOSOGGETTO) AS tipo_cliente, ANY_VALUE(TIPODOCFISICOID) AS tipo_doc, "
    "ANY_VALUE(STATOMOROSITA) AS stato_morosita, STRING_AGG(DISTINCT STATOFORNITURA, ', ') AS stato_fornitura, "
    "BOOL_OR(STATOFORNITURA = 'ATT') AS fornitura_attiva, MIN(DESCRIZIONETIPOSERVIZIO) AS servizio, "
    "MIN(DESCRIZIONEUSOMERCEOLOGICO) AS uso, ANY_VALUE(DESCRIZIONECANALE) AS canale, "
    "MAX(TRY_CAST(DATAEMISSIONE AS DATE)) AS data_emissione, MAX(TRY_CAST(DATASCADENZA AS DATE)) AS data_scadenza, "
    "MAX(TRY_CAST(DATAPAGAMENTO AS DATE)) AS data_pagamento, "
    "MAX(TRY_CAST(DATAULTIMOSOLLECITO AS DATE)) AS data_ultimo_sollecito, "
    "MAX(TRY_CAST(NUMEROSOLLECITI AS INTEGER)) AS solleciti, MAX(TRY_CAST(IMPORTOFATTURATO AS DOUBLE)) AS fatturato, "
    "MAX(TRY_CAST(IMPORTOPAGATO AS DOUBLE)) AS pagato, "
    "MAX(TRY_CAST(IMPORTOFATTURATO AS DOUBLE)) - MAX(TRY_CAST(IMPORTOPAGATO AS DOUBLE)) AS residuo "
    f"FROM {P} GROUP BY CODICESEZIONALE, ANNODOCUMENTO, NUMERODOCUMENTO, PROGRESSIVORATA)"
)

DOC = (
    "WITH documenti AS (SELECT CODICESEZIONALE, ANNODOCUMENTO, NUMERODOCUMENTO, "
    "ANY_VALUE(CODICESOGGETTO) AS CODICESOGGETTO, "
    "ANY_VALUE(COALESCE(RAGIONESOCIALE, TRIM(COALESCE(COGNOME, '') || ' ' || COALESCE(NOME, '')))) AS cliente, "
    "ANY_VALUE(TIPODOCFISICOID) AS tipo_doc, MIN(DESCRIZIONETIPOSERVIZIO) AS servizio, "
    "MAX(TRY_CAST(DATAEMISSIONE AS DATE)) AS data_emissione, "
    "MAX(TRY_CAST(IMPORTOTOTALEFATTURATO AS DOUBLE)) AS importo_documento, "
    "COUNT(DISTINCT PROGRESSIVORATA) AS numero_rate "
    f"FROM {P} GROUP BY CODICESEZIONALE, ANNODOCUMENTO, NUMERODOCUMENTO)"
)

# Same text as DOC but chained after another CTE.
DOC_CHAINED = DOC.replace("WITH documenti AS", ", documenti AS", 1)
RATE_CHAINED = RATE.replace("WITH rate AS", ", rate AS", 1)

SEMANTIC = f"""- cliente -> CODICESOGGETTO (per contare i clienti usa COUNT(DISTINCT CODICESOGGETTO))
- utente -> CODICESOGGETTO
- intestatario -> CODICESOGGETTO
- nome cliente -> COALESCE(RAGIONESOCIALE, TRIM(COALESCE(COGNOME, '') || ' ' || COALESCE(NOME, '')))
- ragione sociale -> RAGIONESOCIALE (valorizzata solo per aziende, per persone fisiche usa COGNOME e NOME)
- codice fiscale -> CODICEFISCALE
- partita iva -> PARTITAIVA
- tipo cliente -> DESCRIZIONETIPOSOGGETTO (PERSONA FISICA, SOCIETÀ, CONDOMINIO, PUBBLICA AMMINISTRAZIONE, ...)
- documento -> CODICESEZIONALE + ANNODOCUMENTO + NUMERODOCUMENTO
- tipo documento -> TIPODOCFISICOID (nelle CTE rate e documenti: tipo_doc)
- bolletta -> tipo_doc = 'B' (applica il filtro solo se la domanda distingue le bollette da fatture o note di credito, altrimenti considera tutti i documenti)
- fattura -> tipo_doc = 'F' (stessa regola)
- nota di credito -> tipo_doc = 'N' (stessa regola)
- data emissione -> DATAEMISSIONE (nelle CTE: data_emissione)
- data fattura -> DATAEMISSIONE
- anno documento -> ANNODOCUMENTO
- rata -> PROGRESSIVORATA ('0' = documento non rateizzato)
- rateizzato -> PROGRESSIVORATA <> '0'
- bolletta multirata -> nella CTE documenti: numero_rate > 1
- bolletta a rata unica -> nella CTE documenti: numero_rate = 1
- importo bolletta -> importo_documento nella CTE documenti
- fatturato -> IMPORTOFATTURATO (nella CTE rate: fatturato, per rata)
- importo rata -> IMPORTOFATTURATO
- pagato -> IMPORTOPAGATO (nella CTE rate: pagato)
- incassato -> IMPORTOPAGATO (nella CTE rate: pagato, attribuito alla data_pagamento della rata)
- incassato nel periodo -> pagato filtrato su data_pagamento (mai su data_emissione o data_scadenza)
- totale documento -> IMPORTOTOTALEFATTURATO
- non pagato -> IMPORTOFATTURATO - IMPORTOPAGATO, solo dove il risultato e > 0 (nella CTE rate: residuo > 0)
- insoluto -> IMPORTOFATTURATO - IMPORTOPAGATO, solo dove il risultato e > 0
- residuo -> IMPORTOFATTURATO - IMPORTOPAGATO, solo dove il risultato e > 0
- scadenza -> DATASCADENZA (nelle CTE: data_scadenza)
- scaduto -> non pagato con DATASCADENZA < CURRENT_DATE (nella CTE rate: residuo > 0 AND data_scadenza < CURRENT_DATE)
- morosita (in senso generico) -> scaduto
- aging -> DATE_DIFF('day', data_scadenza, CURRENT_DATE) sulla CTE rate
- giorni di ritardo -> DATE_DIFF('day', data_scadenza, CURRENT_DATE) sulla CTE rate
- stato morosita -> STATOMOROSITA (nella CTE rate: stato_morosita; situazione di insolvenza della rata e stato delle azioni di recupero; codici es. NM, S1, S2, SOSP)
- data inizio morosita -> DATAINIZIOSTATOMOROSITA ('0001-01-01T00:00:00' = nessuno stato di morosita, trattalo come NULL)
- solleciti -> NUMEROSOLLECITI (nella CTE rate: solleciti)
- sollecitato -> NUMEROSOLLECITI <> '0' (nella CTE rate: solleciti > 0)
- ultimo sollecito -> DATAULTIMOSOLLECITO (nella CTE rate: data_ultimo_sollecito)
- data pagamento -> DATAPAGAMENTO (NULL = rata non pagata; nella CTE rate: data_pagamento)
- data incasso -> DATAPAGAMENTO
- data registrazione pagamento -> DATARIFERIMENTO
- canale di pagamento -> DESCRIZIONECANALE (contiene solo codici, es. 'CANALE: 202'; non esiste una descrizione estesa)
- canale incasso -> DESCRIZIONECANALE
- fornitura -> CODICEFORNITURA
- servizio -> DESCRIZIONETIPOSERVIZIO (GAS METANO, ENERGIA ELETTRICA, COMMODITY VAS)
- commodity -> DESCRIZIONETIPOSERVIZIO
- stato fornitura -> STATOFORNITURA (stato contrattuale della fornitura all'emissione del documento: ATT = attiva, ATTC = attiva commercialmente, ICSO = in corso di sospensione, SOSP = sospesa, CFAT = cessata fatturata, CNFA = cessata da fatturare, CCOM = cessata commercialmente, ANN = annullata, DAT = da attivare, DATC = da attivare commercialmente)
- fornitura attiva -> STATOFORNITURA = 'ATT' (nella CTE rate: fornitura_attiva)
- uso -> DESCRIZIONEUSOMERCEOLOGICO
- uso merceologico -> DESCRIZIONEUSOMERCEOLOGICO
- categoria d'uso -> DESCRIZIONECATEGORIAUSO
- sezione -> DESCRIZIONESEZIONE

Regole del dominio:
- Tutte le colonne sono stringhe. Importi: TRY_CAST(colonna AS DOUBLE). Date: TRY_CAST(colonna AS DATE), formato yyyy-MM-ddTHH:mm:ss.
- Funzioni data DuckDB: DATE_DIFF('day', inizio, fine), DATE_TRUNC, EXTRACT, STRFTIME, CURRENT_DATE. NON usare julianday, julian, GETDATE, DATEDIFF a due argomenti.
- Ogni riga e documento x rata x fornitura: se un documento ha piu forniture, gli importi della rata sono ripetuti su ogni riga.
- REGOLA OBBLIGATORIA: per qualsiasi somma o conteggio su importi, rate, scaduto, insoluto o incassato inizia SEMPRE con questa CTE, copiata identica, e interroga la CTE rate invece del parquet. Non usare SELECT DISTINCT su sottoinsiemi di colonne per deduplicare.
  CTE rate: {RATE}
- Colonne della CTE rate: CODICESEZIONALE, ANNODOCUMENTO, NUMERODOCUMENTO, PROGRESSIVORATA, CODICESOGGETTO, cliente, tipo_cliente, tipo_doc, stato_morosita, stato_fornitura, fornitura_attiva, servizio, uso, canale, data_emissione, data_scadenza, data_pagamento, data_ultimo_sollecito, solleciti, fatturato, pagato, residuo.
- REGOLA OBBLIGATORIA: per domande su bollette o documenti (numero di bollette, bollette multirata o a rata unica, importo bolletta) inizia SEMPRE con questa CTE, copiata identica, e interroga la CTE documenti (una riga per documento). Non raggruppare per ANNODOCUMENTO o per cliente prima di avere la riga per documento.
  CTE documenti: {DOC}
- Colonne della CTE documenti: CODICESEZIONALE, ANNODOCUMENTO, NUMERODOCUMENTO, CODICESOGGETTO, cliente, tipo_doc, servizio, data_emissione, importo_documento, numero_rate.
- Se servono entrambe le CTE, concatenale copiandole identiche (WITH ... AS (...), nome AS (...)).
- Eccezione: i conteggi di soggetti o documenti che non coinvolgono importi, scaduto o incassato (es. percentuale di clienti con documenti rateizzati) possono interrogare direttamente il parquet con COUNT(DISTINCT ...).
- Per filtrare un cliente per NOME e COGNOME usa CODICESOGGETTO IN (SELECT CODICESOGGETTO FROM parquet_scan(...) WHERE NOME = '...' AND COGNOME = '...') senza modificare le CTE.
- Scaduto sulla CTE rate: residuo > 0 AND data_scadenza < CURRENT_DATE.
- Nella CTE rate stato_fornitura e una lista di stati separati da virgola (una rata puo avere piu forniture): per filtrare uno stato usa LIKE '%SOSP%', non =. Per le forniture attive usa fornitura_attiva (LIKE '%ATT%' includerebbe anche ATTC).
- Non sommare IMPORTOTOTALEFATTURATO su piu rate: e il totale del documento ripetuto su ogni rata.
- Un documento e identificato da CODICESEZIONALE + ANNODOCUMENTO + NUMERODOCUMENTO: NUMERODOCUMENTO da solo non e univoco.
- NOME, COGNOME e RAGIONESOCIALE sono in maiuscolo. Per raggruppare per cliente usa CODICESOGGETTO, non NOME e COGNOME (sono NULL per le aziende).
- Il dataset non contiene regione, provincia o comune.
- Colonne monetarie: IMPORTOFATTURATO, IMPORTOPAGATO, IMPORTOTOTALEFATTURATO, IMPORTOTOTALEPAGATO e tutto cio che ne deriva (nelle CTE: fatturato, pagato, residuo, importo_documento; nei risultati: scaduto, incassato, insoluto, importi e somme). Nel campo column_formats dichiarale come currency; conteggi (clienti, rate, bollette, giorni, solleciti) come integer; percentuali come percent.

Regole temporali (valgono per ogni domanda con riferimenti al tempo):
- Per ogni data relativa usa sempre CURRENT_DATE di DuckDB (coincide con la Data odierna del prompt); non scrivere mai la data odierna come valore letterale.
- Quale data usare: incassato, pagato, incassi -> data_pagamento; fatturato, emesso, emissione -> data_emissione; scaduto, scadenze -> data_scadenza; solleciti -> data_ultimo_sollecito. Se la domanda non indica la data, usa quella della metrica.
- ultimi N mesi = N mesi di calendario incluso il mese corrente (parziale): data >= DATE_TRUNC('month', CURRENT_DATE) - INTERVAL (N-1) MONTH (ultimi 6 mesi -> INTERVAL 5 MONTH) e data < DATE_TRUNC('month', CURRENT_DATE) + INTERVAL 1 MONTH.
- ultimi N giorni: data >= CURRENT_DATE - INTERVAL N DAY.
- mese corrente: da DATE_TRUNC('month', CURRENT_DATE) (incluso) a DATE_TRUNC('month', CURRENT_DATE) + INTERVAL 1 MONTH (escluso). mese scorso: da DATE_TRUNC('month', CURRENT_DATE) - INTERVAL 1 MONTH (incluso) a DATE_TRUNC('month', CURRENT_DATE) (escluso).
- quest'anno: data >= DATE_TRUNC('year', CURRENT_DATE). anno scorso: da DATE_TRUNC('year', CURRENT_DATE) - INTERVAL 1 YEAR (incluso) a DATE_TRUNC('year', CURRENT_DATE) (escluso).
- mese per mese / andamento mensile: una sola colonna mese = STRFTIME(data, '%Y-%m'), ordinata in modo crescente; non usare EXTRACT(YEAR) ed EXTRACT(MONTH) in colonne separate. Per gli ultimi N mesi genera tutti i mesi con generate_series e fai LEFT JOIN, con COALESCE(..., 0) per i mesi senza dati.
- Eccezione per confrontare gli stessi mesi di anni diversi (es. quest'anno contro l'anno scorso): usa EXTRACT(MONTH FROM data) come colonna mese numerica e una colonna per ogni anno con SUM(...) FILTER (WHERE EXTRACT(YEAR FROM data) = ...).
- L'incassato di una rata (pagato) e attribuito al mese della sua data_pagamento: il dataset non contiene i singoli versamenti parziali.
- Una domanda mese per mese non richiede un grafico se non e esplicitamente richiesto: plot_code = null.
"""

EXAMPLES = []


def ex(question, sql, plot=None):
    EXAMPLES.append((question, sql, plot))


ex(
    "Genera un grafico a torta che mostri la distribuzione dello scaduto per fascia di aging (0-30, 31-60, 61-90, 91-180, oltre 180 giorni)",
    RATE
    + ", scaduto AS (SELECT residuo, DATE_DIFF('day', data_scadenza, CURRENT_DATE) AS giorni FROM rate WHERE residuo > 0 AND data_scadenza < CURRENT_DATE) "
    "SELECT CASE WHEN giorni <= 30 THEN '0-30 giorni' WHEN giorni <= 60 THEN '31-60 giorni' WHEN giorni <= 90 THEN '61-90 giorni' "
    "WHEN giorni <= 180 THEN '91-180 giorni' ELSE 'oltre 180 giorni' END AS fascia_aging, MIN(giorni) AS ordine, SUM(residuo) AS totale_scaduto "
    "FROM scaduto GROUP BY 1 ORDER BY 2",
    "fig = px.pie(df, names='fascia_aging', values='totale_scaduto', title='Distribuzione dello scaduto per fascia di aging', "
    "category_orders={'fascia_aging': df['fascia_aging'].tolist()})\n"
    "fig.update_traces(textinfo='percent+label', sort=False)\nresult = fig",
)

ex(
    "Forniscimi una sintesi che evidenzi il valore totale dello scaduto, il numero di clienti a rischio e i clienti che richiedono una immediata azione di recupero",
    RATE
    + ", scaduto AS (SELECT CODICESOGGETTO, residuo, solleciti, DATE_DIFF('day', data_scadenza, CURRENT_DATE) AS giorni FROM rate WHERE residuo > 0 AND data_scadenza < CURRENT_DATE) "
    "SELECT SUM(residuo) AS totale_scaduto, COUNT(DISTINCT CODICESOGGETTO) AS clienti_a_rischio, "
    "COUNT(DISTINCT CASE WHEN giorni > 90 OR solleciti > 0 THEN CODICESOGGETTO END) AS clienti_azione_immediata, "
    "SUM(CASE WHEN giorni > 90 OR solleciti > 0 THEN residuo ELSE 0 END) AS scaduto_azione_immediata FROM scaduto",
)

ex(
    "Mostra i 20 clienti con lo scaduto piu alto, con nome, numero di rate scadute e ritardo massimo in giorni",
    RATE
    + " SELECT CODICESOGGETTO AS codice_cliente, MAX(cliente) AS cliente, COUNT(*) AS rate_scadute, "
    "MAX(DATE_DIFF('day', data_scadenza, CURRENT_DATE)) AS ritardo_massimo_giorni, SUM(residuo) AS totale_scaduto "
    "FROM rate WHERE residuo > 0 AND data_scadenza < CURRENT_DATE GROUP BY 1 ORDER BY totale_scaduto DESC LIMIT 20",
)

ex(
    "Grafico a barre dello scaduto per anno e mese di scadenza",
    RATE
    + " SELECT STRFTIME(data_scadenza, '%Y-%m') AS mese, SUM(residuo) AS totale_scaduto FROM rate "
    "WHERE residuo > 0 AND data_scadenza < CURRENT_DATE GROUP BY 1 ORDER BY 1",
    "fig = px.bar(df, x='mese', y='totale_scaduto', labels={'mese': 'Mese di scadenza', 'totale_scaduto': 'Scaduto'}, "
    "title='Scaduto per mese di scadenza')\nresult = fig",
)

ex(
    "Che percentuale di clienti ha documenti rateizzati?",
    "SELECT COUNT(DISTINCT CASE WHEN PROGRESSIVORATA <> '0' THEN CODICESOGGETTO END) AS clienti_con_rate, "
    "COUNT(DISTINCT CODICESOGGETTO) AS clienti_totali, "
    "ROUND(100.0 * COUNT(DISTINCT CASE WHEN PROGRESSIVORATA <> '0' THEN CODICESOGGETTO END) / COUNT(DISTINCT CODICESOGGETTO), 2) AS percentuale_clienti_con_rate "
    f"FROM {P}",
)

ex(
    "Incassato per canale di pagamento e anno di pagamento, grafico a barre impilate",
    RATE
    + " SELECT EXTRACT(YEAR FROM data_pagamento) AS anno, canale, SUM(pagato) AS totale_incassato FROM rate "
    "WHERE data_pagamento IS NOT NULL GROUP BY 1, 2 ORDER BY 1, 2",
    "fig = px.bar(df, x=df['anno'].astype(int).astype(str), y='totale_incassato', color='canale', barmode='stack', "
    "labels={'x': 'Anno', 'totale_incassato': 'Incassato', 'canale': 'Canale'}, title='Incassato per canale e anno di pagamento')\nresult = fig",
)

ex(
    "Tabella dello scaduto per tipo servizio e stato di morosita, con numero di clienti",
    RATE
    + " SELECT servizio, stato_morosita, COUNT(DISTINCT CODICESOGGETTO) AS numero_clienti, SUM(residuo) AS totale_scaduto "
    "FROM rate WHERE residuo > 0 AND data_scadenza < CURRENT_DATE GROUP BY 1, 2 ORDER BY totale_scaduto DESC",
)

ex(
    "Numero di bollette multirata e importo totale per tipo servizio",
    DOC
    + " SELECT servizio, COUNT(*) AS numero_bollette_multirata, SUM(importo_documento) AS importo_totale "
    "FROM documenti WHERE numero_rate > 1 GROUP BY 1 ORDER BY 2 DESC",
)

ex(
    "Elenco dei soggetti con bollette con più rate, con nome, cognome, ragione sociale, codice fiscale, partita IVA e numero di bollette multirata",
    DOC
    + f", soggetti AS (SELECT CODICESOGGETTO, ANY_VALUE(NOME) AS NOME, ANY_VALUE(COGNOME) AS COGNOME, ANY_VALUE(RAGIONESOCIALE) AS RAGIONESOCIALE, "
    f"ANY_VALUE(CODICEFISCALE) AS CODICEFISCALE, ANY_VALUE(PARTITAIVA) AS PARTITAIVA FROM {P} GROUP BY 1) "
    "SELECT s.CODICESOGGETTO, s.NOME, s.COGNOME, s.RAGIONESOCIALE, s.CODICEFISCALE, s.PARTITAIVA, COUNT(*) AS bollette_multirata "
    "FROM documenti d JOIN soggetti s ON s.CODICESOGGETTO = d.CODICESOGGETTO WHERE d.numero_rate > 1 "
    "GROUP BY 1, 2, 3, 4, 5, 6 ORDER BY bollette_multirata DESC",
)

ex(
    "Dettaglio delle bollette multirata dell'utente INCENDIO SANTOS con importo della rata, importo della bolletta e data scadenza",
    RATE
    + DOC_CHAINED
    + " SELECT r.CODICESEZIONALE, r.ANNODOCUMENTO, r.NUMERODOCUMENTO, r.PROGRESSIVORATA, r.fatturato AS importo_rata, "
    "d.importo_documento AS importo_bolletta, r.data_scadenza FROM rate r JOIN documenti d "
    "ON d.CODICESEZIONALE = r.CODICESEZIONALE AND d.ANNODOCUMENTO = r.ANNODOCUMENTO AND d.NUMERODOCUMENTO = r.NUMERODOCUMENTO "
    f"WHERE d.numero_rate > 1 AND r.CODICESOGGETTO IN (SELECT CODICESOGGETTO FROM {P} WHERE NOME = 'INCENDIO' AND COGNOME = 'SANTOS') "
    "ORDER BY r.ANNODOCUMENTO, r.NUMERODOCUMENTO, r.PROGRESSIVORATA",
)

ex(
    "Estrai il dettaglio di tutte le bollette con numero di rate, tipo bolletta (multirata o rata unica), importo documento, somma delle rate e totale per utente",
    RATE
    + DOC_CHAINED
    + ", somme AS (SELECT CODICESEZIONALE, ANNODOCUMENTO, NUMERODOCUMENTO, SUM(fatturato) AS somma_rate FROM rate GROUP BY 1, 2, 3) "
    "SELECT d.CODICESOGGETTO, d.cliente, d.ANNODOCUMENTO, d.NUMERODOCUMENTO, d.CODICESEZIONALE, d.numero_rate, "
    "CASE WHEN d.numero_rate > 1 THEN 'MULTIRATA' ELSE 'RATA UNICA' END AS tipo_bolletta, d.importo_documento, s.somma_rate, "
    "SUM(d.importo_documento) OVER (PARTITION BY d.CODICESOGGETTO) AS totale_utente, "
    "COUNT(*) OVER (PARTITION BY d.CODICESOGGETTO) AS numero_bollette_utente FROM documenti d JOIN somme s "
    "ON s.CODICESEZIONALE = d.CODICESEZIONALE AND s.ANNODOCUMENTO = d.ANNODOCUMENTO AND s.NUMERODOCUMENTO = d.NUMERODOCUMENTO "
    "ORDER BY d.cliente, d.ANNODOCUMENTO, d.NUMERODOCUMENTO",
)

COLS = (
    "sezione, gruppo, CODICESOGGETTO, cliente, stato_morosita, commodity, stati_forniture, importo_residuo, numero_rate_insolute, "
    "solleciti_doc_vecchi, data_ultimo_sollecito, giorni_da_ultimo_sollecito, rata_piu_anziana, scadenza_rata_piu_anziana, "
    "numero_clienti, perc_sul_totale"
)
LONG_SQL = (
    RATE
    + ", rate_flag AS (SELECT CODICESOGGETTO, cliente, ANNODOCUMENTO, NUMERODOCUMENTO, PROGRESSIVORATA, stato_morosita, servizio AS commodity, "
    "stato_fornitura, fornitura_attiva, data_scadenza, data_ultimo_sollecito, COALESCE(solleciti, 0) AS n_solleciti, "
    "GREATEST(COALESCE(residuo, 0), 0) AS residuo_rata, data_emissione <= CURRENT_DATE - INTERVAL 3 YEAR AS doc_vecchio, "
    "data_scadenza < CURRENT_DATE AND COALESCE(residuo, 0) > 0 AS insoluta FROM rate), "
    "clienti AS (SELECT CODICESOGGETTO, ANY_VALUE(cliente) AS cliente, SUM(n_solleciti) FILTER (WHERE doc_vecchio) AS solleciti_doc_vecchi, "
    "MAX(data_ultimo_sollecito) FILTER (WHERE doc_vecchio) AS data_ultimo_sollecito, "
    "SUM(residuo_rata) FILTER (WHERE insoluta) AS importo_residuo, COUNT(*) FILTER (WHERE insoluta) AS numero_rate_insolute, "
    "MIN(data_scadenza) FILTER (WHERE insoluta) AS scadenza_rata_piu_anziana, "
    "ARG_MIN(ANNODOCUMENTO || '/' || NUMERODOCUMENTO || ' rata ' || PROGRESSIVORATA, data_scadenza) FILTER (WHERE insoluta) AS rata_piu_anziana, "
    "STRING_AGG(DISTINCT stato_morosita, ', ') FILTER (WHERE insoluta) AS stato_morosita, "
    "STRING_AGG(DISTINCT commodity, ', ') FILTER (WHERE insoluta) AS commodity, "
    "STRING_AGG(DISTINCT stato_fornitura, ', ') FILTER (WHERE insoluta) AS stati_forniture, "
    "COALESCE(BOOL_OR(fornitura_attiva) FILTER (WHERE insoluta), FALSE) AS fornitura_attiva FROM rate_flag GROUP BY CODICESOGGETTO "
    "HAVING SUM(n_solleciti) FILTER (WHERE doc_vecchio) >= 3 AND COUNT(*) FILTER (WHERE insoluta) > 0), "
    "elenco AS (SELECT 1 AS ord, 'ELENCO CLIENTI' AS sezione, CASE WHEN fornitura_attiva THEN 'FORNITURA ATTIVA' ELSE 'FORNITURA NON ATTIVA' END AS gruppo, "
    "CODICESOGGETTO, cliente, stato_morosita, commodity, stati_forniture, ROUND(importo_residuo, 2) AS importo_residuo, numero_rate_insolute, "
    "solleciti_doc_vecchi, data_ultimo_sollecito, DATE_DIFF('day', data_ultimo_sollecito, CURRENT_DATE) AS giorni_da_ultimo_sollecito, "
    "rata_piu_anziana, scadenza_rata_piu_anziana, CAST(NULL AS BIGINT) AS numero_clienti, CAST(NULL AS DOUBLE) AS perc_sul_totale FROM clienti), "
    "distribuzione AS (SELECT 2 AS ord, 'DISTRIBUZIONE PER STATO MOROSITA' AS sezione, "
    "CASE WHEN c.fornitura_attiva THEN 'FORNITURA ATTIVA' ELSE 'FORNITURA NON ATTIVA' END AS gruppo, "
    "CAST(NULL AS VARCHAR) AS CODICESOGGETTO, CAST(NULL AS VARCHAR) AS cliente, r.stato_morosita, CAST(NULL AS VARCHAR) AS commodity, "
    "CAST(NULL AS VARCHAR) AS stati_forniture, ROUND(SUM(r.residuo_rata), 2) AS importo_residuo, COUNT(*) AS numero_rate_insolute, "
    "CAST(NULL AS BIGINT) AS solleciti_doc_vecchi, CAST(NULL AS DATE) AS data_ultimo_sollecito, CAST(NULL AS BIGINT) AS giorni_da_ultimo_sollecito, "
    "CAST(NULL AS VARCHAR) AS rata_piu_anziana, CAST(NULL AS DATE) AS scadenza_rata_piu_anziana, COUNT(DISTINCT r.CODICESOGGETTO) AS numero_clienti, "
    "ROUND(100 * SUM(r.residuo_rata) / SUM(SUM(r.residuo_rata)) OVER (), 2) AS perc_sul_totale FROM rate_flag r "
    "JOIN clienti c ON c.CODICESOGGETTO = r.CODICESOGGETTO WHERE r.insoluta GROUP BY 1, 2, 3, r.stato_morosita), "
    f"unione AS (SELECT ord, {COLS} FROM elenco UNION ALL SELECT ord, {COLS} FROM distribuzione) "
    f"SELECT {COLS} FROM unione ORDER BY ord, gruppo, importo_residuo DESC"
)
ex(
    "Individua i clienti che presentano almeno tre solleciti di pagamento su vecchi documenti emessi fino a 3 anni fa e hanno ancora rate scadute non interamente pagate. "
    "Per ciascun cliente mostra l'importo residuo, il numero di rate insolute, la data dell'ultimo sollecito, i giorni trascorsi dall'ultimo sollecito, lo stato di morosità, "
    "la commodity, lo stato delle forniture coinvolte e la rata scaduta più anziana. Evidenzia separatamente i clienti con fornitura ancora attiva e rappresenta la distribuzione "
    "dell'importo residuo per stato di morosità.",
    LONG_SQL,
)

MESI_6 = (
    ", mesi AS (SELECT STRFTIME(m, '%Y-%m') AS mese FROM generate_series("
    "CAST(DATE_TRUNC('month', CURRENT_DATE) AS DATE) - INTERVAL 5 MONTH, CAST(DATE_TRUNC('month', CURRENT_DATE) AS DATE), INTERVAL 1 MONTH) AS t(m)), "
    "incassi AS (SELECT STRFTIME(data_pagamento, '%Y-%m') AS mese, SUM(pagato) AS incassato FROM rate "
    "WHERE data_pagamento >= DATE_TRUNC('month', CURRENT_DATE) - INTERVAL 5 MONTH "
    "AND data_pagamento < DATE_TRUNC('month', CURRENT_DATE) + INTERVAL 1 MONTH GROUP BY 1) "
    "SELECT mesi.mese, COALESCE(incassi.incassato, 0) AS incassato FROM mesi LEFT JOIN incassi ON incassi.mese = mesi.mese ORDER BY mesi.mese"
)
ex("Quanto abbiamo incassato negli ultimi 6 mesi, mese per mese?", RATE + MESI_6)

MESI_12 = MESI_6.replace("INTERVAL 5 MONTH", "INTERVAL 11 MONTH")
ex(
    "Grafico a linee dell'incassato mensile degli ultimi 12 mesi",
    RATE + MESI_12,
    "fig = px.line(df, x='mese', y='incassato', markers=True, labels={'mese': 'Mese di pagamento', 'incassato': 'Incassato'}, "
    "title='Incassato mensile negli ultimi 12 mesi')\nresult = fig",
)

ex(
    "Fatturato mese per mese di quest'anno confrontato con l'anno scorso",
    RATE
    + " SELECT EXTRACT(MONTH FROM data_emissione) AS mese, "
    "SUM(fatturato) FILTER (WHERE EXTRACT(YEAR FROM data_emissione) = EXTRACT(YEAR FROM CURRENT_DATE)) AS anno_corrente, "
    "SUM(fatturato) FILTER (WHERE EXTRACT(YEAR FROM data_emissione) = EXTRACT(YEAR FROM CURRENT_DATE) - 1) AS anno_precedente "
    "FROM rate WHERE data_emissione >= DATE_TRUNC('year', CURRENT_DATE) - INTERVAL 1 YEAR AND data_emissione < DATE_TRUNC('year', CURRENT_DATE) + INTERVAL 1 YEAR "
    "GROUP BY 1 ORDER BY 1",
)

ex(
    "Incassato del mese scorso per tipo servizio",
    RATE
    + " SELECT servizio, SUM(pagato) AS incassato FROM rate WHERE data_pagamento >= DATE_TRUNC('month', CURRENT_DATE) - INTERVAL 1 MONTH "
    "AND data_pagamento < DATE_TRUNC('month', CURRENT_DATE) GROUP BY 1 ORDER BY 2 DESC",
)

ex(
    "Quanto risulta scaduto sui documenti emessi negli ultimi 90 giorni?",
    RATE
    + " SELECT COALESCE(SUM(residuo), 0) AS totale_scaduto, COUNT(*) AS rate_scadute, COUNT(DISTINCT CODICESOGGETTO) AS clienti "
    "FROM rate WHERE data_emissione >= CURRENT_DATE - INTERVAL 90 DAY AND residuo > 0 AND data_scadenza < CURRENT_DATE",
)


CUR, INT, PCT = "currency", "integer", "percent"
# Formati dichiarati per esempio, nell'ordine di EXAMPLES (colonne del risultato SQL).
FORMATS = [
    {"ordine": INT, "totale_scaduto": CUR},
    {"totale_scaduto": CUR, "clienti_a_rischio": INT, "clienti_azione_immediata": INT, "scaduto_azione_immediata": CUR},
    {"rate_scadute": INT, "ritardo_massimo_giorni": INT, "totale_scaduto": CUR},
    {"totale_scaduto": CUR},
    {"clienti_con_rate": INT, "clienti_totali": INT, "percentuale_clienti_con_rate": PCT},
    {"totale_incassato": CUR},
    {"numero_clienti": INT, "totale_scaduto": CUR},
    {"numero_bollette_multirata": INT, "importo_totale": CUR},
    {"bollette_multirata": INT},
    {"importo_rata": CUR, "importo_bolletta": CUR},
    {"numero_rate": INT, "importo_documento": CUR, "somma_rate": CUR, "totale_utente": CUR, "numero_bollette_utente": INT},
    {"importo_residuo": CUR, "numero_rate_insolute": INT, "solleciti_doc_vecchi": INT, "giorni_da_ultimo_sollecito": INT, "numero_clienti": INT, "perc_sul_totale": PCT},
    {"incassato": CUR},
    {"incassato": CUR},
    {"anno_corrente": CUR, "anno_precedente": CUR},
    {"incassato": CUR},
    {"totale_scaduto": CUR, "rate_scadute": INT, "clienti": INT},
]
assert len(FORMATS) == len(EXAMPLES), (len(FORMATS), len(EXAMPLES))


def render_example(question, sql, plot, fmt):
    body = "{\n"
    body += f'    "sql": {json.dumps(sql, ensure_ascii=False)},\n'
    body += f'    "plot_code": {json.dumps(plot, ensure_ascii=False) if plot else "null"},\n'
    body += f'    "column_formats": {json.dumps(fmt, ensure_ascii=False)},\n'
    body += '    "error": null\n}'
    return f"Input: {question}\nOutput:\n{body}"


FEW_SHOT = "\n\n".join(render_example(*e, fmt) for e, fmt in zip(EXAMPLES, FORMATS)) + "\n"

with open(f"{OUT_DIR}/SemanticMap_ESTRATTOCONTO.txt", "w", encoding="utf-8", newline="\r\n") as f:
    f.write(SEMANTIC)
with open(f"{OUT_DIR}/PromptExamples_ESTRATTOCONTO.txt", "w", encoding="utf-8", newline="\r\n") as f:
    f.write(FEW_SHOT)
with open(f"{OUT_DIR}/examples.json", "w", encoding="utf-8") as f:
    json.dump([{"q": q, "sql": s} for q, s, _ in EXAMPLES], f, ensure_ascii=False)
print("examples:", len(EXAMPLES))

# ---- Variante per MCP_NetaAnalytics.NET (EXECUTION_MODE=dotnet): FROM dataset, chart dichiarativo, un Output per riga ----
DOTNET_CHARTS = {
    0: {"title": "Distribuzione dello scaduto per fascia di aging",
        "traces": [{"type": "pie", "labels": "fascia_aging", "values": "totale_scaduto", "textinfo": "percent+label", "sort": False}]},
    3: {"title": "Scaduto per mese di scadenza",
        "traces": [{"type": "bar", "x": "mese", "y": "totale_scaduto"}],
        "layout": {"xaxis": {"title": {"text": "Mese di scadenza"}}, "yaxis": {"title": {"text": "Scaduto"}}}},
    5: {"title": "Incassato per canale e anno di pagamento",
        "traces": [{"type": "bar", "x": "anno", "y": "totale_incassato", "split_by": "canale"}],
        "layout": {"barmode": "stack", "xaxis": {"title": {"text": "Anno"}}, "yaxis": {"title": {"text": "Incassato"}},
                   "legend": {"title": {"text": "Canale"}}}},
    13: {"title": "Incassato mensile negli ultimi 12 mesi",
         "traces": [{"type": "line", "x": "mese", "y": "incassato", "mode": "lines+markers"}],
         "layout": {"xaxis": {"title": {"text": "Mese di pagamento"}}, "yaxis": {"title": {"text": "Incassato"}}}},
}


def dotnet_sql(index, sql):
    sql = sql.replace(P, "dataset")
    if index == 5:  # anno come testo: asse categorico invece di numerico
        sql = sql.replace("EXTRACT(YEAR FROM data_pagamento) AS anno", "CAST(EXTRACT(YEAR FROM data_pagamento) AS VARCHAR) AS anno")
    return sql


dotnet_blocks = []
dotnet_examples = []
for i, ((question, sql, _plot), fmt) in enumerate(zip(EXAMPLES, FORMATS)):
    net_sql = dotnet_sql(i, sql)
    output = {"sql": net_sql, "chart": DOTNET_CHARTS.get(i), "table_style": None, "column_formats": fmt, "error": None}
    dotnet_blocks.append(f"Input: {question}\nOutput: " + json.dumps(output, ensure_ascii=False, separators=(",", ":")))
    dotnet_examples.append({"q": question, "sql": net_sql})

# La semantic map e condivisa con la modalita parita: stesso testo del Python, ma neutro rispetto a plot_code/chart.
semantic_dotnet = SEMANTIC.replace(
    "richiesto: plot_code = null.", "richiesto (chart e plot_code = null).")
assert semantic_dotnet != SEMANTIC

with open(f"{OUT_DIR}/dotnet_SemanticMap_ESTRATTOCONTO.txt", "w", encoding="utf-8", newline="\r\n") as f:
    f.write(semantic_dotnet)
with open(f"{OUT_DIR}/dotnet_PromptExamples_ESTRATTOCONTO.txt", "w", encoding="utf-8", newline="\r\n") as f:
    f.write("\n\n".join(dotnet_blocks) + "\n")
with open(f"{OUT_DIR}/examples_dotnet.json", "w", encoding="utf-8") as f:
    json.dump(dotnet_examples, f, ensure_ascii=False)
print("examples dotnet:", len(dotnet_blocks))
