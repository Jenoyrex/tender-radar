"""Self-serve sign-up and removal through GitHub issue forms (.github/ISSUE_TEMPLATE).

Run by .github/workflows/signup.yml as `tender-radar issue EVENT_JSON`. The issue
text is untrusted: it is parsed here in Python, validated, and only ever written
to YAML through yaml.safe_dump. Nothing is stored except what the person typed
into the public issue, plus the issue number (so only they can remove it later).
"""

import datetime as dt
import re
from pathlib import Path
from urllib.parse import quote

import yaml

from . import company, util

SITE = "https://jenoyrex.github.io/tender-radar"
SIGNUP_LABEL, REMOVE_LABEL = "signup", "remove-feed"
# Abuse limits (README "Sign-up limits"). They also keep the daily build well inside free Actions minutes.
MAX_PROFILES = 200  # hard cap on profiles, examples included
MAX_PER_DAY = 20  # new sign-ups per UTC day, all users together
MIN_ACCOUNT_DAYS = 7  # GitHub account age of the person signing up
# plus: at most 1 active feed per GitHub user (checked against their own sign-up issues)

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


def _profiles(profiles_dir: Path) -> list[dict]:
    return [yaml.safe_load(p.read_text(encoding="utf-8")) or {} for p in sorted(Path(profiles_dir).glob("*.yaml"))]


def check_limits(issue: dict, profiles_dir: Path, gh, today: dt.date) -> None:
    """Raise Rejected if this sign-up would break an abuse limit. `gh` answers two questions about
    the GitHub user (account creation date, numbers of their sign-up issues); nothing is stored."""
    profs = _profiles(profiles_dir)
    if len(profs) >= MAX_PROFILES:
        raise Rejected("tender-radar is full right now (free hosting limits). Sorry; please try again later.")
    if sum(str(p.get("created")) == today.isoformat() for p in profs) >= MAX_PER_DAY:
        raise Rejected(f"We already created {MAX_PER_DAY} feeds today, the daily limit. Please try again tomorrow.")
    login = issue["user"]["login"]
    created = dt.date.fromisoformat(gh.user_created(login)[:10])
    if (today - created).days < MIN_ACCOUNT_DAYS:
        raise Rejected(f"To limit spam, GitHub accounts must be at least {MIN_ACCOUNT_DAYS} days old to sign up.")
    active = {p.get("signup_issue") for p in profs if p.get("signup_issue")}
    mine = active & set(gh.signup_issue_numbers(login))
    if mine:
        raise Rejected(
            f"You already have an active feed (sign-up issue #{min(mine)}). Each GitHub account can have one; "
            "remove it first with a removal request if you want a new one."
        )


def handle(issue: dict, profiles_dir: Path, cfg: dict, gh, lookup=company, today: dt.date | None = None) -> dict:
    """Process one sign-up or removal issue. Returns {number, action, slug, comment}; action is
    created | removed | rejected | ignored. Changes profiles_dir on success."""
    today = today or dt.date.today()
    labels = {lb["name"] for lb in issue.get("labels", [])}
    res = {"number": issue["number"], "action": "ignored", "slug": "", "comment": ""}
    try:
        if SIGNUP_LABEL in labels:
            check_limits(issue, profiles_dir, gh, today)
            slug, prof = profile_from_issue(issue, profiles_dir, cfg, lookup)
            prof["created"] = today.isoformat()
            util.write_text(Path(profiles_dir) / f"{slug}.yaml", company.to_yaml(prof))
            res |= {"action": "created", "slug": slug, "comment": signup_reply(slug, prof)}
        elif REMOVE_LABEL in labels:
            path = removal_target(issue, profiles_dir)
            n = (yaml.safe_load(path.read_text(encoding="utf-8")) or {}).get("signup_issue")
            if not may_remove(issue, path, gh.issue_author(n) if n else None):
                raise Rejected(f"Only the person who opened sign-up issue #{n} can remove this feed.")
            path.unlink()
            res |= {
                "action": "removed",
                "slug": path.stem,
                "comment": f"Removed the feed `{path.stem}`. Its page disappears with the next site build (a few minutes).",
            }
    except Rejected as e:
        res |= {
            "action": "rejected",
            "comment": f"Sorry, I couldn't process this request: {e}\n\nYou're welcome to open a new issue with the form.",
        }
    return res


class GitHub:
    """The few GitHub REST calls sign-up needs (public data; GITHUB_TOKEN raises the rate limit)."""

    def __init__(self, get=None):
        from .feedback import github_api

        self.get = get or github_api

    def user_created(self, login: str) -> str:
        return self.get(f"users/{quote(login)}")["created_at"]

    def signup_issue_numbers(self, login: str) -> list[int]:
        q = f"issues?creator={quote(login)}&labels={SIGNUP_LABEL}&state=all&per_page=100"
        return [i["number"] for i in self.get("repos/{repo}/" + q) if "pull_request" not in i]

    def issue_author(self, n: int) -> str:
        return self.get(f"repos/{{repo}}/issues/{int(n)}")["user"]["login"]

    def open_requests(self) -> list[dict]:
        """Open sign-up and removal issues, oldest first (the workflow processes them all, in order)."""
        out = []
        for label in (SIGNUP_LABEL, REMOVE_LABEL):
            out += self.get(f"repos/{{repo}}/issues?labels={label}&state=open&per_page=100&sort=created&direction=asc")
        return sorted((i for i in out if "pull_request" not in i), key=lambda i: i["number"])
