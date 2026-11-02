import glob
import json
import os
import re

import duckdb

base = r"C:\Lavoro\Workspace\NETAOS-NETAASSISTANT-BACKEND\MCP_NetaAnalytics"
sem = open(os.path.join(base, "SemanticMap", "ESTRATTOCONTO.txt"), encoding="utf-8").read()
fs = open(os.path.join(base, "PromptExamples", "ESTRATTOCONTO.txt"), encoding="utf-8").read()

rate = re.search(r"CTE rate: (WITH rate AS \(.*?\))\r?\n", sem).group(1)
doc = re.search(r"CTE documenti: (WITH documenti AS \(.*?\))\r?\n", sem).group(1)
rate_chained = rate.replace("WITH rate AS", ", rate AS", 1)
doc_chained = doc.replace("WITH documenti AS", ", documenti AS", 1)

blocks = re.split(r"\r?\n\r?\n(?=Input: )", fs.strip())
print("esempi:", len(blocks))
for i, b in enumerate(blocks, 1):
    q = re.match(r"Input: (.*)", b).group(1)
    sql = json.loads(re.search(r'"sql": (".*?"),\r?\n\s+"plot_code"', b, re.S).group(1))
    issues = []
    if "rate AS (" in sql and rate not in sql and rate_chained not in sql:
        issues.append("CTE rate NON identica")
    if "documenti AS (" in sql and doc not in sql and doc_chained not in sql:
        issues.append("CTE documenti NON identica")
    if re.search(r"SELECT\s+DISTINCT", sql, re.I):
        issues.append("SELECT DISTINCT")
    if re.search(r"SELECT\s+\*", sql, re.I):
        issues.append("SELECT *")
    if re.search(r"'20\d\d-\d\d-\d\d", sql):
        issues.append("data letterale")
    if re.search(r"\bbollett", q, re.I) and "tipo_doc" not in sql:
        issues.append("domanda su 'bollette' senza filtro tipo_doc (ammesso dalla regola)")
    uses_cte = "rate AS (" in sql or "documenti AS (" in sql
    if not uses_cte:
        issues.append("legge il parquet direttamente (ammesso solo per conteggi senza importi)")
    print(f"[{i}] {q[:70]} -> {'; '.join(issues) if issues else 'OK'}")

root = r"C:\Lavoro\MCP\RMosca"
p = glob.glob(os.path.join(root, "*", "*", "Analytics", "Source", "ESTRATTOCONTO_.parquet"))[0]
con = duckdb.connect()
print(con.execute(f"""SELECT TIPODOCFISICOID AS tipo_doc, COUNT(DISTINCT CODICESEZIONALE||ANNODOCUMENTO||NUMERODOCUMENTO) AS documenti FROM parquet_scan('{p}') GROUP BY 1 ORDER BY 2 DESC""").df().to_string(index=False))
print(con.execute(f"""WITH d AS (SELECT ANY_VALUE(TIPODOCFISICOID) AS t, COUNT(DISTINCT PROGRESSIVORATA) AS n FROM parquet_scan('{p}') GROUP BY CODICESEZIONALE, ANNODOCUMENTO, NUMERODOCUMENTO) SELECT t, COUNT(*) FILTER (WHERE n > 1) AS multirata, COUNT(*) AS totale FROM d GROUP BY 1 ORDER BY 3 DESC""").df().to_string(index=False))
print(con.execute(f"""SELECT COUNT(*) AS rate_con_stato_multiplo FROM (SELECT 1 FROM parquet_scan('{p}') GROUP BY CODICESEZIONALE, ANNODOCUMENTO, NUMERODOCUMENTO, PROGRESSIVORATA HAVING COUNT(DISTINCT STATOFORNITURA) > 1)""").fetchall())
