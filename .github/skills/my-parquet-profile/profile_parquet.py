"""Read-only profiler for a parquet/CSV file; prints Markdown to stdout.

Usage:
  python profile_parquet.py <file> [--rows 10] [--max-rows 1000000] [--mask-columns A,B] [--no-samples]
  python profile_parquet.py <file> --query "SELECT ... FROM dataset ..." [--rows 10]
  python profile_parquet.py <file> --structure [--max-rows 3000000]
  python profile_parquet.py <file> --level "COL_A,COL_B" [--max-rows 3000000]
  python profile_parquet.py <file> --check-examples <PromptExamples/DOMAIN.txt>

The file is exposed as the view `dataset` (same name used by the NETA Analytics server).
"""
import argparse
import json
import re
import sys
import time
from pathlib import Path

import duckdb

DATE_RE = r"^\d{4}-\d{2}-\d{2}([T ]\d{2}:\d{2}(:\d{2}(\.\d+)?)?(Z|[+-]\d{2}:?\d{2})?)?$"
LOW_CARDINALITY = 30
MASK = "***"


def ident(name: str) -> str:
    return '"' + name.replace('"', '""') + '"'


def cell(value, width: int = 40) -> str:
    text = "" if value is None else str(value)
    text = text.replace("|", "/").replace("\r", " ").replace("\n", " ")
    return text if len(text) <= width else text[: width - 1] + "…"


def table(headers, rows) -> str:
    lines = ["| " + " | ".join(headers) + " |", "|" + "|".join("---" for _ in headers) + "|"]
    lines += ["| " + " | ".join(cell(v) for v in row) + " |" for row in rows]
    return "\n".join(lines)


def open_dataset(path: Path) -> duckdb.DuckDBPyConnection:
    literal = str(path).replace("'", "''")
    reader = "read_parquet" if path.suffix.lower() == ".parquet" else "read_csv_auto"
    con = duckdb.connect()
    con.execute(f"CREATE VIEW dataset AS SELECT * FROM {reader}('{literal}')")
    return con


def run_query(con, sql: str, rows: int) -> None:
    text = sql.strip().rstrip(";").strip()
    if ";" in text or not re.match(r"^(select|with)\b", text, re.IGNORECASE):
        sys.exit("Only a single SELECT/WITH statement is allowed.")
    try:
        cursor = con.execute(text)
        data = cursor.fetchmany(rows)
        headers = [d[0] for d in cursor.description]
    except duckdb.Error as ex:
        sys.exit(f"SQL error: {ex}")
    print(table(headers, data))
    print(f"\n(first {len(data)} rows shown)")


def hint(col_type: str, stats: dict, total: int) -> str:
    non_empty = stats["non_empty"]
    if col_type.startswith(("DATE", "TIMESTAMP")):
        return "date (native type)"
    if non_empty == 0:
        return "empty"
    if col_type == "VARCHAR":
        if stats["date_like"] / non_empty >= 0.95:
            note = ", has 0001-01-01 sentinel" if stats["sentinel"] else ""
            return "date in text" + note
        if stats["numeric_like"] / non_empty >= 0.95:
            if stats["leading_zero"]:
                return "numeric code (leading zeros)"
            return "integer in text (count or code?)" if stats["integral"] == non_empty else "decimal in text (amount?)"
    elif col_type in {"DOUBLE", "FLOAT"} or col_type.startswith("DECIMAL"):
        return "decimal number (amount?)"
    elif "INT" in col_type:
        return "integer (count or code?)"
    if stats["distinct"] <= LOW_CARDINALITY:
        return f"category (~{stats['distinct']} values)"
    return "free text / identifier" if col_type == "VARCHAR" else ""


