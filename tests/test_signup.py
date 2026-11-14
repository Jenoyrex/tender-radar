import datetime as dt
import json
import re
import types

import pytest
import yaml

from tender_radar import cli, match, signup

DESC = "We build and maintain websites and web portals on open-source CMS for public bodies."


def form(**fields):
    labels = {
        "name": "Company name",
        "desc": "What does your business do?",
        "countries": "Countries",
        "lo": "Minimum contract value (EUR)",
        "hi": "Maximum contract value (EUR)",
        "excl": "Words to exclude",
    }
    return "\n\n".join(f"### {labels[k]}\n\n{fields.get(k) or '_No response_'}" for k in labels)


def issue(body, number=42, labels=("signup",), login="alice", assoc="NONE"):
    return {
        "number": number,
        "body": body,
        "labels": [{"name": x} for x in labels],
        "user": {"login": login},
        "author_association": assoc,
    }


NO_WINS = types.SimpleNamespace(
    search=lambda n, c: [], own_wins=lambda n, ns: [], make_profile=lambda n, w: (_ for _ in ()).throw(ValueError("none"))
)
WINS = types.SimpleNamespace(
    search=lambda n, c: ["x"],
    own_wins=lambda n, ns: ns,
    make_profile=lambda n, w: {
        "name": f"{n} (from 7 past TED wins)",
        "description": "Wartung GIS",
        "countries": ["DEU"],
        "cpv": ["7222"],
    },
)


def test_parse_form_handles_no_response():
    f = signup.parse_form(form(desc=DESC))
    assert f["What does your business do?"] == DESC and f["Company name"] == ""


def test_valid_signup_from_description(tmp_path):
    body = form(desc=DESC, countries="Portugal (PRT), Spain (ESP)", lo="10 000", hi="750,000", excl="hardware, printers")
    slug, prof = signup.profile_from_issue(issue(body), tmp_path, {}, lookup=NO_WINS)
    assert slug.endswith("-42") and slug.startswith("we-build")
    assert prof["countries"] == ["ESP", "PRT"] and prof["min_value_eur"] == 10000 and prof["max_value_eur"] == 750000
    assert prof["exclude_keywords"] == ["hardware", "printers"] and prof["signup_issue"] == 42
    f = tmp_path / f"{slug}.yaml"
    f.write_text(yaml.safe_dump(prof), encoding="utf-8")
    assert match.Profile.load(f).description == DESC  # loadable by the matcher


def test_signup_from_company_name_uses_past_wins(tmp_path):
    slug, prof = signup.profile_from_issue(issue(form(name="Geo Daten GmbH")), tmp_path, {}, lookup=WINS)
    assert slug == "geo-daten-42" and prof["description"] == "Wartung GIS"
    assert prof["countries"] == ["DEU"] and prof["cpv"] == ["7222"] and "7 past TED wins" in prof["name"]


@pytest.mark.parametrize(
    "body, reason",
    [
        (form(), "company name"),
        (form(desc="cheap seo"), "8+ words"),
        (form(desc=DESC + " Visit https://spam.example now"), "links"),
        (form(desc=DESC, countries="Narnia"), "Unknown country"),
        (form(desc=DESC, lo="lots"), "whole number"),
        (form(desc=DESC, lo="900000", hi="1000"), "larger than"),
        (form(desc="word " * 400), "too long"),
        (form(name="Nobody Ltd"), "no EU (TED)"),
    ],
)
def test_invalid_or_spam_signups_are_rejected(tmp_path, body, reason):
    with pytest.raises(signup.Rejected, match=re.escape(reason)):
        signup.profile_from_issue(issue(body), tmp_path, {}, lookup=NO_WINS)


def _profiles(tmp_path):
    (tmp_path / "web-42.yaml").write_text(
        yaml.safe_dump({"name": "w", "description": DESC, "signup_issue": 42}), encoding="utf-8"
    )
    (tmp_path / "example.yaml").write_text(yaml.safe_dump({"name": "e", "description": DESC}), encoding="utf-8")
    return tmp_path


