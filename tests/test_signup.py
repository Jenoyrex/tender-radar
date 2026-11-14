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


def test_signup_rejected_when_full(tmp_path, monkeypatch):
    monkeypatch.setattr(signup, "MAX_PROFILES", 1)
    (tmp_path / "a.yaml").write_text("name: a", encoding="utf-8")
    with pytest.raises(signup.Rejected, match="full"):
        signup.profile_from_issue(issue(form(desc=DESC)), tmp_path, {}, lookup=NO_WINS)


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


def test_issue_command_end_to_end(tmp_path, monkeypatch):
    monkeypatch.setattr(cli, "ROOT", tmp_path)
    (tmp_path / "profiles").mkdir()
    ev, out = tmp_path / "event.json", tmp_path / "result.json"
    ev.write_text(json.dumps({"issue": issue(form(desc=DESC))}), encoding="utf-8")
    cli.cmd_issue({"cpv_prefixes": ["72"], "user_agent": "t"}, types.SimpleNamespace(event=ev, out=out))
    res = json.loads(out.read_text())
    assert res["action"] == "created" and (tmp_path / "profiles" / f"{res['slug']}.yaml").exists()
    assert f"/p/{res['slug']}.html" in res["comment"]
    # removal by a stranger is refused and keeps the file
    monkeypatch.setattr(cli, "_github", lambda path: {"user": {"login": "alice"}})
    ev.write_text(
        json.dumps(
            {
                "issue": issue(
                    f"### Your feed page or sign-up issue number\n\n{res['slug']}", 43, ("remove-feed",), login="mallory"
                )
            }
        ),
        encoding="utf-8",
    )
    cli.cmd_issue({}, types.SimpleNamespace(event=ev, out=out))
    assert json.loads(out.read_text())["action"] == "rejected"
    assert (tmp_path / "profiles" / f"{res['slug']}.yaml").exists()
    ev.write_text(
        json.dumps(
            {"issue": issue(f"### Your feed page or sign-up issue number\n\n{res['slug']}", 44, ("remove-feed",), login="alice")}
        ),
        encoding="utf-8",
    )
    cli.cmd_issue({}, types.SimpleNamespace(event=ev, out=out))
    assert json.loads(out.read_text())["action"] == "removed"
    assert not (tmp_path / "profiles" / f"{res['slug']}.yaml").exists()
