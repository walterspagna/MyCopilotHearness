import json
import os
import sys

import numpy as np
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go

base = r"C:\Lavoro\Workspace\NETAOS-NETAASSISTANT-BACKEND\MCP_NetaAnalytics"
os.chdir(base)
sys.path.insert(0, base)
os.environ.setdefault("ROOT_PATH_DATAFRAME", r"C:\Lavoro\MCP\RMosca\RMOSCA-primaparte")
import server as s  # noqa: E402

print("locale:", s.FORMAT_LOCALE, "| valuta:", s.FORMAT_CURRENCY, "| decimali:", s.FORMAT_DECIMALS, "| separators:", repr(s._plotly_separators()))

# template: le graffe devono restare valide per .format()
s.SYSTEM_PROMPT_TEMPLATE_DUCKDB.format(parquet_path="p", structData="{}", semantic_section="", few_shot_examples="", today="2026-10-28")
print("template .format OK")

df = pd.DataFrame({
    "mese": ["2026-05", "2026-06", "2026-07"],
    "incassato": [109738.87, 1536.75, 1536.75],
    "numero_pagamenti": [10, 3, 4],
    "quota": [12.5, 3.25, 4.0],
})
fmts = s._normalize_column_formats({"incassato": "currency", "numero_pagamenti": "integer", "quota": "percent", "x": "boh"})
print("column_formats normalizzati:", fmts)


def dump(title, fig, **kw):
    d = s._serialize_plotly_figure(fig, df, fmts) if kw.get("fmts", True) else s._serialize_plotly_figure(fig)
    lay = d["layout"]
    print(f"--- {title}")
    print("separators:", repr(lay.get("separators")))
    for key in ("yaxis", "xaxis", "yaxis2"):
        ax = lay.get(key, {})
        print(key, {k: ax.get(k) for k in ("tickformat", "hoverformat", "ticksuffix", "tickprefix") if ax.get(k)})
    for t in d["data"]:
        for attr in ("hovertemplate", "texttemplate"):
            if t.get(attr):
                print(attr, "->", t[attr])


dump("barre valuta (px, text_auto)", px.bar(df, x="mese", y="incassato", text_auto=True))
dump("barre conteggio intero", px.bar(df, x="mese", y="numero_pagamenti"))
dump("barre orizzontali valuta", px.bar(df, x="incassato", y="mese", orientation="h"))
dump("linea percentuale", px.line(df, x="mese", y="quota", markers=True))
dump("torta valuta", px.pie(df, names="mese", values="incassato"))

fig2 = go.Figure()
fig2.add_bar(x=df["mese"], y=df["incassato"], name="Incassato")
fig2.add_scatter(x=df["mese"], y=df["numero_pagamenti"], name="Pagamenti", yaxis="y2")
fig2.update_layout(yaxis2=dict(overlaying="y", side="right"))
dump("doppio asse", fig2)

fig3 = px.bar(df, x="mese", y="incassato")
fig3.update_yaxes(tickformat=".1f", ticksuffix=" k")
dump("formato esplicito del modello (non sovrascritto)", fig3)

dump("fallback sui nomi (nessun column_formats)", px.bar(df.rename(columns={"incassato": "importo_totale"}), x="mese", y="importo_totale"), fmts=False)

print("--- tabelle")
print(s._format_dataframe_for_display(df, fmts).to_string(index=False))
print("senza column_formats:")
print(s._format_dataframe_for_display(df).to_string(index=False))

out = s.formatta_risultato_per_llm(px.bar(df, x="mese", y="incassato"), "t", fmts, df)
print("formatta:", out["message"], "| contenuto json ok:", bool(json.loads(out["contentValue"])))
