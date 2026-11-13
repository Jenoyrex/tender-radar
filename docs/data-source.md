# Data source: TED Search API v3

Verified by hand with real requests on 2026-11-13. Where this differs from the
original project brief, this file wins.

## Endpoint

```
POST https://api.ted.europa.eu/v3/notices/search
Content-Type: application/json
```

- **No API key needed** for search (confirmed: anonymous requests return 200).
- Served through CloudFront + AWS WAF. No rate-limit headers are returned, and a
  burst of 12 back-to-back requests was not throttled. The official docs do not
  publish a number, so we stay polite anyway: one request at a time, 1.5 s
  between requests, a descriptive `User-Agent`, and raw responses cached on disk.
- Typical latency: 0.6–3.5 s per request (250 notices ≈ 3 s).

## Request body

```json
{
  "query": "classification-cpv=72* AND PD>=20260914 AND PD<=20261113 AND form-type=competition",
  "fields": ["publication-number", "notice-title", "..."],
  "limit": 250,
  "page": 1
}
```

| Parameter | Verified behaviour |
|---|---|
| `query` | TED "expert search" syntax. `AND`, `IN (a b c)`, `field=value`, wildcard `72*`, `FT~"word"` (full text), `PD>=YYYYMMDD`, `SORT BY field DESC` all work. The brief's example `FT~"software" AND PD>=20260101 AND buyer-country=DEU` is valid. |
| `fields` | **Required.** Unknown names → HTTP 400 whose message lists all ~1,830 supported field names (handy for discovery). |
| `limit` | Max **250** per page (251 → 400 `SEARCH_EXCEEDS_MAX_LIMIT`). |
| `page` | 1-based. `page × limit` must be ≤ **15,000** (else 400 `SEARCH_WINDOW_TOO_WIDE`). |
| `paginationMode` | `"ITERATION"` returns `iterationNextToken` for result sets beyond 15,000. Not needed here: a 60-day CPV-72 window is ~5,400 competition notices. |
| `scope` | `ALL` (default), `ACTIVE` (≈ still-open notices), `LATEST` (latest version only). We use the default and filter deadlines ourselves, so the logic is visible. |

Response: `{"notices": [...], "totalNoticeCount": int, "iterationNextToken": str|null, "timedOut": bool}`.
A day with no publications (e.g. Sunday `PD=20261108`) returns `totalNoticeCount: 0` and an empty list, not an error.

## Fields we use and their real shapes

| Field | Shape (example) | Notes |
|---|---|---|
| `publication-number` | `"756453-2026"` | Unique notice id. Our primary key. |
| `notice-type` | `"cn-standard"` | Also `can-standard` (award), `pin-*`, `veat`, … |
| `form-type` | `"competition"` | Filter on this: `competition` = open calls for tender (mostly `cn-standard`, some `cn-social`, `pin-cfc-standard`). About half of all CPV-72 notices are awards (`result`), useless to a bidder. |
| `notice-title` | `{"eng": "Sweden – Information systems … services – Omvärldsanalys IT", "deu": …}` | Always in all 24 EU languages, built as *country – CPV label – original title*. **Contains the CPV label**, so it must be hidden from the matcher during evaluation. |
| `title-proc` | `{"swe": "Omvärldsanalys IT"}` | Original language only. |
| `description-proc` | `{"swe": "Detta ramavtal …"}` | Original language only (Czech, German, Spanish, Polish most common; English ~5%). |
| `buyer-name` | `{"swe": ["Liseberg AB"]}` | Dict of language → list. |
| `buyer-country` | `["SWE"]` | ISO 3166-1 alpha-3, list. |
| `classification-cpv` | `["72222000", "72222000"]` | 8-digit codes, list with duplicates (main + additional, per lot). |
| `publication-date` | `"2026-11-02+01:00"` | Date with UTC offset. |
| `deadline-receipt-tender-date-lot` | `["2026-12-12+01:00"]` | Per lot; missing on ~1/4 of competition notices (some use `deadline-receipt-request-date-lot` for two-stage procedures). |
| `estimated-value-proc` / `-cur-proc` | `"13000000"` / `"SEK"` | Strings. Missing on roughly half the notices. Falls back to the sum of `estimated-value-lot`. Never invented. |
| `links.html.ENG` | `https://ted.europa.eu/en/notice/-/detail/756453-2026` | Human-readable notice page. |

Field names from the brief that do **not** exist: `deadline-receipt-tender-date-proc`. `estimated-value-glo` exists but was empty in every sample.

## Implications for the design

1. **Multilingual text.** Only the title is translated; descriptions are in the
   buyer's language. A monolingual English TF-IDF model is blind to ~95% of
   descriptions. This is the main argument for a *multilingual* embedding model.
2. **CPV leaks into `notice-title`.** For evaluation the matcher sees only
   `title-proc` + `description-proc`.
3. **Volume.** CPV 72, all EU, 60 days: ~10,200 notices, ~5,400 of them
   `form-type=competition` → 22 pages of 250 → a full backfill takes about a minute.

## Licence and attribution

TED content may be reused with attribution (Commission Decision 2011/833/EU on
reuse of Commission documents). Attribution used on every page:
"Source: TED – Tenders Electronic Daily, © European Union, Publications Office of the EU."
This project is not affiliated with the EU.