def column_stats(con, name: str, col_type: str) -> dict:
    c = ident(name)
    is_text = col_type == "VARCHAR"
    extra = ""
    if is_text:
        extra = (
            f", count(*) FILTER (WHERE regexp_matches(trim({c}), '{DATE_RE}'))"
            f", count(*) FILTER (WHERE try_cast({c} AS DOUBLE) IS NOT NULL)"
            f", count(*) FILTER (WHERE regexp_matches({c}, '^0[0-9]+$'))"
            f", count(*) FILTER (WHERE regexp_matches({c}, '^-?[0-9]+$'))"
            f", count(*) FILTER (WHERE {c} LIKE '0001-01-01%')"
            f", count(*) FILTER (WHERE trim({c}) <> '')"
        )
    row = con.execute(
        f"SELECT count(*), count({c}), approx_count_distinct({c}), min({c})::VARCHAR, max({c})::VARCHAR{extra} FROM profiled"
    ).fetchone()
    stats = {"rows": row[0], "non_null": row[1], "distinct": row[2], "min": row[3], "max": row[4]}
    if is_text:
        stats.update(date_like=row[5], numeric_like=row[6], leading_zero=row[7], integral=row[8], sentinel=row[9], non_empty=row[10])
    else:
        stats.update(date_like=0, numeric_like=0, leading_zero=0, integral=0, sentinel=0, non_empty=row[1])
    return stats


def is_numeric_hint(col_type: str, stats: dict) -> bool:
    if col_type == "VARCHAR":
        return stats["non_empty"] > 0 and stats["numeric_like"] / stats["non_empty"] >= 0.95 and not stats["leading_zero"]
    return col_type in {"DOUBLE", "FLOAT"} or col_type.startswith("DECIMAL")


def print_level(con, prefix, columns, types, stats, n, always=False) -> None:
    others = [c for c, _ in columns if c not in prefix]
    group_by = ", ".join(ident(c) for c in prefix)
    inner = "count(*) AS nrows, " + ", ".join(f"count(DISTINCT {ident(c)}) AS d{i}" for i, c in enumerate(others))
    outer = "sum((nrows > 1)::INT), " + ", ".join(f"sum((d{i} > 1)::INT)" for i in range(len(others)))
    row = con.execute(f"SELECT count(*), {outer} FROM (SELECT {inner} FROM profiled GROUP BY {group_by})").fetchone()
    groups, multi, varying = row[0], row[1], row[2:]
    if groups == 0 or (multi == 0 and not always):
        return
    constant = [c for c, v in zip(others, varying) if v / groups <= 0.001]
    varies = [c for c in others if c not in constant]
    amounts = [c for c in constant if is_numeric_hint(types[c], stats[c])]
    print(f"## Level [{', '.join(prefix)}]: {groups} groups, {n} rows (x{n / groups:.2f} rows per group)\n")
    print(f"- Groups with more than one row: {multi} ({100 * multi / groups:.1f}%)")
    print(f"- Constant inside each group ({len(constant)}): {', '.join(constant) or 'none'}")
    print(f"- Varying inside the group ({len(varies)}): {', '.join(varies) or 'none'}")
    if amounts:
        print(f"- Numeric columns repeated on every row of the group (double counting if summed per row): {', '.join(amounts)}")
    print()


def prepare(con, max_rows: int):
    total = con.execute("SELECT count(*) FROM dataset").fetchone()[0]
    con.execute(f"CREATE TEMP TABLE profiled AS SELECT * FROM dataset LIMIT {int(max_rows)}")
    n = con.execute("SELECT count(*) FROM profiled").fetchone()[0]
    if n < total:
        print(f"WARNING: only {n} of {total} rows analysed: rows of the same group may be missing, so repetition levels can look weaker than they are.\n")
    columns = con.execute("SELECT column_name, column_type FROM (DESCRIBE profiled)").fetchall()
    stats = {name: column_stats(con, name, col_type) for name, col_type in columns}
    return n, columns, dict(columns), stats


def level(con, path: Path, cols: list, max_rows: int) -> None:
    """Columns constant / varying inside the groups defined by the given columns (a hypothesis chosen with the user)."""
    n, columns, types, stats = prepare(con, max_rows)
    unknown = [c for c in cols if c not in types]
    if unknown:
        sys.exit(f"Unknown columns: {', '.join(unknown)}")
    print(f"# Level analysis of {path.name} (rows analysed: {n})\n")
    print_level(con, cols, columns, types, stats, n, always=True)


