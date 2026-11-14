"""Self-serve sign-up and removal through GitHub issue forms (.github/ISSUE_TEMPLATE).

Run by .github/workflows/signup.yml as `tender-radar issue EVENT_JSON`. The issue
text is untrusted: it is parsed here in Python, validated, and only ever written
to YAML through yaml.safe_dump. Nothing is stored except what the person typed
into the public issue, plus the issue number (so only they can remove it later).
"""

import re
from pathlib import Path

import yaml

from . import company

SITE = "https://jenoyrex.github.io/tender-radar"
SIGNUP_LABEL, REMOVE_LABEL = "signup", "remove-feed"
MAX_PROFILES = 300  # ponytail: keeps the daily build well inside free Actions minutes; raise if it ever fills up

COUNTRIES = {  # TED buyer countries offered in the form: EU 27 + EEA + CH + UK
    "AUT": "Austria",
    "BEL": "Belgium",
    "BGR": "Bulgaria",
    "HRV": "Croatia",
    "CYP": "Cyprus",
    "CZE": "Czechia",
    "DNK": "Denmark",
    "EST": "Estonia",
    "FIN": "Finland",
    "FRA": "France",
    "DEU": "Germany",
    "GRC": "Greece",
    "HUN": "Hungary",
    "IRL": "Ireland",
    "ITA": "Italy",
    "LVA": "Latvia",
    "LTU": "Lithuania",
    "LUX": "Luxembourg",
    "MLT": "Malta",
    "NLD": "Netherlands",
    "POL": "Poland",
    "PRT": "Portugal",
    "ROU": "Romania",
    "SVK": "Slovakia",
    "SVN": "Slovenia",
    "ESP": "Spain",
    "SWE": "Sweden",
    "ISL": "Iceland",
    "LIE": "Liechtenstein",
    "NOR": "Norway",
    "CHE": "Switzerland",
    "GBR": "United Kingdom",
}
URL_RE = re.compile(r"https?://|www\.|\[url|<a\s", re.I)


class Rejected(ValueError):
    """Input we won't turn into a profile; the message is shown to the person."""


def parse_form(body: str) -> dict:
    """GitHub renders issue forms as '### Label\\n\\nvalue'. -> {label: value or ''}."""
    out = {}
    for block in re.split(r"^### ", body or "", flags=re.M)[1:]:
        label, _, value = block.partition("\n")
        value = value.strip()
        out[label.strip()] = "" if value == "_No response_" else value
    return out


def _money(s: str, field: str) -> float | None:
    s = re.sub(r"[\s,.'€]|eur", "", (s or "").lower())
    if not s:
        return None
    if not s.isdigit() or len(s) > 10:
        raise Rejected(f"{field} should be a whole number of euros, e.g. 50000.")
    return float(s)


def _countries(s: str) -> list[str]:
    codes = re.findall(r"\(([A-Z]{3})\)", s or "")
    if not codes and (s or "").strip():  # typed by hand: accept bare codes or names
        names = {v.lower(): k for k, v in COUNTRIES.items()}
        for part in re.split(r"[,;\n]+", s):
            part = part.strip()
            code = part.upper() if part.upper() in COUNTRIES else names.get(part.lower())
            if part and not code:
                raise Rejected(f"Unknown country {part[:40]!r}. Use the list in the form.")
            if code:
                codes.append(code)
    bad = [c for c in codes if c not in COUNTRIES]
    if bad:
        raise Rejected(f"Unknown country code {bad[0]!r}.")
    return sorted(set(codes))


def _clean_text(s: str, field: str, max_len: int) -> str:
    s = re.sub(r"\s+", " ", s or "").strip()
    if URL_RE.search(s):
        raise Rejected(f"Please remove links from '{field}': profiles are plain descriptions.")
    if len(s) > max_len:
        raise Rejected(f"'{field}' is too long ({len(s)} characters, max {max_len}).")
    return s


