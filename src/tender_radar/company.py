"""Profile from company name: find a company's past TED wins and turn them into a profile.

The profile text is the titles + start of the descriptions of its past wins: the
same text the award backtest (docs/evaluation.md) uses to build a company profile.
"""

import collections
import re

import yaml

from . import ted
from .awards import _names, normalise_name

DESC_CHARS = 300  # per win; long descriptions would drown the titles
MAX_WINS = 40


def _first(d) -> str:
    if not isinstance(d, dict) or not d:
        return ""
    v = d.get("eng") or next(iter(d.values()))
    return " ".join(v) if isinstance(v, list) else (v or "")


def win_text(n: dict) -> str:
    """One past win as text: title + start of description (raw TED award notice)."""
    return f"{_first(n.get('title-proc'))}. {_first(n.get('description-proc'))[:DESC_CHARS]}".strip()


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


def make_profile(name: str, wins: list[dict]) -> dict:
    """Profile dict (same keys as profiles/*.yaml). Raises ValueError if there are no wins."""
    if not wins:
        raise ValueError(f"no CPV-matching TED award notices won by {name!r}")
    countries = collections.Counter(c for n in wins for c in (n.get("buyer-country") or [])[:1])
    cpvs = collections.Counter(c[:4] for n in wins for c in (n.get("main-classification-proc") or [])[:1])
    return {
        "name": f"{name} (from {len(wins)} past TED wins)",
        "description": profile_text([win_text(n) for n in wins]),
        "countries": sorted(countries),
        "cpv": [c for c, _ in cpvs.most_common(4)],
        "exclude_keywords": [],
    }


def to_yaml(profile: dict) -> str:
    return yaml.safe_dump(profile, allow_unicode=True, sort_keys=False, width=100)
