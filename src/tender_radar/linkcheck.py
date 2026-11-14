"""Check the published site for broken links: `python -m tender_radar.linkcheck URL`.

Crawls every HTML page under the start URL, checks every internal link and asset,
parses every RSS feed as XML, and checks external links once per distinct URL.
TED notice links are sampled (MAX_TED per run) to stay polite to TED; the
prefilled GitHub "new issue" links are checked once, as they only differ in query.
Exit code 1 if anything is broken.
"""

import random
import sys
import time
import urllib.error
import urllib.request
import xml.etree.ElementTree as ET
from html.parser import HTMLParser
from urllib.parse import urldefrag, urljoin, urlparse

MAX_TED = 15
UA = "tender-radar-linkcheck/1.0 (+https://github.com/Jenoyrex/tender-radar)"


class Links(HTMLParser):
    def __init__(self):
        super().__init__()
        self.links = []

    def handle_starttag(self, tag, attrs):
        for k, v in attrs:
            if k in ("href", "src") and v and not v.startswith(("mailto:", "javascript:", "data:")):
                self.links.append(v)


def fetch(url: str, method: str = "GET") -> tuple[int, bytes]:
    req = urllib.request.Request(url, method=method, headers={"User-Agent": UA})
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            return r.status, (r.read() if method == "GET" else b"")
    except urllib.error.HTTPError as e:
        return e.code, b""
    except (urllib.error.URLError, TimeoutError) as e:
        return 0, repr(e).encode()


def links_in(html: str, base: str) -> list[str]:
    p = Links()
    p.feed(html)
    return [urldefrag(urljoin(base, x))[0] for x in p.links]


def external_key(url: str) -> str:
    """Collapse URLs that only differ in their query to one check (GitHub prefilled issues)."""
    u = urlparse(url)
    return f"{u.scheme}://{u.netloc}{u.path}" if u.netloc == "github.com" and u.path.endswith("/issues/new") else url


def check(start: str, seed: int = 0) -> list[str]:
    start = start if start.endswith("/") else start + "/"
    errors, seen, queue, external = [], set(), [start], {}
    while queue:
        url = queue.pop()
        if url in seen:
            continue
        seen.add(url)
        status, body = fetch(url)
        if status != 200:
            errors.append(f"{status} {url}")
            continue
        if url.endswith(".xml"):
            try:
                ET.fromstring(body)
            except ET.ParseError as e:
                errors.append(f"bad XML {url}: {e}")
            continue
        if not (url.endswith((".html", "/"))):
            continue
        for link in links_in(body.decode("utf-8", "replace"), url):
            if link.startswith(start):
                queue.append(link)
            elif link.startswith("http"):
                external.setdefault(external_key(link), url)
    ted = [u for u in external if "ted.europa.eu/en/notice" in u]
    sample = set(random.Random(seed).sample(ted, min(MAX_TED, len(ted))))
    for link, page in external.items():
        if link in ted and link not in sample:
            continue
        status, _ = fetch(link)
        for wait in (2, 5, 10):  # transient network errors / bot refusals: retry politely
            if status not in (0, 403, 405, 429, 500, 502, 503):
                break
            time.sleep(wait)
            status, _ = fetch(link)
        if not 200 <= status < 400 and status != 429:
            errors.append(f"{status} {link} (linked from {page})")
        if "ted.europa.eu" in link:
            time.sleep(1)
    print(
        f"checked {len(seen)} site URLs, {len(external) - len(ted) + len(sample)} external "
        f"({len(sample)} of {len(ted)} TED notice links sampled): {len(errors)} broken"
    )
    return errors


if __name__ == "__main__":
    errs = check(sys.argv[1] if len(sys.argv) > 1 else "https://jenoyrex.github.io/tender-radar/")
    print("\n".join(errs))
    sys.exit(1 if errs else 0)
