"""SQLite storage. The DB is a rebuildable cache of TED, so it is not committed."""

import sqlite3
from pathlib import Path

from .clean import COLUMNS

SCHEMA = f"""
CREATE TABLE IF NOT EXISTS tenders (
    id TEXT PRIMARY KEY, {", ".join(c + (" REAL" if c in ("value", "value_eur") else " TEXT") for c in COLUMNS[1:])}
);
CREATE INDEX IF NOT EXISTS ix_deadline ON tenders(deadline);
CREATE INDEX IF NOT EXISTS ix_published ON tenders(published);
"""


def connect(path) -> sqlite3.Connection:
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    con = sqlite3.connect(path)
    con.row_factory = sqlite3.Row
    con.executescript(SCHEMA)
    return con


def upsert(con, rows: list[dict]) -> None:
    cols = ", ".join(COLUMNS)
    marks = ", ".join(f":{c}" for c in COLUMNS)
    with con:
        con.executemany(f"INSERT OR REPLACE INTO tenders ({cols}) VALUES ({marks})", rows)


def load(con, where: str = "1=1", params=()) -> list[dict]:
    return [dict(r) for r in con.execute(f"SELECT * FROM tenders WHERE {where} ORDER BY published DESC, id", params)]
