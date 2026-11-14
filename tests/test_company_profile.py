import pytest
import yaml

from tender_radar import company, match


def award(nid, date, winners, title="Wartung GIS-System", country="DEU", cpv="72222300"):
    return {
        "publication-number": nid,
        "publication-date": f"{date}+01:00",
        "winner-name": {"deu": winners},
        "title-proc": {"deu": title},
        "description-proc": {"deu": "Pflege und Weiterentwicklung " * 30},
        "buyer-country": [country],
        "main-classification-proc": [cpv],
    }


NOTICES = [
    award("1-2026", "2026-01-05", ["Geo Daten GmbH"]),
    award("2-2026", "2026-03-01", ["GEO DATEN GMBH", "Other AG"], title="Geoportal Betrieb", country="AUT", cpv="72212000"),
    award("3-2026", "2026-02-01", ["Geo Daten Consulting GmbH"], title="not this company"),  # TED word match only
    award("4-2026", "2026-04-01", ["Somebody Else KG"]),
]


def test_own_wins_requires_normalised_name_equality_and_sorts_newest_first():
    wins = company.own_wins("Geo Daten GmbH", NOTICES)
    assert [n["publication-number"] for n in wins] == ["2-2026", "1-2026"]


def test_make_profile_is_loadable_by_the_matcher(tmp_path):
    prof = company.make_profile("Geo Daten", company.own_wins("Geo Daten", NOTICES))
    assert prof["countries"] == ["AUT", "DEU"]
    assert prof["cpv"] == ["7221", "7222"]  # most common first, ties in newest-win order
    assert "Geoportal Betrieb" in prof["description"] and "Wartung GIS-System" in prof["description"]
    assert "not this company" not in prof["description"]
    assert len(prof["description"].split("\n")[0]) <= len("Wartung GIS-System. ") + company.DESC_CHARS
    f = tmp_path / "geo.yaml"
    f.write_text(company.to_yaml(prof), encoding="utf-8")
    p = match.Profile.load(f)
    assert p.slug == "geo" and p.countries == ["AUT", "DEU"] and yaml.safe_load(f.read_text(encoding="utf-8"))


def test_make_profile_without_wins_raises():
    with pytest.raises(ValueError):
        company.make_profile("Nobody", [])


def test_profile_text_drops_duplicates_and_empties():
    assert company.profile_text(["a. x", "a. x", ". ", "b. y"]) == "a. x\nb. y"


def test_slugify():
    assert company.slugify("Esri Polska Sp. z o.o.") == "esri-polska"
    assert company.slugify("!!!") == "company"
