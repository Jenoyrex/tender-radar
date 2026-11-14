"""Profile from company name: find a company's past TED wins and turn them into a profile.

The profile text is the titles + start of the descriptions of its past wins: the
same text the award backtest (docs/evaluation.md) uses to build a company profile.
"""

import collections
import re

import yaml

from . import ted
from .awards import DESC_CHARS, _names, normalise_name, win_text  # noqa: F401  (DESC_CHARS re-exported)

MAX_WINS = 40


def profile_text(texts: list[str]) -> str:
    """Join win texts, dropping exact duplicates (multi-lot re-publications)."""
    return "\n".join(dict.fromkeys(t for t in texts if t.strip(". ")))


def search(name: str, cfg: dict) -> list[dict]:
    """Award notices whose winner-name matches `name` (TED word search), CPV filter from config."""
    words = re.sub(r'["\\]', " ", name).strip()
    q = f'winner-name="{words}" AND form-type=result'
    if cfg["cpv_prefixes"]:
        q += " AND (" + " OR ".join(f"classification-cpv={p}*" for p in cfg["cpv_prefixes"]) + ")"
    body = {"query": q, "fields": ted.AWARD_FIELDS, "limit": 250, "page": 1}
    return ted._post(body, cfg["user_agent"]).get("notices") or []


def own_wins(name: str, notices: list[dict]) -> list[dict]:
    """Keep notices where one of the winners IS the company (normalised name equality),
    not merely contains the words (TED's search matches 'Tekies' in 'Tekies Consulting')."""
    target = normalise_name(name)
    out = [n for n in notices if target and any(normalise_name(w) == target for w in _names(n.get("winner-name")))]
    return sorted(out, key=lambda n: n["publication-date"], reverse=True)[:MAX_WINS]


def slugify(s: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", normalise_name(s)).strip("-")[:40] or "company"


def profile_from_rows(name: str, rows: list[dict]) -> dict:
    """Profile dict (same keys as profiles/*.yaml) from win rows {text, buyer_country, main_cpv},
    newest first. Shared by `profile-from-company` and the award backtest."""
    if not rows:
        raise ValueError(f"no CPV-matching TED award notices won by {name!r}")
    rows = rows[:MAX_WINS]
    cpvs = collections.Counter((r["main_cpv"] or "")[:4] for r in rows if r["main_cpv"])
    return {
        "name": f"{name} (from {len(rows)} past TED wins)",
        "description": profile_text([r["text"] for r in rows]),
        "countries": sorted({r["buyer_country"] for r in rows if r["buyer_country"]}),
        "cpv": [c for c, _ in cpvs.most_common(4)],
        "exclude_keywords": [],
    }


def make_profile(name: str, wins: list[dict]) -> dict:
    """Profile dict from raw TED award notices (newest first). Raises ValueError if there are none."""
    rows = [
        {
            "text": win_text(n),
            "buyer_country": (n.get("buyer-country") or [None])[0],
            "main_cpv": (n.get("main-classification-proc") or [None])[0],
        }
        for n in wins
    ]
    return profile_from_rows(name, rows)


def to_yaml(profile: dict) -> str:
    return yaml.safe_dump(profile, allow_unicode=True, sort_keys=False, width=100)
