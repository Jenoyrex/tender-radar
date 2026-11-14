import http.client
import io
import json

from tender_radar import ted


def test_post_retries_a_truncated_response(monkeypatch):
    """TED sometimes cuts a chunked response short (IncompleteRead); that must be retried, not crash the run."""
    calls = []

    def urlopen(req, timeout):
        calls.append(1)
        if len(calls) == 1:
            raise http.client.IncompleteRead(b"partial")
        return io.BytesIO(json.dumps({"notices": [], "totalNoticeCount": 0}).encode())

    monkeypatch.setattr(ted.urllib.request, "urlopen", urlopen)
    monkeypatch.setattr(ted.time, "sleep", lambda s: None)
    assert ted._post({"query": "x"}, "ua") == {"notices": [], "totalNoticeCount": 0}
    assert len(calls) == 2


def test_build_query_kinds():
    import datetime as dt

    q = ted.build_query(dt.date(2026, 1, 2), ["72"], [], kind="result")
    assert q == "PD=20260102 AND form-type=result AND (classification-cpv=72*)"