def structure(con, path: Path, max_rows: int) -> None:
    """Hypotheses on the grain: a greedy candidate key and, for each key prefix, the columns constant inside each group."""
    started = time.time()
    n, columns, types, stats = prepare(con, max_rows)

    candidates = [c for c, s in stats.items() if s["non_null"] >= 0.99 * n and s["distinct"] > 1]
    key, current = [], 1
    while len(key) < 6 and candidates:
        best = None
        for c in candidates:
            cols = ", ".join(ident(k) for k in key + [c])
            d = con.execute(f"SELECT count(*) FROM (SELECT DISTINCT {cols} FROM profiled)").fetchone()[0]
            if best is None or d > best[1]:
                best = (c, d)
        if best is None or best[1] <= current:
            break
        key.append(best[0])
        candidates.remove(best[0])
        current = best[1]
        if current == n:
            break

    print(f"# Structure of {path.name}\n")
    print(f"- Rows analysed: {n}")
    if not key:
        print("- No candidate key found.")
        return
    print(f"- Candidate key (greedy, added in this order): {' + '.join(key)}")
    print(f"- Distinct key combinations: {current} (duplicate rows left: {n - current})")
    print("- These are hypotheses from the data only: confirm with the user what one row and each level mean.\n")

    for k in range(1, len(key)):
        print_level(con, key[:k], columns, types, stats, n)
    print(f"(elapsed {time.time() - started:.0f}s)")


def profile(con, path: Path, rows: int, max_rows: int, masked: set, no_samples: bool) -> None:
    total = con.execute("SELECT count(*) FROM dataset").fetchone()[0]
    con.execute(f"CREATE TEMP TABLE profiled AS SELECT * FROM dataset LIMIT {int(max_rows)}")
    profiled = con.execute("SELECT count(*) FROM profiled").fetchone()[0]
    columns = con.execute("SELECT column_name, column_type FROM (DESCRIBE profiled)").fetchall()

    print(f"# Profile of {path.name}\n")
    print(f"- Total rows: {total} (profiled: {profiled})")
    print(f"- Columns: {len(columns)}")
    if masked:
        print(f"- Masked columns: {', '.join(sorted(masked))}")
    print()

    if not no_samples:
        names = [name for name, _ in columns]
        preview = con.execute(f"SELECT * FROM profiled LIMIT {int(rows)}").fetchall()
        shown = [[MASK if names[i] in masked else v for i, v in enumerate(r)] for r in preview]
        print(f"## Preview (first {len(preview)} rows)\n")
        print(table(names, shown))
        print()

    result_rows, frequent = [], []
    for index, (name, col_type) in enumerate(columns, start=1):
        s = column_stats(con, name, col_type)
        null_pct = 0 if s["rows"] == 0 else round(100 * (s["rows"] - s["non_null"]) / s["rows"], 1)
        hide = name in masked or (no_samples and col_type == "VARCHAR")
        low, high = (MASK, MASK) if hide else (s["min"], s["max"])
        result_rows.append([index, name, col_type, null_pct, s["distinct"], low, high, hint(col_type, s, profiled)])
        if not hide and not no_samples and 0 < s["distinct"] <= LOW_CARDINALITY:
            top = con.execute(
                f"SELECT {ident(name)}::VARCHAR, count(*) FROM profiled GROUP BY 1 ORDER BY 2 DESC LIMIT 10"
            ).fetchall()
            frequent.append((name, ", ".join(f"'{cell(v, 30)}' ({round(100 * n / profiled)}%)" for v, n in top)))

    print("## Columns\n")
    print(table(["#", "Column", "Type", "Null %", "Distinct (approx)", "Min", "Max", "Hint"], result_rows))
    if frequent:
        print("\n## Frequent values (low-cardinality columns)\n")
        for name, values in frequent:
            print(f"- {name}: {values}")


