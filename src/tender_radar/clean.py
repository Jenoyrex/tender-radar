"""Turn raw TED notices into tidy rows. Fails loudly on unexpected shapes."""

import re

# ponytail: static, rounded EUR rates (Nov 2026) for non-euro EU currencies.
# Only used for the value filter; the original value + currency are always kept.
# Upgrade path: fetch the ECB daily reference rates.
EUR_PER_UNIT = {
    "EUR": 1.0,
    "BGN": 0.511,
    "CZK": 0.040,
    "DKK": 0.134,
    "HUF": 0.0025,
    "PLN": 0.235,
    "RON": 0.197,
    "SEK": 0.091,
    "NOK": 0.085,
    "CHF": 1.06,
    "ISK": 0.0071,
    "GBP": 1.17,
}
COLUMNS = [
    "id",
    "title",
    "title_en",
    "description",
    "buyer",
    "country",
    "cpv",
    "value",
    "currency",
    "value_eur",
    "published",
    "deadline",
    "link",
    "notice_type",
    "main_cpv",
    "cpv_label",
    "title_english",
    "procedure_id",
]


class SchemaError(ValueError):
    """The API returned something we don't understand. Don't save it."""


def _expect(n, key, types):
    v = n.get(key)
    if not isinstance(v, types):
        raise SchemaError(f"{n.get('publication-number')}: field {key!r} is {type(v).__name__}, expected {types}")
    return v


def _first_lang(d, prefer="eng"):
    """TED multilingual dict {lang: str | [str]} -> one string."""
    if not d:
        return None
    if not isinstance(d, dict):
        raise SchemaError(f"expected language dict, got {type(d).__name__}")
    v = d.get(prefer) or next(iter(d.values()))
    if isinstance(v, list):
        v = " ".join(x for x in v if x)
    return v.strip() or None


def _date(s):
    """'2026-11-02+01:00' -> '2026-11-02'."""
    m = re.match(r"\d{4}-\d{2}-\d{2}", s or "")
    if not m:
        raise SchemaError(f"bad date {s!r}")
    return m.group(0)


def _value(n):
    v, cur = n.get("estimated-value-proc"), n.get("estimated-value-cur-proc")
    if v is None:  # fall back to summing lots, but only if all share one currency
        lots, curs = n.get("estimated-value-lot") or [], set(n.get("estimated-value-cur-lot") or [])
        if not lots or len(curs) != 1:
            return None, None
        v, cur = sum(float(x) for x in lots), curs.pop()
    try:
        v = float(v)
    except (TypeError, ValueError) as e:
        raise SchemaError(f"{n['publication-number']}: bad value {v!r}") from e
    return (v, cur) if v > 0 else (None, None)


def clean(n: dict) -> dict:
    nid = _expect(n, "publication-number", str)
    if not re.fullmatch(r"\d+-\d{4}", nid):
        raise SchemaError(f"bad publication-number {nid!r}")
    cpv = _expect(n, "classification-cpv", list)
    if not cpv or not all(re.fullmatch(r"\d{8}", c) for c in cpv):
        raise SchemaError(f"{nid}: bad CPV {cpv!r}")
    countries = _expect(n, "buyer-country", list)
    title_orig = _first_lang(_expect(n, "title-proc", dict))
    title_en = _first_lang(_expect(n, "notice-title", dict))
    # notice-title is "Country – CPV label – original title": only the label is really English.
    parts = (title_en or "").split(" – ", 2)
    main = (n.get("main-classification-proc") or [None])[0]
    if main is not None and not re.fullmatch(r"\d{8}", main):
        raise SchemaError(f"{nid}: bad main CPV {main!r}")
    eng = _first_lang({"eng": n["title-proc"]["eng"]}) if "eng" in n["title-proc"] else None
    desc = _first_lang(n.get("description-proc")) or _first_lang(n.get("description-lot"))
    deadlines = (n.get("deadline-receipt-tender-date-lot") or []) + (n.get("deadline-receipt-request-date-lot") or [])
    value, cur = _value(n)
    rate = EUR_PER_UNIT.get(cur) if cur else None
    return {
        "id": nid,
        "title": title_orig or title_en,
        "title_en": title_en,
        "description": (desc or "")[:4000],
        "buyer": _first_lang(n.get("buyer-name")),
        "country": countries[0] if countries else None,
        "cpv": " ".join(sorted(set(cpv))),
        "value": value,
        "currency": cur,
        "value_eur": round(value * rate) if value is not None and rate else None,
        "published": _date(_expect(n, "publication-date", str)),
        # Latest lot deadline: the tender is still worth showing while any lot is open.
        "deadline": max(_date(d) for d in deadlines) if deadlines else None,
        "link": f"https://ted.europa.eu/en/notice/-/detail/{nid}",
        "notice_type": n.get("notice-type"),
        "main_cpv": main,
        "cpv_label": parts[1] if len(parts) == 3 else None,
        "title_english": eng,  # genuine English title, only ~8% of notices
        "procedure_id": n.get("procedure-identifier"),  # shared with the award notice (eForms only)
    }


def clean_all(notices: list[dict]) -> list[dict]:
    """Clean and deduplicate on notice id (last one wins)."""
    return list({r["id"]: r for r in map(clean, notices)}.values())
