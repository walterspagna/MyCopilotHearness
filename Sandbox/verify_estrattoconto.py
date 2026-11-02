import glob
import json
import os
import sys

import duckdb

out_dir = sys.argv[1]
root = r"C:\Lavoro\MCP\RMosca"
files = glob.glob(os.path.join(root, "*", "*", "Analytics", "Source", "ESTRATTOCONTO_.parquet")) or glob.glob(os.path.join(root, "*", "*", "Analytics", "ESTRATTOCONTO_*.parquet"))
print("parquet trovati:", len(files))
examples = json.load(open(os.path.join(out_dir, "examples.json"), encoding="utf-8"))
con = duckdb.connect()

if not files:
    print("Nessun parquet: solo parse via EXPLAIN su tabella vuota non possibile")
    sys.exit(1)
path = files[0]

for i, e in enumerate(examples, 1):
    sql = e["sql"].replace("{parquet_path}", path.replace("'", "''"))
    label = f"[{i}] {e['q'][:60]}"
    try:
        con.execute("EXPLAIN " + sql).fetchall()
    except Exception as ex:
        print(label, "-> EXPLAIN KO:", str(ex)[:300])
        continue
    try:
        df = con.execute(sql).df()
        print(label, "-> OK righe:", len(df), "colonne:", len(df.columns))
        if i >= 14:  # esempi temporali: solo aggregati, niente dati personali
            print(df.head(14).to_string(index=False))
    except Exception as ex:
        print(label, "-> EXEC KO:", str(ex)[:300])

r = con.execute(
    f"SELECT MIN(TRY_CAST(DATAPAGAMENTO AS DATE)), MAX(TRY_CAST(DATAPAGAMENTO AS DATE)), MAX(TRY_CAST(DATAEMISSIONE AS DATE)) FROM parquet_scan('{path}')"
).fetchall()
print("DATAPAGAMENTO min/max, DATAEMISSIONE max:", r)
