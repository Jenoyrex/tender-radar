import csv
import re
from urllib.parse import parse_qs, urlparse

from tender_radar import build, feedback


def gh_issue(n, verdict, profile="web-studio-iberia", tender="123-2026", title=None, **kw):
    return {
        "number": n,
        "created_at": "2026-11-14T08:00:00Z",
        "title": title or f"[feedback] {verdict}: {profile} / {tender}",
        "body": f"feedback: {verdict} | profile: {profile} | tender: {tender} | score: 0.412\n\nTender: x",
    } | kw


def test_parse_reads_the_line_build_writes():
    """Round trip: the prefilled issue body from build.feedback_url parses back."""
    t = {"id": "777-2026", "score": 0.5, "title_en": "T", "title": "T", "link": "L"}
    q = parse_qs(urlparse(build.feedback_url(t, "my-profile", "not relevant")).query)
    row = feedback.parse({"number": 1, "created_at": "2026-11-14T00:00:00Z", "title": q["title"][0], "body": q["body"][0]})
    assert row == {
        "issue": 1,
        "created": "2026-11-14",
        "verdict": "not relevant",
        "profile": "my-profile",
        "tender": "777-2026",
        "score": 0.5,
    }


def test_parse_ignores_other_issues_and_prs():
    assert feedback.parse(gh_issue(1, "relevant", title="Get my tender feed")) is None
    assert feedback.parse(gh_issue(2, "relevant", pull_request={})) is None
    assert feedback.parse(gh_issue(3, "relevant") | {"body": "feedback: maybe | profile: x"}) is None


def test_fetch_all_pages_and_report(tmp_path):
    pages = {
        1: [gh_issue(i, "relevant", tender=f"{i}-2026") for i in range(1, 101)],
        2: [gh_issue(101, "not relevant", tender="1-2026"), gh_issue(102, "relevant", profile="other")],
    }
    rows = feedback.fetch_all(lambda path: pages[int(re.search(r"[?&]page=(\d+)", path).group(1))])
    assert len(rows) == 102
    out = tmp_path / "f.csv"
    feedback.write(rows, out)
    assert len(list(csv.DictReader(out.open(encoding="utf-8")))) == 102
    rep = feedback.report(rows)
    assert "102 feedback issues, 101 distinct" in rep  # issue 101 re-votes on tender 1-2026
    assert "web-studio-iberia: 99 relevant, 1 not relevant" in rep and "other: 1 relevant, 0 not relevant" in rep
