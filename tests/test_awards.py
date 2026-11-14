import pytest

from tender_radar.awards import clean_award, normalise_id, normalise_name, resolve


@pytest.mark.parametrize(
    "raw, want",
    [
        ("ACME Software GmbH", "acme software"),
        ("Acme Software GmbH & Co. KG", "acme software"),
        ("ACME SOFTWARE, S.L.", "acme software"),
        ("Acme Software S.L.U.", "acme software"),
        ("Acme Software B.V.", "acme software"),
        ("Esri Polska Sp. z o.o.", "esri polska"),
        ("Tekies s.r.o.", "tekies"),
        ("Tekies, spol. s r.o.", "tekies"),
        ("Arcmed Kft", "arcmed"),
        ("ZENIT Informatikai Korlátolt Felelősségű Társaság", "zenit informatikai"),
        ("Société Générale S.A.", "societe generale"),
        ("Tietoevry Oyj", "tietoevry"),
        ("Leadership Business Consulting, S.A.", "leadership business consulting"),
        ("Leadership Business Consulting S A", "leadership business consulting"),
        ("Cloudware Polska Sp.o.o.", "cloudware polska"),
        ("ARCDATA PRAHA, s r o", "arcdata praha"),
        ("Atea A/S", "atea"),
        ("Łukasiewicz Sp. z o.o.", "lukasiewicz"),
        ("ΔΕΛΤΑ ΑΕ", "δελτα"),
        ("Ltd", "ltd"),  # a bare legal form is left alone rather than emptied
        ("", ""),
    ],
)
def test_normalise_name(raw, want):
    assert normalise_name(raw) == want


def test_normalise_id():
    assert normalise_id("DE 123.456.789") == "DE123456789"
    assert normalise_id("b-12345678") == "B12345678"
    for junk in (None, "", "-", "n/a", "0000000", "1234"):
        assert normalise_id(junk) is None


def _award(**kw):
    n = {
        "publication-number": "1-2026",
        "publication-date": "2026-10-01+02:00",
        "procedure-identifier": "p1",
        "buyer-country": ["POL"],
        "notice-title": {"eng": "T"},
    }
    return n | kw


def test_clean_award_pairs_ids_only_when_counts_match():
    rows = clean_award(
        _award(
            **{
                "winner-name": {"pol": ["A Sp. z o.o.", "B S.A."]},
                "winner-identifier": ["6762499389", "5260250995"],
                "winner-country": ["POL", "POL"],
            }
        )
    )
    assert [(r["winner_norm"], r["winner_id"]) for r in rows] == [("a", "6762499389"), ("b", "5260250995")]
    # 1 name, 2 IDs (TED lists every tenderer's ID): keep the name, drop the ID
    rows = clean_award(
        _award(
            **{
                "winner-name": {"hun": ["Arcmed Kft"]},
                "winner-identifier": ["1111111", "2222222"],
                "winner-country": ["HUN", "HUN"],
            }
        )
    )
    assert [(r["winner_norm"], r["winner_id"], r["winner_country"]) for r in rows] == [("arcmed", None, "HUN")]


def test_clean_award_no_winner_and_bilingual():
    assert clean_award(_award()) == []
    rows = clean_award(
        _award(
            **{
                "winner-name": {"fra": ["Acme SA"], "eng": ["Acme SA"]},
                "winner-identifier": ["BE0123456789"],
                "winner-country": ["BEL"],
            }
        )
    )
    assert len(rows) == 1


def test_resolve_groups_by_id_and_by_name_within_country():
    w = lambda norm, wid, c="DEU": {"winner_norm": norm, "winner_id": wid, "winner_country": c}
    ents = resolve(
        [
            w("acme", "DE1"),  # 0
            w("acme software", "DE1"),  # same ID -> same company as 0
            w("acme", None),  # same name, same country -> 0
            w("acme", None, "AUT"),  # same name, other country -> different company
            w("other", "DE2"),  # different
            w("other", "DE3"),  # same name as 4 -> joined, even with a different ID
        ]
    )
    assert ents[0] == ents[1] == ents[2]
    assert len({ents[0], ents[3], ents[4]}) == 3
    assert ents[4] == ents[5]


def test_resolve_does_not_merge_different_firms_sharing_an_id():
    """TED often lists a consortium partner's or other tenderer's ID: same ID alone is not enough."""
    w = lambda norm, wid: {"winner_norm": norm, "winner_id": wid, "winner_country": "NLD"}  # noqa: E731
    ents = resolve(
        [
            w("atabix", "17084945"),
            w("visma circle", "17084945"),
            w("glintt global", "50354"),
            w("glintt global intelligent technologies", "50354"),
        ]
    )
    assert ents[0] != ents[1]
    assert ents[2] == ents[3]
