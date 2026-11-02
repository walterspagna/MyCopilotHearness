import glob
import json
import os
import sys

import duckdb

out_dir = sys.argv[1]
root = r"C:\Lavoro\MCP\RMosca"
path = glob.glob(os.path.join(root, "*", "*", "Analytics", "Source", "ESTRATTOCONTO_.parquet"))[0]
examples = json.load(open(os.path.join(out_dir, "examples_dotnet.json"), encoding="utf-8"))

con = duckdb.connect()
con.execute(f"CREATE VIEW dataset AS SELECT * FROM parquet_scan('{path.replace(chr(39), chr(39) * 2)}')")
failures = 0
for i, e in enumerate(examples, 1):
    label = f"[{i}] {e['q'][:60]}"
    try:
        df = con.execute(e["sql"]).df()
        print(label, "-> OK righe:", len(df), "colonne:", list(df.columns)[:6])
    except Exception as ex:
        failures += 1
        print(label, "-> KO:", str(ex)[:300])
print("falliti:", failures)