@pytest.mark.parametrize("ref", ["https://jenoyrex.github.io/tender-radar/p/web-42.html", "42", "#42", "web-42"])
def test_remove_finds_profile_by_link_number_or_slug(tmp_path, ref):
    body = f"### Your feed page or sign-up issue number\n\n{ref}"
    assert signup.removal_target(issue(body, 50, ("remove-feed",)), _profiles(tmp_path)).name == "web-42.yaml"


def test_remove_rejects_examples_and_unknown(tmp_path):
    d = _profiles(tmp_path)
    for ref, msg in (("example", "built-in"), ("99", "No feed")):
        with pytest.raises(signup.Rejected, match=msg):
            signup.removal_target(issue(f"### Your feed page or sign-up issue number\n\n{ref}", 50, ("remove-feed",)), d)


def test_remove_only_by_signup_author_or_maintainer(tmp_path):
    p = _profiles(tmp_path) / "web-42.yaml"
    assert signup.may_remove(issue("", login="alice"), p, "alice")
    assert not signup.may_remove(issue("", login="mallory"), p, "alice")
    assert signup.may_remove(issue("", login="owner", assoc="OWNER"), p, "alice")


class FakeGitHub:
    """Stands in for signup.GitHub: account dates, sign-up issues per user, issue authors."""

    def __init__(self, created=None, issues=None, authors=None):
        self.created = created or {}
        self.issues = issues or {}
        self.authors = authors or {}

    def user_created(self, login):
        return self.created.get(login, "2015-01-01T00:00:00Z")

    def signup_issue_numbers(self, login):
        return self.issues.get(login, [])

    def issue_author(self, n):
        return self.authors[n]


TODAY = dt.date(2026, 11, 14)


def _write(d, name, **prof):
    (d / f"{name}.yaml").write_text(yaml.safe_dump({"name": name, "description": DESC} | prof), encoding="utf-8")


def _handle(tmp_path, iss, gh=None):
    return signup.handle(iss, tmp_path, {}, gh or FakeGitHub(), lookup=NO_WINS, today=TODAY)


def test_handle_creates_a_loadable_profile_with_signup_issue_and_date(tmp_path):
    res = _handle(tmp_path, issue(form(desc=DESC)))
    assert res["action"] == "created" and res["number"] == 42 and f"/p/{res['slug']}.html" in res["comment"]
    prof = yaml.safe_load((tmp_path / f"{res['slug']}.yaml").read_text(encoding="utf-8"))
    assert prof["signup_issue"] == 42 and prof["created"] == "2026-11-14"
    assert "alice" not in (tmp_path / f"{res['slug']}.yaml").read_text(encoding="utf-8")  # no username stored
    assert match.Profile.load(tmp_path / f"{res['slug']}.yaml").created == "2026-11-14"


def test_limit_hard_cap_on_profiles(tmp_path, monkeypatch):
    monkeypatch.setattr(signup, "MAX_PROFILES", 2)
    _write(tmp_path, "a")
    _write(tmp_path, "b")
    res = _handle(tmp_path, issue(form(desc=DESC)))
    assert res["action"] == "rejected" and "full" in res["comment"] and len(list(tmp_path.glob("*.yaml"))) == 2


def test_limit_sign_ups_per_day(tmp_path):
    for i in range(signup.MAX_PER_DAY):
        _write(tmp_path, f"s{i}", signup_issue=100 + i, created="2026-11-14")
    _write(tmp_path, "yesterday", signup_issue=99, created="2026-11-13")
    res = _handle(tmp_path, issue(form(desc=DESC), number=200, login="new"))
    assert res["action"] == "rejected" and "daily limit" in res["comment"]
    (tmp_path / "s0.yaml").unlink()  # one fewer today: allowed again
    assert _handle(tmp_path, issue(form(desc=DESC), number=201, login="new"))["action"] == "created"


