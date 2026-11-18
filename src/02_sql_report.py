"""Run every named query in sql/analysis.sql and write the answers to markdown."""
import re
import sqlite3
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
DB = ROOT / "data" / "loans.db"
SQL = ROOT / "sql" / "analysis.sql"
OUT = ROOT / "outputs" / "sql_findings.md"

BLOCK = re.compile(r"^-- name:\s*(\w+)\s*$", re.MULTILINE)


def parse(text: str):
    """Split the file into (name, comment, statement) blocks."""
    marks = list(BLOCK.finditer(text))
    for i, m in enumerate(marks):
        end = marks[i + 1].start() if i + 1 < len(marks) else len(text)
        body = text[m.end():end].strip()
        note = " ".join(
            line.lstrip("- ").strip()
            for line in body.splitlines()
            if line.strip().startswith("--")
        )
        statement = "\n".join(
            line for line in body.splitlines() if not line.strip().startswith("--")
        ).strip()
        yield m.group(1), note, statement


def main() -> None:
    text = SQL.read_text()
    lines = ["# What the SQL says", "", "Every table below is the output of a query in `sql/analysis.sql`.", ""]
    with sqlite3.connect(DB) as con:
        for name, note, statement in parse(text):
            df = pd.read_sql_query(statement, con)
            title = name.replace("_", " ").capitalize()
            lines += [f"## {title}", ""]
            if note:
                lines += [note, ""]
            lines += [df.to_markdown(index=False), ""]
            print(f"{name}: {len(df)} rows")
    OUT.write_text("\n".join(lines))
    print(f"\nwritten to {OUT}")


if __name__ == "__main__":
    main()
