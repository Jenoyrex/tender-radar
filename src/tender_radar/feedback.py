"""Collect the 👍/👎 feedback issues (opened from the links on each profile page) into data/feedback.csv.

Issues are found by their title prefix, not the 'feedback' label: GitHub ignores the
`labels=` URL parameter for people without triage rights. Only the machine-readable
first body line is kept (verdict, profile, tender, score) plus the issue number and
date: no usernames or free text.
"""

import collections
import csv
import json
import os
import re
import urllib.request
from pathlib import Path

from . import util

COLUMNS = ["issue", "created", "verdict", "profile", "tender", "score"]
LINE = re.compile(
    r"feedback:\s*(relevant|not relevant)\s*\|\s*profile:\s*([\w-]+)\s*\|\s*tender:\s*(\d+-\d{4})"
    r"\s*\|\s*score:\s*([\d.]+)"
)


def github_get(path: str, repo: str | None = None):
    """GET from the GitHub REST API, authenticated when GITHUB_TOKEN is set."""
    repo = repo or os.environ.get("GITHUB_REPOSITORY", "Jenoyrex/tender-radar")
    req = urllib.request.Request(
        f"https://api.github.com/repos/{repo}/{path}",
        headers={"Accept": "application/vnd.github+json", "User-Agent": "tender-radar"},
    )
    if os.environ.get("GITHUB_TOKEN"):
        req.add_header("Authorization", f"Bearer {os.environ['GITHUB_TOKEN']}")
    with urllib.request.urlopen(req, timeout=30) as r:
        return json.load(r)


def parse(issue: dict) -> dict | None:
    """A feedback row from an issue, or None if it isn't a well-formed feedback issue."""
    if "pull_request" in issue or not (issue.get("title") or "").startswith("[feedback]"):
        return None
    m = LINE.search((issue.get("body") or "").split("\n", 1)[0])
    if not m:
        return None
    return {
        "issue": issue["number"],
        "created": issue["created_at"][:10],
        "verdict": m.group(1),
        "profile": m.group(2),
        "tender": m.group(3),
        "score": float(m.group(4)),
    }


def fetch_all(get=github_get) -> list[dict]:
    rows, page = [], 1
    while True:
        batch = get(f"issues?state=all&per_page=100&page={page}&sort=created&direction=asc")
        rows += [r for r in map(parse, batch) if r]
        if len(batch) < 100:
            return rows
        page += 1


def write(rows: list[dict], path: Path) -> None:
    with util.atomic_path(path) as tmp, open(tmp, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, COLUMNS, lineterminator="\n")
        w.writeheader()
        w.writerows(sorted(rows, key=lambda r: r["issue"]))


def report(rows: list[dict]) -> str:
    """Plain-text counts per profile; the last vote on a (profile, tender) pair wins."""
    latest = {(r["profile"], r["tender"]): r for r in sorted(rows, key=lambda r: r["issue"])}
    by = collections.defaultdict(collections.Counter)
    for r in latest.values():
        by[r["profile"]][r["verdict"]] += 1
    lines = [f"{len(rows)} feedback issues, {len(latest)} distinct (profile, tender) pairs"]
    for prof in sorted(by):
        c = by[prof]
        lines.append(f"  {prof}: {c['relevant']} relevant, {c['not relevant']} not relevant")
    return "\n".join(lines)