def check_examples(con, examples: Path) -> None:
    """Run the SQL of every few-shot example on `dataset` and report which columns and chart kinds the examples cover."""
    if not examples.is_file():
        sys.exit(f"Examples file not found: {examples}")
    legacy = re.compile(r"(?:parquet_scan|read_parquet)\s*\(\s*'\{parquet_path\}'\s*\)", re.IGNORECASE)
    lines = examples.read_text(encoding="utf-8").splitlines()
    items, question = [], ""
    for line in lines:
        if line.startswith("Input:"):
            question = line[len("Input:"):].strip()
        elif line.startswith("Output:"):
            items.append((question, line[len("Output:"):].strip()))
    if not items:
        sys.exit("No 'Input:' / 'Output:' pairs found (expected one-line JSON after 'Output:').")

    columns = [r[0] for r in con.execute("DESCRIBE dataset").fetchall()]
    used, chart_types, tables, failed, no_sql = set(), {}, 0, 0, 0
    print(f"# Examples check: {examples.name} ({len(items)} examples)\n")
    for number, (question, payload) in enumerate(items, start=1):
        label = cell(question, 70)
        try:
            node = json.loads(payload)
        except json.JSONDecodeError as ex:
            failed += 1
            print(f"- [{number}] KO invalid JSON ({ex.msg}): {label}")
            continue
        sql = node.get("sql")
        if not sql:
            no_sql += 1
            print(f"- [{number}] no sql (error answer expected): {label}")
            continue
        sql = legacy.sub("dataset", sql).strip().rstrip(";")
        for col in columns:
            if re.search(r"\b" + re.escape(col) + r"\b", sql, re.IGNORECASE):
                used.add(col)
        chart = node.get("chart")
        for spec in (chart if isinstance(chart, list) else [chart] if isinstance(chart, dict) else []):
            for trace in spec.get("traces", []):
                chart_types[trace.get("type", "bar")] = chart_types.get(trace.get("type", "bar"), 0) + 1
        tables += 1 if node.get("table_style") else 0
        try:
            count = con.execute(f"SELECT count(*) FROM ({sql})").fetchone()[0]
            result_cols = [d[0] for d in con.execute(f"SELECT * FROM ({sql}) LIMIT 0").description]
            missing = [c for c in (node.get("column_formats") or {}) if c not in result_cols]
            for spec in (chart if isinstance(chart, list) else [chart] if isinstance(chart, dict) else []):
                for trace in spec.get("traces", []):
                    missing += [trace[k] for k in ("x", "y", "z", "labels", "values", "split_by") if isinstance(trace.get(k), str) and trace[k] not in result_cols]
            note = f" (columns not produced by the SQL: {', '.join(sorted(set(missing)))})" if missing else ""
            failed += 1 if missing else 0
            print(f"- [{number}] {'KO' if missing else 'OK'} {count} rows{note}: {label}")
        except duckdb.Error as ex:
            failed += 1
            print(f"- [{number}] KO {cell(str(ex).splitlines()[0], 150)}: {label}")

    print(f"\nFailed: {failed}")
    print("\n## Coverage\n")
    unused = [c for c in columns if c not in used]
    print(f"- Columns not referenced by any example SQL ({len(unused)}): {', '.join(unused) or 'none'}")
    print(f"- Chart traces by type: {', '.join(f'{k} x{v}' for k, v in sorted(chart_types.items())) or 'none'}")
    print(f"- Examples with table_style: {tables}")
    print(f"- Examples using CURRENT_DATE: {sum(1 for _, p in items if 'CURRENT_DATE' in p.upper())}")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("file", type=Path)
    parser.add_argument("--rows", type=int, default=10, help="rows shown in the preview / query result")
    parser.add_argument("--max-rows", type=int, default=None, help="rows used (default 1,000,000 for the profile, 3,000,000 for --structure/--level)")
    parser.add_argument("--mask-columns", default="", help="comma-separated columns whose values are hidden")
    parser.add_argument("--no-samples", action="store_true", help="no preview, no values of text columns")
    parser.add_argument("--query", help="run a SELECT/WITH on the view `dataset` and print the first rows")
    parser.add_argument("--structure", action="store_true", help="hypotheses on grain: candidate key, repetition levels, repeated amounts")
    parser.add_argument("--level", help="comma-separated columns defining a group (e.g. a document id): shows what is constant or varying inside it")
    parser.add_argument("--check-examples", type=Path, help="run the SQL of a PromptExamples/<DOMAIN>.txt file on `dataset` and report coverage")
    args = parser.parse_args()

    if not args.file.is_file():
        sys.exit(f"File not found: {args.file}")
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")

    con = open_dataset(args.file)
    if args.query:
        run_query(con, args.query, args.rows)
    elif args.structure:
        structure(con, args.file, args.max_rows or 3_000_000)
    elif args.level:
        level(con, args.file, [c.strip() for c in args.level.split(",") if c.strip()], args.max_rows or 3_000_000)
    elif args.check_examples:
        check_examples(con, args.check_examples)
    else:
        masked = {c.strip() for c in args.mask_columns.split(",") if c.strip()}
        profile(con, args.file, args.rows, args.max_rows or 1_000_000, masked, args.no_samples)


if __name__ == "__main__":
    main()
