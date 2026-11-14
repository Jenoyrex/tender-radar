import functools
import threading
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer

from tender_radar import linkcheck


def serve(root):
    handler = functools.partial(SimpleHTTPRequestHandler, directory=str(root))
    handler.log_message = lambda *a: None
    srv = ThreadingHTTPServer(("127.0.0.1", 0), handler)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    return srv, f"http://127.0.0.1:{srv.server_address[1]}/"


def test_finds_broken_internal_link_and_bad_feed(tmp_path):
    (tmp_path / "p").mkdir()
    (tmp_path / "index.html").write_text(
        '<a href="p/a.html">a</a> <a href="p/missing.html">x</a> <a href="#top">t</a>', encoding="utf-8"
    )
    (tmp_path / "p" / "a.html").write_text(
        '<a href="../index.html">home</a> <a href="a.xml">rss</a> <a href="b.xml">rss</a>', encoding="utf-8"
    )
    (tmp_path / "p" / "a.xml").write_text("<rss><channel></channel></rss>", encoding="utf-8")
    (tmp_path / "p" / "b.xml").write_text("<rss><channel>", encoding="utf-8")  # truncated feed
    srv, url = serve(tmp_path)
    try:
        errors = linkcheck.check(url)
    finally:
        srv.shutdown()
    assert len(errors) == 2
    assert any(e.startswith("404 ") and e.endswith("p/missing.html") for e in errors)
    assert any(e.startswith("bad XML ") and "b.xml" in e for e in errors)


def test_clean_site_passes(tmp_path):
    (tmp_path / "index.html").write_text('<a href="index.html">self</a>', encoding="utf-8")
    srv, url = serve(tmp_path)
    try:
        assert linkcheck.check(url) == []
    finally:
        srv.shutdown()


def test_prefilled_github_issue_links_are_checked_once():
    a = "https://github.com/o/r/issues/new?title=a&body=1"
    b = "https://github.com/o/r/issues/new?title=b&body=2"
    assert linkcheck.external_key(a) == linkcheck.external_key(b) == "https://github.com/o/r/issues/new"
    assert linkcheck.external_key("https://ted.europa.eu/x?a=1") == "https://ted.europa.eu/x?a=1"
