import os
import sys

import pandas as pd
import plotly.express as px

base = r"C:\Lavoro\Workspace\NETAOS-NETAASSISTANT-BACKEND\MCP_NetaAnalytics"
os.chdir(base)
sys.path.insert(0, base)
os.environ.setdefault("ROOT_PATH_DATAFRAME", r"C:\Lavoro\MCP\RMosca\RMOSCA-primaparte")

import server as s  # noqa: E402

empty = pd.DataFrame({"mese": [], "incassato": []})
one_null = pd.DataFrame({"totale": [None]})
one_zero = pd.DataFrame({"conteggio": [0]})
normal = pd.DataFrame({"mese": ["2026-10"], "incassato": [10.0]})
partial = pd.DataFrame({"a": [None], "b": [0]})

print("vuoto            ->", s._is_no_data_result(empty))
print("una riga NULL    ->", s._is_no_data_result(one_null))
print("conteggio 0      ->", s._is_no_data_result(one_zero))
print("riga normale     ->", s._is_no_data_result(normal))
print("NULL + valore    ->", s._is_no_data_result(partial))
print("None             ->", s._is_no_data_result(None))

fig = px.bar(empty, x="mese", y="incassato")
print("tracce figura vuota:", len(fig.to_dict().get("data", [])))
out = s.formatta_risultato_per_llm(fig, "test")
print("figura senza tracce ->", out["message"], "|", out["contentType"])
out = s.formatta_risultato_per_llm({"a": fig}, "test")
print("dict di figure      ->", out["message"])
out = s.formatta_risultato_per_llm([fig], "test")
print("lista di figure     ->", out["message"])
out = s.formatta_risultato_per_llm(px.bar(normal, x="mese", y="incassato"), "test")
print("figura normale      ->", out["message"], "|", out["contentType"])
print("messaggio:", s.NO_DATA_MESSAGE)