def profile_from_issue(issue: dict, profiles_dir: Path, cfg: dict, lookup=company) -> tuple[str, dict]:
    """(slug, profile dict) for a sign-up issue, or raise Rejected with a friendly reason."""
    f = parse_form(issue.get("body") or "")
    name = _clean_text(f.get("Company name", ""), "Company name", 120)
    desc = _clean_text(f.get("What does your business do?", ""), "What does your business do?", 1500)
    if desc and len(desc.split()) < 8:
        raise Rejected(
            "Please describe what you do in at least one full sentence (8+ words): "
            "the matcher compares these words with each tender."
        )
    if not name and not desc:
        raise Rejected("Please give a company name (we look up its past EU contract wins) or describe what you do.")
    countries = _countries(f.get("Countries", ""))
    lo, hi = (
        _money(f.get("Minimum contract value (EUR)", ""), "Minimum value"),
        _money(f.get("Maximum contract value (EUR)", ""), "Maximum value"),
    )
    if lo and hi and lo > hi:
        raise Rejected("The minimum value is larger than the maximum value.")
    excl = [
        w
        for w in (x.strip() for x in re.split(r"[,;\n]+", _clean_text(f.get("Words to exclude", ""), "Words to exclude", 300)))
        if w
    ][:20]
    if len(list(Path(profiles_dir).glob("*.yaml"))) >= MAX_PROFILES:
        raise Rejected("tender-radar is full right now (free hosting limits). Sorry; please try again later.")

    prof = {
        "name": name or " ".join(desc.split()[:8]) + "…",
        "description": desc,
        "countries": countries,
        "cpv": [],
        "exclude_keywords": excl,
    }
    if name:
        try:
            past = lookup.make_profile(name, lookup.own_wins(name, lookup.search(name, cfg)))
        except ValueError:
            if not desc:
                raise Rejected(
                    f"We found no EU (TED) IT-services contracts won by {name!r}. "
                    "Open a new sign-up and describe what you do instead."
                ) from None
        else:
            prof["description"] = (desc + "\n" + past["description"]).strip()
            prof["cpv"] = past["cpv"]
            prof["countries"] = countries or past["countries"]
            prof["name"] = f"{name} (+ {past['name'].split('(from ')[1].rstrip(')')})"
    if lo:
        prof["min_value_eur"] = lo
    if hi:
        prof["max_value_eur"] = hi
    prof["signup_issue"] = issue["number"]
    slug = f"{company.slugify(name or desc)[:30].strip('-')}-{issue['number']}"
    return slug, prof


def removal_target(issue: dict, profiles_dir: Path) -> Path:
    """The profile file a removal issue asks to delete. Raises Rejected if it can't be identified."""
    f = parse_form(issue.get("body") or "")
    ref = f.get("Your feed page or sign-up issue number", "").strip()
    m = re.search(r"/p/([a-z0-9-]+)\.(?:html|xml)", ref) or re.fullmatch(r"#?(\d+)", ref) or re.fullmatch(r"([a-z0-9-]+)", ref)
    if not m:
        raise Rejected("Please paste your feed page link (…/p/<name>.html) or your sign-up issue number.")
    key = m.group(1)
    for p in Path(profiles_dir).glob("*.yaml"):
        d = yaml.safe_load(p.read_text(encoding="utf-8")) or {}
        if p.stem == key or str(d.get("signup_issue")) == key:
            if not d.get("signup_issue"):
                raise Rejected("That is one of the built-in example profiles; it can't be removed this way.")
            return p
    raise Rejected(f"No feed found for {key!r}. It may already have been removed.")


def may_remove(issue: dict, profile: Path, signup_author: str | None) -> bool:
    """Only the person who signed up, or a repository maintainer, may remove a feed."""
    if issue.get("author_association") in ("OWNER", "MEMBER", "COLLABORATOR"):
        return True
    return bool(signup_author) and issue["user"]["login"] == signup_author


def signup_reply(slug: str, prof: dict) -> str:
    page, feed = f"{SITE}/p/{slug}.html", f"{SITE}/p/{slug}.xml"
    return (
        f"Your tender feed is ready.\n\n- Page: {page}\n- RSS feed: {feed}\n\n"
        f"It updates every morning with open EU (TED) IT-services tenders ranked for: *{prof['name']}*. "
        "The page can take a few minutes to appear after this comment.\n\n"
        f"To remove it, open a [removal request](https://github.com/Jenoyrex/tender-radar/issues/new?template=remove.yml) "
        f"with issue number {prof['signup_issue']}.\n\n"
        "Data: TED, © European Union. tender-radar is unofficial; always read the official notice."
    )
