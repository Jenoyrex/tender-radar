import copy
import json
from pathlib import Path

import pytest

from tender_radar import db
from tender_radar.clean import SchemaError, clean, clean_all
from tender_radar.ted import build_query
import datetime as dt

RAW = json.loads((Path(__file__).parent / "fixtures" / "search_page.json").read_text(encoding="utf-8"))


def test_fixture_cleans():
    rows = clean_all(RAW)
    assert len(rows) == len(RAW)
    for r in rows:
        assert r["title"] and r["country"] and len(r["country"]) == 3
        assert r["published"] == "2026-11-12"
        assert r["link"].endswith(r["id"])
        assert all(len(c) == 8 for c in r["cpv"].split())


def test_missing_value_stays_null():
    n = copy.deepcopy(RAW[0])
    for k in ("estimated-value-proc", "estimated-value-cur-proc", "estimated-value-lot", "estimated-value-cur-lot"):
        n.pop(k, None)
    r = clean(n)
    assert r["value"] is None and r["currency"] is None and r["value_eur"] is None


def test_value_from_lots_needs_single_currency():
    n = copy.deepcopy(RAW[0])
    n.pop("estimated-value-proc", None)
    n["estimated-value-lot"], n["estimated-value-cur-lot"] = ["100", "50"], ["EUR", "EUR"]
    assert clean(n)["value"] == 150
    n["estimated-value-cur-lot"] = ["EUR", "PLN"]
    assert clean(n)["value"] is None


def test_unknown_currency_has_no_eur_value():
    n = copy.deepcopy(RAW[0])
    n["estimated-value-proc"], n["estimated-value-cur-proc"] = "1000", "XYZ"
    r = clean(n)
    assert r["value"] == 1000 and r["value_eur"] is None


def test_deadline_is_latest_lot():
    n = copy.deepcopy(RAW[0])
    n["deadline-receipt-tender-date-lot"] = ["2026-12-01+01:00", "2026-12-20+01:00"]
    assert clean(n)["deadline"] == "2026-12-20"


def test_dedup_on_id():
    assert len(clean_all([RAW[0], copy.deepcopy(RAW[0])])) == 1


@pytest.mark.parametrize("field,bad", [
    ("publication-number", None),
    ("publication-number", "not-an-id"),
    ("classification-cpv", "72000000"),
    ("classification-cpv", ["72x"]),
    ("publication-date", "yesterday"),
    ("title-proc", "plain string"),
])
def test_schema_change_fails_loudly(field, bad):
    n = copy.deepcopy(RAW[0])
    n[field] = bad
    with pytest.raises(SchemaError):
        clean(n)


def test_db_upsert_dedupes(tmp_path):
    con = db.connect(tmp_path / "t.sqlite")
    rows = clean_all(RAW)
    db.upsert(con, rows)
    db.upsert(con, rows)
    assert len(db.load(con)) == len(rows)


def test_build_query():
    q = build_query(dt.date(2026, 11, 2), ["72", "48"], ["DEU"])
    assert q == "PD=20261102 AND form-type=competition AND (classification-cpv=72* OR classification-cpv=48*) AND buyer-country IN (DEU)"


def test_english_fields():
    n = copy.deepcopy(RAW[0])
    n["notice-title"] = {"eng": "Sweden – Software development services – Nytt system"}
    n["title-proc"] = {"swe": "Nytt system"}
    n["main-classification-proc"] = ["72212000"]
    r = clean(n)
    assert r["cpv_label"] == "Software development services"
    assert r["main_cpv"] == "72212000"
    assert r["title_english"] is None  # the template title is not a translation
    n["title-proc"] = {"swe": "Nytt system", "eng": "New system"}
    assert clean(n)["title_english"] == "New system"
    n["main-classification-proc"] = ["7221"]
    with pytest.raises(SchemaError):
        clean(n)
