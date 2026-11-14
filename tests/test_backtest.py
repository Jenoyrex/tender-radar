import numpy as np

from tender_radar import backtest


def tender(i, published, deadline, text, country="DEU", cpv="72222300", proc=None):
    return {
        "id": f"{i}-2025",
        "title": text,
        "title_en": f"Germany – IT services – {text}",
        "description": text,
        "buyer": f"buyer {i}",
        "country": country,
        "cpv": cpv,
        "main_cpv": cpv,
        "cpv_label": "IT services",
        "value": None,
        "currency": None,
        "value_eur": None,
        "published": published,
        "deadline": deadline,
        "procedure_id": proc or f"p{i}",
    }


def win(n, published, proc, entity=1, text="Geoportal GIS Wartung", country="DEU", cpv="72222300"):
    return {
        "notice_id": f"w{n}",
        "procedure_id": proc,
        "published": published,
        "entity": entity,
        "winner_name": "Geo Daten GmbH",
        "text": text,
        "title_en": f"Germany – GIS – {text}",
        "buyer_country": country,
        "main_cpv": cpv,
    }


GIS = "Betrieb und Wartung Geoportal GIS Kartendienst"
TENDERS = (
    [tender(1, "2025-03-01", "2025-04-01", GIS, proc="target")]
    + [tender(i, "2025-02-20", "2025-03-30", f"Lieferung von Druckern und Kopierern Los {i}") for i in range(2, 40)]
    + [
        tender(90, "2024-01-01", "2024-02-01", GIS + " alt"),  # closed long before d: not in the pool
        tender(91, "2025-02-01", None, "ohne Frist GIS"),  # no deadline, 28 days old: in the pool
        tender(92, "2024-10-01", None, "ohne Frist alt"),  # no deadline, > 60 days old: out
        tender(93, "2025-02-25", "2025-03-30", GIS, country="FRA"),  # other country: filtered out
    ]
)
WINS = [
    win(1, "2024-05-01", "a"),
    win(2, "2024-07-01", "b"),
    win(3, "2024-09-01", "c"),
    win(4, "2025-06-01", "target"),  # held-out: latest linked win
    win(5, "2025-07-01", "unlinked"),  # later but not linked to a contract notice: still trains? no, after d
    win(6, "2025-01-01", "target"),  # another lot of the same procedure: never in training
    # a company with too few wins
    win(7, "2024-05-01", "x", entity=2),
    win(8, "2025-06-01", "target", entity=2),
]


def test_cases_use_only_earlier_wins_of_other_procedures():
    cases, funnel = backtest.make_cases(TENDERS, WINS)
    assert len(cases) == 1 and funnel["usable cases"] == 1
    c = cases[0]
    assert c.held["notice_id"] == "w4" and c.date == "2025-03-01"
    assert [w["notice_id"] for w in c.train] == ["w3", "w2", "w1"]  # newest first; w5 is after d, w6 same procedure


def test_pool_is_open_on_d_and_respects_product_filters():
    c = backtest.make_cases(TENDERS, WINS)[0][0]
    p = backtest.case_profile(c)
    assert p.countries == ["DEU"] and p.cpv == ["7222"] and "Geoportal" in p.description
    ids = {t["id"] for t in backtest.pool(TENDERS, c.date, p)}
    assert "1-2025" in ids and "91-2025" in ids
    assert not ids & {"90-2025", "92-2025", "93-2025"}


def test_run_ranks_the_relevant_tender_first_and_random_does_worse():
    results, _ = backtest.run(TENDERS, WINS)
    r = results[0]
    assert not r["filtered_out"] and r["pool"] == 40
    assert r["ranks"]["char-tfidf"] == 1 and r["ranks"][backtest.CURRENT] == 1
    assert r["ranks"]["same-main-cpv"] > 10  # all pool items share the CPV: a 40-way tie -> expected rank 20.5
    assert "e5" not in r["ranks"]  # no embeddings passed


def test_rank_of_counts_ties_as_expected_rank():
    s = np.array([0.9, 0.5, 0.5, 0.5, 0.1])
    assert backtest.rank_of(s, np.array([False, True, False, False, False])) == 2 + 2 / 2
    assert backtest.rank_of(s, np.array([True, False, False, False, True])) == 1  # best of two target items


def _res(part, ranks, filtered=False):
    return {"part": part, "filtered_out": filtered, "ranks": ranks, "pool": 100}


def test_metrics_treat_filtered_out_as_miss():
    rs = [_res("test", {"m": 1}), _res("test", {"m": 30}), _res("test", {"m": 200}), _res("test", {}, True)]
    x = backtest.metrics(rs, "m")
    assert x["hit@10"] == 0.25 and x["hit@50"] == 0.5 and x["median"] == (30 + 200) / 2


def test_choose_on_dev_ignores_baselines_and_keeps_current_on_ties():
    cur = backtest.CURRENT
    rs = [
        _res("dev", {cur: 5, "char-tfidf": 5, "random": 1, "same-main-cpv": 1}),
        _res("test", {cur: 50, "char-tfidf": 1, "random": 1, "same-main-cpv": 1}),
    ]
    assert backtest.choose(rs) == cur
    rs[0]["ranks"]["char-tfidf"] = 2
    rs[0]["ranks"][cur] = 20
    assert backtest.choose(rs) == "char-tfidf"


def test_bootstrap_diff_ci_contains_the_mean():
    rs = [_res("test", {"a": 1 if i % 2 else 100, "b": 100}) for i in range(100)]
    diff, lo, hi = backtest.bootstrap_diff(rs, "a", "b")
    assert diff == 0.5 and lo < 0.5 < hi and lo > 0.3


def test_to_markdown_labels_every_matcher():
    cur = backtest.CURRENT
    ms = {cur: 3, "char-tfidf": 2, "english-tfidf": 9, "e5": 4, "blend w=0.5": 1, "random": 30, "same-main-cpv": 8}
    rs = [_res("dev", dict(ms)), _res("test", dict(ms))] * 3
    md = backtest.to_markdown(rs, {"usable cases": 6})
    assert "Baseline: random order" in md and "multilingual-e5-small" in md and "Blend w=0.5" in md
    assert "chosen on dev" in md and "95% bootstrap CI" in md
