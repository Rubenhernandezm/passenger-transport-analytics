#!/usr/bin/env python3
"""
Create the database, load the synthetic CSVs into the src schema and build
the dw views, then print the validation checks.

Configuration comes from environment variables (see .env.example):
    MSSQL_SA_PASSWORD   required
    DB_HOST             default: localhost
    DB_PORT             default: 1433
    DB_USER             default: sa
    DB_NAME             default: TransportAnalytics
"""
from __future__ import annotations

import csv
import os
import re
import sys
import time
from pathlib import Path

import pymssql

ROOT = Path(__file__).resolve().parents[1]
DATA, SQL = ROOT / "data", ROOT / "sql"

HOST = os.getenv("DB_HOST", "localhost")
PORT = int(os.getenv("DB_PORT", "1433"))
USER = os.getenv("DB_USER", "sa")
PASSWORD = os.getenv("MSSQL_SA_PASSWORD")
DB = os.getenv("DB_NAME", "TransportAnalytics")

# load order follows the logical dependencies of the source systems
TABLES = ["companies", "customers", "products", "delivery_notes", "sales_lines",
          "vehicles", "fuel_card_transactions", "telematics_monthly"]
GO = re.compile(r"^\s*GO\s*$", re.IGNORECASE | re.MULTILINE)
BATCH = 1000


def connect(database: str = "master", autocommit: bool = True, attempts: int = 40):
    for attempt in range(1, attempts + 1):
        try:
            return pymssql.connect(server=HOST, port=PORT, user=USER, password=PASSWORD,
                                   database=database, autocommit=autocommit, charset="UTF-8")
        except pymssql.Error:
            if attempt == attempts:
                raise
            print(f"SQL Server not ready yet ({attempt}/{attempts}), retrying in 5 s...")
            time.sleep(5)


def print_result(cursor) -> None:
    cols = [c[0] for c in cursor.description]
    rows = cursor.fetchall()
    widths = [max([len(str(c))] + [len(str(r[i])) for r in rows]) for i, c in enumerate(cols)]
    print("   " + "  ".join(str(c).ljust(w) for c, w in zip(cols, widths)))
    for r in rows:
        print("   " + "  ".join(str(v).ljust(w) for v, w in zip(r, widths)))
    print()


def run_script(conn, path: Path) -> None:
    print(f"-> {path.name}")
    cursor = conn.cursor()
    for batch in GO.split(path.read_text(encoding="utf-8")):
        if not batch.strip():
            continue
        cursor.execute(batch)
        while True:
            if cursor.description:
                print_result(cursor)
            if not cursor.nextset():
                break
    cursor.close()


def load_table(conn, table: str) -> None:
    path = DATA / f"{table}.csv"
    with path.open(encoding="utf-8", newline="") as f:
        reader = csv.reader(f)
        header = next(reader)
        rows = [tuple(v if v != "" else None for v in row) for row in reader]
    sql = (f"INSERT INTO src.{table} ({', '.join(header)}) "
           f"VALUES ({', '.join(['%s'] * len(header))})")
    cursor = conn.cursor()
    for i in range(0, len(rows), BATCH):
        cursor.executemany(sql, rows[i:i + BATCH])
    conn.commit()
    cursor.close()
    print(f"   src.{table:<24} {len(rows):>7,} rows")


def main() -> None:
    if not PASSWORD:
        sys.exit("MSSQL_SA_PASSWORD is not set (copy .env.example to .env).")
    missing = [t for t in TABLES if not (DATA / f"{t}.csv").exists()]
    if missing:
        sys.exit(f"Missing CSVs in {DATA}: {missing}. Run generator/generate_data.py first.")

    master = connect()
    master.cursor().execute(f"IF DB_ID(N'{DB}') IS NULL CREATE DATABASE [{DB}];")
    master.close()

    conn = connect(DB)
    run_script(conn, SQL / "01_schema.sql")
    conn.close()

    print("-> loading CSVs into src")
    loader = connect(DB, autocommit=False)
    for table in TABLES:
        load_table(loader, table)
    loader.close()

    conn = connect(DB)
    for script in ("02_dimensions.sql", "03_facts.sql", "04_checks.sql"):
        run_script(conn, SQL / script)
    conn.close()
    print(f"Done. Connect Power BI to {HOST},{PORT} / database {DB} and import the dw views.")


if __name__ == "__main__":
    main()
