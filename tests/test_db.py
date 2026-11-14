import sqlite3

import pytest

from tender_radar import awards, db
from tender_radar.clean import COLUMNS


def test_old_schema_tenders_rows_survive_and_gain_new_columns(tmp_path):
    path = tmp_path / "old.sqlite"
    old_cols = [c for c in COLUMNS if c not in ("procedure_id", "title_english")]  # an older release
    con = sqlite3.connect(path)
    con.execute(f"CREATE TABLE tenders (id TEXT PRIMARY KEY, {', '.join(c + ' TEXT' for c in old_cols[1:])}, legacy TEXT)")
    con.execute("INSERT INTO tenders (id, title, published, legacy) VALUES ('1-2026', 'Zürich portal', '2026-01-01', 'x')")
    con.commit()
    con.close()

    con = db.connect(path)
    rows = db.load(con)
    assert len(rows) == 1 and rows[0]["title"] == "Zürich portal"
    assert rows[0]["procedure_id"] is None and "title_english" in rows[0]
    assert rows[0]["legacy"] == "x"  # unknown old columns are kept, not dropped
    row = {c: None for c in COLUMNS} | {"id": "2-2026", "procedure_id": "p2", "published": "2026-02-01"}
    db.upsert(con, [row])
    assert [r["id"] for r in db.load(con)] == ["2-2026", "1-2026"]
    assert db.ensure_columns(con, "tenders", {"title": "TEXT"}) == []  # idempotent


def _win(n, **kw):
    return (
        {c: None for c in awards.WIN_COLUMNS}
        | {"notice_id": f"{n}", "winner_norm": f"firm {n}", "winner_country": "DEU", "published": "2026-01-01"}
        | kw
    )


def test_old_schema_wins_table_is_migrated_not_dropped(tmp_path):
    con = db.connect(tmp_path / "history.sqlite")
    con.execute(
        "CREATE TABLE wins (notice_id TEXT, winner_norm TEXT, winner_id TEXT, entity INTEGER, "
        "PRIMARY KEY (notice_id, winner_norm, winner_id))"
    )
    con.execute("INSERT INTO wins VALUES ('old', 'old firm', NULL, 0)")
    con.commit()
    awards.store(con, [_win(1, text="GIS Wartung"), _win(2)])
    cols = {r[1] for r in con.execute("PRAGMA table_info(wins)")}
    assert {"text", "title_en", "procedure_id"} <= cols
    assert sorted(r[0] for r in con.execute("SELECT notice_id FROM wins")) == ["1", "2"]


def test_failed_wins_refresh_keeps_the_old_rows(tmp_path):
    con = db.connect(tmp_path / "history.sqlite")
    awards.store(con, [_win(1), _win(2)])
    bad = [_win(3), _win(4, text=object())]  # second row can't be stored: the insert fails half-way
    with pytest.raises(sqlite3.Error):
        awards.store(con, bad)
    assert sorted(r[0] for r in con.execute("SELECT notice_id FROM wins")) == ["1", "2"]
