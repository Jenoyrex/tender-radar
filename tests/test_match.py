import datetime as dt

from tender_radar import build, match

TODAY = dt.date(2026, 11, 13)


def t(
    id, title, desc="", country="DEU", cpv="72000000", value_eur=None, deadline="2026-12-01", buyer="B", published="2026-11-01"
):
    return dict(
        id=id,
        title=title,
        title_en=title,
        description=desc,
        buyer=buyer,
        country=country,
        cpv=cpv,
        value=value_eur,
        currency="EUR" if value_eur else None,
        value_eur=value_eur,
        published=published,
        deadline=deadline,
        link=f"https://ted.europa.eu/en/notice/-/detail/{id}",
        notice_type="cn-standard",
    )


P = match.Profile(
    slug="p",
    name="P",
    description="cloud data warehouse dashboards analytics",
    countries=["DEU", "AUT"],
    cpv=["7231"],
    min_value_eur=10_000,
    max_value_eur=1_000_000,
    exclude_keywords=["printer"],
)


def test_filters():
    assert match.passes_filters(t("1", "x"), P, TODAY)
    assert not match.passes_filters(t("1", "x", deadline="2026-11-12"), P, TODAY)  # deadline passed
    assert match.passes_filters(t("1", "x", deadline=None), P, TODAY)  # unknown deadline kept
    assert not match.passes_filters(t("1", "x", country="FRA"), P, TODAY)
    assert not match.passes_filters(t("1", "x", value_eur=5_000), P, TODAY)
    assert not match.passes_filters(t("1", "x", value_eur=2_000_000), P, TODAY)
    assert match.passes_filters(t("1", "x", value_eur=None), P, TODAY)  # unknown value kept
    assert not match.passes_filters(t("1", "New Printer fleet"), P, TODAY)


def test_rank_orders_by_similarity_and_explains():
    ts = [
        t("1", "office furniture"),
        t("2", "data warehouse and analytics dashboards"),
        t("3", "road maintenance"),
        t("4", "furniture repair"),
        t("5", "data analytics platform"),
    ]
    res = match.rank(ts, P, today=TODAY)
    assert res[0]["id"] == "2"
    assert any(r.startswith("shared words:") and "warehouse" in r for r in res[0]["reasons"])
    assert res[0]["reasons"][0].startswith("text similarity")


def test_cpv_boost():
    ts = [t("1", "data services", cpv="72310000"), t("2", "data services", cpv="72500000"), t("3", "other thing")]
    res = match.rank(ts, P, today=TODAY)
    assert res[0]["id"] == "1"
    assert abs(res[0]["score"] - res[1]["score"] - match.CPV_BOOST) < 0.002
    assert any("CPV 72310000" in r for r in res[0]["reasons"])


def test_cpv_never_in_matcher_text():
    assert "72310000" not in match.tender_text(t("1", "x", cpv="72310000"))


def test_latest_versions_keeps_newest_duplicate():
    a = t("1", "Same call", published="2026-10-22")
    b = t("2", "Same call", published="2026-10-28")
    assert [x["id"] for x in build.latest_versions([a, b, t("3", "Other")])] == ["2", "3"]


def test_build_writes_pages(tmp_path):
    (tmp_path / "prof").mkdir()
    (tmp_path / "prof" / "x.yaml").write_text("name: X\ndescription: data analytics\ncpv: ['7231']\n", encoding="utf-8")
    ts = [t("1", "data analytics <b>", deadline="2099-01-01"), t("2", "data platform", deadline="2099-01-01")]
    build.build(ts, tmp_path / "prof", tmp_path / "site")
    html = (tmp_path / "site" / "p" / "x.html").read_text(encoding="utf-8")
    assert "data analytics &lt;b&gt;" in html and "European Union" in html
    assert "<rss" in (tmp_path / "site" / "p" / "x.xml").read_text(encoding="utf-8")
    index = (tmp_path / "site" / "index.html").read_text(encoding="utf-8")
    assert "European Union" in index
    assert index.count('<tr><td><a href="https://ted') == 2 and "data analytics &lt;b&gt;" in index  # rows present without JS


def test_feedback_links(tmp_path):
    from urllib.parse import parse_qs, urlparse

    r = dict(t("753867-2026", "IT <x>"), score=0.4, reasons=["r"])
    u = urlparse(build.feedback_url(r, "data-analytics-dach", "not relevant"))
    q = parse_qs(u.query)
    assert u.path.endswith("/issues/new")
    assert q["body"][0].startswith("feedback: not relevant | profile: data-analytics-dach | tender: 753867-2026")
    html = build.card(r, "data-analytics-dach")
    assert "issues/new?" in html and "&amp;body=" in html  # escaped inside the attribute