def test_limit_minimum_account_age(tmp_path):
    gh = FakeGitHub(created={"fresh": "2026-11-10T09:00:00Z", "week": "2026-11-07T09:00:00Z"})
    res = _handle(tmp_path, issue(form(desc=DESC), login="fresh"), gh)
    assert res["action"] == "rejected" and "7 days old" in res["comment"]
    assert _handle(tmp_path, issue(form(desc=DESC), login="week"), gh)["action"] == "created"


def test_limit_one_active_profile_per_user(tmp_path):
    _write(tmp_path, "web-12", signup_issue=12, created="2026-11-01")
    gh = FakeGitHub(issues={"alice": [12, 42], "bob": [43]})
    res = _handle(tmp_path, issue(form(desc=DESC), number=42, login="alice"), gh)
    assert res["action"] == "rejected" and "#12" in res["comment"]
    assert _handle(tmp_path, issue(form(desc=DESC), number=43, login="bob"), gh)["action"] == "created"
    (tmp_path / "web-12.yaml").unlink()  # alice removed her old feed: she may sign up again
    assert _handle(tmp_path, issue(form(desc=DESC), number=44, login="alice"), gh)["action"] == "created"


def test_limits_hold_across_a_burst_processed_in_one_sweep(tmp_path, monkeypatch):
    """The workflow processes all open requests in order, so each one sees the previous one's profile."""
    monkeypatch.setattr(signup, "MAX_PER_DAY", 3)
    gh = FakeGitHub(issues={"spam": [1, 2]})
    results = [
        _handle(tmp_path, issue(form(desc=DESC), number=n, login=u), gh)
        for n, u in [(1, "spam"), (2, "spam"), (3, "b"), (4, "c"), (5, "d")]
    ]
    assert [r["action"] for r in results] == ["created", "rejected", "created", "created", "rejected"]


def test_removal_by_stranger_refused_by_author_allowed(tmp_path):
    res = _handle(tmp_path, issue(form(desc=DESC)))
    gh = FakeGitHub(authors={42: "alice"})
    body = f"### Your feed page or sign-up issue number\n\n{res['slug']}"
    r = _handle(tmp_path, issue(body, 50, ("remove-feed",), login="mallory"), gh)
    assert r["action"] == "rejected" and (tmp_path / f"{res['slug']}.yaml").exists()
    r = _handle(tmp_path, issue(body, 51, ("remove-feed",), login="alice"), gh)
    assert r["action"] == "removed" and not (tmp_path / f"{res['slug']}.yaml").exists()


def test_unlabelled_issue_is_ignored(tmp_path):
    assert _handle(tmp_path, issue("hello", labels=()))["action"] == "ignored"


def test_issues_command_sweeps_open_requests(tmp_path, monkeypatch):
    monkeypatch.setattr(cli, "ROOT", tmp_path)
    (tmp_path / "profiles").mkdir()
    reqs = [issue(form(desc=DESC), number=7, login="a"), issue(form(desc=DESC), number=8, login="b")]
    fake = FakeGitHub()
    fake.open_requests = lambda: reqs
    monkeypatch.setattr(signup, "GitHub", lambda: fake)
    monkeypatch.setattr(signup.company, "search", lambda n, c: [])
    out = tmp_path / "r.json"
    cli.cmd_issues({}, types.SimpleNamespace(event=None, out=out))
    res = json.loads(out.read_text(encoding="utf-8"))
    assert [(r["number"], r["action"]) for r in res] == [(7, "created"), (8, "created")]


def test_github_client_paths():
    calls = []
    gh = signup.GitHub(get=lambda path: calls.append(path) or ([] if "issues?" in path else {"created_at": "x"}))
    gh.user_created("al ice")
    gh.signup_issue_numbers("alice")
    gh.open_requests()
    assert calls[0] == "users/al%20ice"
    assert calls[1] == "repos/{repo}/issues?creator=alice&labels=signup&state=all&per_page=100"
    assert {c.split("labels=")[1].split("&")[0] for c in calls[2:]} == {"signup", "remove-feed"}
