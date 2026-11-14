"""SQLite storage. Schema changes only ever add columns (ensure_columns); no table holding data is dropped."""

import sqlite3
from pathlib import Path

from .clean import COLUMNS


def col_type(c: str) -> str:
    return "REAL" if c in ("value", "value_eur") else "TEXT"


SCHEMA = f"""
CREATE TABLE IF NOT EXISTS tenders (
    id TEXT PRIMARY KEY, {", ".join(f"{c} {col_type(c)}" for c in COLUMNS[1:])}
);
CREATE INDEX IF NOT EXISTS ix_deadline ON tenders(deadline);
CREATE INDEX IF NOT EXISTS ix_published ON tenders(published);
"""


def ensure_columns(con: sqlite3.Connection, table: str, types: dict[str, str]) -> list[str]:
    """Non-destructive migration: add any missing columns (existing rows get NULL). Never drops
    data; columns the code no longer uses are simply left in place. Returns the added names."""
    have = {r[1] for r in con.execute(f"PRAGMA table_info({table})")}
    added = [c for c in types if c not in have]
    with con:
        for c in added:
            con.execute(f"ALTER TABLE {table} ADD COLUMN {c} {types[c]}")
    return added


def connect(path) -> sqlite3.Connection:
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    con = sqlite3.connect(path)
    con.row_factory = sqlite3.Row
    con.executescript(SCHEMA)  # CREATE ... IF NOT EXISTS: a no-op on an existing table
    ensure_columns(con, "tenders", {c: col_type(c) for c in COLUMNS[1:]})
    return con


def upsert(con, rows: list[dict]) -> None:
    cols = ", ".join(COLUMNS)
    marks = ", ".join(f":{c}" for c in COLUMNS)
    with con:
        con.executemany(f"INSERT OR REPLACE INTO tenders ({cols}) VALUES ({marks})", rows)


def load(con, where: str = "1=1", params=()) -> list[dict]:
    return [dict(r) for r in con.execute(f"SELECT * FROM tenders WHERE {where} ORDER BY published DESC, id", params)]
