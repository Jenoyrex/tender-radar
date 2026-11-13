"""Fetch notices from the TED Search API v3 (see docs/data-source.md)."""

import datetime as dt
import gzip
import hashlib
import json
import logging
import time
import urllib.error
import urllib.request
from pathlib import Path

URL = "https://api.ted.europa.eu/v3/notices/search"
PAGE_SIZE = 250  # API maximum
FIELDS = [
    "publication-number", "notice-type", "form-type", "notice-title", "title-proc",
    "description-proc", "description-lot", "buyer-name", "buyer-country",
    "classification-cpv", "publication-date", "deadline-receipt-tender-date-lot",
    "deadline-receipt-request-date-lot", "estimated-value-proc",
    "estimated-value-cur-proc", "estimated-value-lot", "estimated-value-cur-lot", "links",
    "main-classification-proc",
]
# Raw cache files are keyed by the field list, so adding a field re-fetches automatically.
CACHE_TAG = hashlib.sha1(" ".join(FIELDS).encode()).hexdigest()[:8]
log = logging.getLogger(__name__)


class TedError(RuntimeError):
    pass


def build_query(day: dt.date, cpv_prefixes: list[str], countries: list[str]) -> str:
    d = day.strftime("%Y%m%d")
    q = f"PD={d} AND form-type=competition"
    if cpv_prefixes:
        q += " AND (" + " OR ".join(f"classification-cpv={p}*" for p in cpv_prefixes) + ")"
    if countries:
        q += f" AND buyer-country IN ({' '.join(countries)})"
    return q


def _post(body: dict, user_agent: str, retries: int = 4) -> dict:
    data = json.dumps(body).encode()
    for attempt in range(retries):
        req = urllib.request.Request(
            URL, data=data,
            headers={"Content-Type": "application/json", "User-Agent": user_agent},
        )
        try:
            with urllib.request.urlopen(req, timeout=60) as r:
                return json.load(r)
        except urllib.error.HTTPError as e:
            msg = e.read().decode(errors="replace")[:300]
            if e.code < 500 and e.code != 429:  # our fault: retrying won't help
                raise TedError(f"HTTP {e.code}: {msg}") from e
            err = f"HTTP {e.code}"
        except (urllib.error.URLError, TimeoutError, json.JSONDecodeError) as e:
            err = repr(e)
        wait = 5 * 2**attempt
        log.warning("TED request failed (%s), retry in %ss", err, wait)
        time.sleep(wait)
    raise TedError(f"giving up after {retries} attempts: {err}")


def fetch_day(day: dt.date, cfg: dict) -> list[dict]:
    """All competition notices published on `day`. Empty list on empty days."""
    query = build_query(day, cfg["cpv_prefixes"], cfg["countries"])
    notices, page = [], 1
    while True:
        body = {"query": query, "fields": FIELDS, "limit": PAGE_SIZE, "page": page}
        res = _post(body, cfg["user_agent"])
        if res.get("timedOut"):
            raise TedError(f"search timed out for {day}")
        batch = res.get("notices") or []
        notices += batch
        total = res.get("totalNoticeCount") or 0
        if len(notices) >= total or not batch:
            break
        page += 1
        time.sleep(cfg["request_delay_seconds"])
    if len(notices) != total:
        raise TedError(f"{day}: got {len(notices)} notices, API reported {total}")
    return notices


def raw_path(raw_dir: Path, day: dt.date) -> Path:
    return Path(raw_dir) / f"{day.isoformat()}.{CACHE_TAG}.json.gz"


def collect(start: dt.date, end: dt.date, cfg: dict, refresh_days: int = 2) -> tuple[list[dt.date], list[dt.date]]:
    """Fetch each day in [start, end] into the raw cache.

    Days already cached are skipped, except the last `refresh_days` (TED may
    still be adding to them). Returns (fetched_days, failed_days); a failing
    day is logged and skipped so one bad day never loses the others.
    """
    raw_dir = Path(cfg["raw_dir"])
    raw_dir.mkdir(parents=True, exist_ok=True)
    fetched, failed = [], []
    day = start
    while day <= end:
        p = raw_path(raw_dir, day)
        if not p.exists() or (end - day).days < refresh_days:
            try:
                notices = fetch_day(day, cfg)
                with gzip.open(p, "wt", encoding="utf-8") as f:
                    json.dump(notices, f, ensure_ascii=False)
                log.info("%s: %d notices", day, len(notices))
                fetched.append(day)
            except TedError as e:
                log.error("%s: %s", day, e)
                failed.append(day)
            time.sleep(cfg["request_delay_seconds"])
        day += dt.timedelta(days=1)
    return fetched, failed


def load_raw(raw_dir: Path, day: dt.date) -> list[dict]:
    with gzip.open(raw_path(raw_dir, day), "rt", encoding="utf-8") as f:
        return json.load(f)
