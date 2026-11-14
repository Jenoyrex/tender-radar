"""Contract award notices: who won what, and which wins belong to the same company.

Entity resolution is deliberately simple so every grouping can be explained:
two wins belong to the same company if they share a national ID (same winner
country), or the same normalised name in the same winner country.
"""

import re
import sqlite3
import unicodedata

from .clean import SchemaError, _date

WIN_COLUMNS = [
    "notice_id",
    "procedure_id",
    "prev_notice_id",
    "published",
    "decision_date",
    "buyer_country",
    "main_cpv",
    "title",
    "winner_name",
    "winner_norm",
    "winner_id",
    "winner_country",
    "winner_size",
    "value",
    "currency",
]

# Legal-form words, matched as whole tokens at the END of a normalised name
# (after dots are dropped and other punctuation becomes a space).
# ponytail: hand list for the EU's common forms; extend when a top-winner list shows misses.
LEGAL_SUFFIXES = sorted(
    [
        "gmbh",
        "mbh",
        "ag",
        "kg",
        "ohg",
        "ug",
        "ev",
        "se",
        "gmbh co kg",
        "ag co kg",
        "co kg",
        "sl",
        "slu",
        "sa",
        "sau",
        "sas",
        "sasu",
        "sarl",
        "eurl",
        "scs",
        "snc",
        "sca",
        "srl",
        "srls",
        "spa",
        "sapa",
        "scarl",
        "scrl",
        "bv",
        "nv",
        "vof",
        "cv",
        "bvba",
        "sprl",
        "srl",
        "cvba",
        "ltd",
        "limited",
        "plc",
        "llp",
        "lp",
        "llc",
        "inc",
        "corp",
        "co",
        "company",
        "sp z oo",
        "spz oo",
        "sp zoo",
        "sp k",
        "sp j",
        "spk",
        "sro",
        "spol sro",
        "s ro",
        "spol s ro",
        "vos",
        "ks",
        "αε",
        "επε",
        "ικε",
        "οε",
        "εε",
        "ад",
        "еад",
        "оод",
        "еоод",
        "kft",
        "zrt",
        "nyrt",
        "bt",
        "korlatolt felelossegu tarsasag",
        "zartkoruen mukodo reszvenytarsasag",
        "oy",
        "oyj",
        "ab",
        "publ",
        "aps",
        "a s",
        "asa",
        "hf",
        "ehf",
        "ou",
        "uab",
        "sia",
        "as",
        "doo",
        "dd",
        "ad",
        "ead",
        "eood",
        "ood",
        "lda",
        "unipessoal lda",
        "ike",
        "ae",
        "epe",
        "oe",
        "ee",
    ],
    key=lambda s: -len(s),
)  # longest first, so "gmbh co kg" wins over "kg"

_ID_JUNK = re.compile(r"[^0-9A-Z]")


def normalise_name(name: str) -> str:
    """'ACME Software GmbH & Co. KG' -> 'acme software'. Empty string if nothing is left."""
    s = unicodedata.normalize("NFKD", name or "")
    s = "".join(c for c in s if not unicodedata.combining(c)).lower()
    s = s.replace("ł", "l").replace("ø", "o").replace("ß", "ss").replace("đ", "d")
    s = s.replace(".", "")  # S.L. -> sl, s.r.o. -> sro, Sp. z o.o. -> sp z oo
    s = re.sub(r"[^\w]+|_", " ", s).strip()
    s = re.sub(r"\s+", " ", s)
    changed = True
    while changed:  # strip stacked forms: "... spol sro" / "... gmbh co kg"
        changed = False
        for suf in LEGAL_SUFFIXES:
            if s.endswith(" " + suf):
                s, changed = s[: -len(suf) - 1].strip(), True
                break
    return s


def normalise_id(raw: str | None) -> str | None:
    """National ID -> uppercase alphanumerics. None for placeholders like '-', 'n/a', '0000000'."""
    s = _ID_JUNK.sub("", (raw or "").upper())
    if len(s) < 5 or len(set(s)) == 1 or s in {"NONE", "NULL", "NOTAPPLICABLE", "NA"}:
        return None
    return s


def _names(d) -> list[str]:
    """Winner names in one language. TED sometimes gives the same names in 2 languages."""
    if not d:
        return []
    if not isinstance(d, dict):
        raise SchemaError(f"expected language dict for winner-name, got {type(d).__name__}")
    v = d.get("eng") or max(d.values(), key=len)
    return [x.strip() for x in (v if isinstance(v, list) else [v]) if x and x.strip()]


def clean_award(n: dict) -> list[dict]:
    """One row per distinct winner of an award notice; [] if no winner is named."""
    nid = n["publication-number"]
    names = _names(n.get("winner-name"))
    ids = n.get("winner-identifier") or []
    countries = n.get("winner-country") or []
    sizes = n.get("winner-size") or []
    # winner-identifier/-country are per tenderer and only line up with names when the
    # counts match; otherwise keep the name and drop the ID rather than guess a pairing.
    aligned = len(ids) == len(names)
    title = n.get("title-proc") or n.get("notice-title") or {}
    title = (title.get("eng") or next(iter(title.values()), "")) if isinstance(title, dict) else ""
    rows = {}
    for i, name in enumerate(names):
        norm = normalise_name(name)
        if not norm:
            continue
        row = {
            "notice_id": nid,
            "procedure_id": n.get("procedure-identifier"),
            "prev_notice_id": (n.get("previous-notice-id-proc") or [None])[0],
            "published": _date(n["publication-date"]),
            "decision_date": _date(n["winner-decision-date"][0]) if n.get("winner-decision-date") else None,
            "buyer_country": (n.get("buyer-country") or [None])[0],
            "main_cpv": (n.get("main-classification-proc") or [None])[0],
            "title": title if isinstance(title, str) else " ".join(title),
            "winner_name": name,
            "winner_norm": norm,
            "winner_id": normalise_id(ids[i]) if aligned else None,
            "winner_country": countries[i]
            if aligned and i < len(countries)
            else (countries[0] if len(set(countries)) == 1 else None),
            "winner_size": sizes[i] if len(sizes) == len(names) else None,
            "value": float(n["result-value-notice"]) if n.get("result-value-notice") else None,
            "currency": n.get("result-value-cur-notice"),
        }
        rows.setdefault((norm, row["winner_id"]), row)  # same winner twice (several lots) = one win
    return list(rows.values())


def resolve(wins: list[dict]) -> list[int]:
    """Entity number for each win (union-find over shared national IDs and shared names)."""
    parent = {}

    def find(x):
        parent.setdefault(x, x)
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x

    keys = []
    for w in wins:
        name_key = ("name", w["winner_country"], w["winner_norm"])
        find(name_key)
        if w["winner_id"]:
            parent[find(name_key)] = find(("id", w["winner_country"], w["winner_id"]))
        keys.append(name_key)
    roots, out = {}, []
    for k in keys:
        out.append(roots.setdefault(find(k), len(roots)))
    return out


SCHEMA = f"""
CREATE TABLE IF NOT EXISTS wins ({", ".join(c + (" REAL" if c == "value" else " TEXT") for c in WIN_COLUMNS)},
    entity INTEGER, PRIMARY KEY (notice_id, winner_norm, winner_id));
CREATE INDEX IF NOT EXISTS ix_wins_entity ON wins(entity);
CREATE INDEX IF NOT EXISTS ix_wins_proc ON wins(procedure_id);
"""


def report(con: sqlite3.Connection, n_notices: int) -> str:
    """Markdown summary of coverage and entity resolution."""
    q = lambda sql: con.execute(sql).fetchone()[0]
    with_winner = q("SELECT count(DISTINCT notice_id) FROM wins")
    linked = q("""SELECT count(DISTINCT w.notice_id) FROM wins w
                  WHERE EXISTS (SELECT 1 FROM tenders t WHERE t.procedure_id = w.procedure_id)""")
    prev = q("SELECT count(DISTINCT notice_id) FROM wins WHERE prev_notice_id IS NOT NULL")
    prev_found = q("""SELECT count(DISTINCT w.notice_id) FROM wins w JOIN tenders t ON t.id = w.prev_notice_id""")
    either = q("""SELECT count(DISTINCT w.notice_id) FROM wins w WHERE
                  EXISTS (SELECT 1 FROM tenders t WHERE t.procedure_id = w.procedure_id OR t.id = w.prev_notice_id)""")
    per_entity = """SELECT entity, count(DISTINCT coalesce(procedure_id, notice_id)) n FROM wins GROUP BY entity"""
    ents = q("SELECT count(DISTINCT entity) FROM wins")
    names = q("SELECT count(DISTINCT winner_country || '|' || winner_name) FROM wins")
    norms = q("SELECT count(DISTINCT winner_country || '|' || winner_norm) FROM wins")
    four = q(f"SELECT count(*) FROM ({per_entity}) WHERE n >= 4")
    four_linked = q("""SELECT count(*) FROM (SELECT entity, count(DISTINCT w.procedure_id) n FROM wins w
                        WHERE EXISTS (SELECT 1 FROM tenders t WHERE t.procedure_id = w.procedure_id)
                        GROUP BY entity) WHERE n >= 4""")
    with_id = q("SELECT count(*) FROM wins WHERE winner_id IS NOT NULL")
    n_wins = q("SELECT count(*) FROM wins")
    pct = lambda a, b: f"{a:,} ({100 * a / b:.0f}%)" if b else "0"
    out = [
        "| | |",
        "|---|---|",
        f"| Award notices (CPV 72) | {n_notices:,} |",
        f"| … naming at least one winner | {pct(with_winner, n_notices)} |",
        f"| … linked to their contract notice via `procedure-identifier` | {pct(linked, with_winner)} |",
        f"| … carrying `previous-notice-id-proc` | {pct(prev, with_winner)} (found in our history: {prev_found:,}) |",
        f"| … linked by either route | {pct(either, with_winner)} |",
        f"| (notice, winner) rows | {n_wins:,}, {pct(with_id, n_wins)} with a usable national ID |",
        f"| Distinct raw winner names (per country) | {names:,} |",
        f"| … after name normalisation | {norms:,} |",
        f"| … after also grouping by national ID = **companies** | **{ents:,}** |",
        f"| Companies with 4+ wins (distinct procedures) | **{four:,}** |",
        f"| … with 4+ wins linked to a contract notice (usable for the backtest) | **{four_linked:,}** |",
        "",
        "Top 15 companies by wins:",
        "",
        "| Wins | Country | Name variants (most common first) |",
        "|---|---|---|",
    ]
    for ent, n in con.execute(f"{per_entity} ORDER BY n DESC LIMIT 15").fetchall():
        rows = con.execute(
            """SELECT winner_name, winner_country, count(*) c FROM wins WHERE entity = ?
                              GROUP BY winner_name ORDER BY c DESC""",
            (ent,),
        ).fetchall()
        variants = "; ".join(r[0] for r in rows[:3]) + (f" (+{len(rows) - 3} more)" if len(rows) > 3 else "")
        out.append(f"| {n} | {rows[0][1]} | {variants} |")
    return "\n".join(out) + "\n"


def store(con: sqlite3.Connection, wins: list[dict]) -> None:
    """Replace the wins table with `wins`, entity numbers included."""
    for w, e in zip(wins, resolve(wins), strict=True):
        w["entity"] = e
    with con:
        con.execute("DROP TABLE IF EXISTS wins")
        con.executescript(SCHEMA)
        cols = WIN_COLUMNS + ["entity"]
        con.executemany(f"INSERT OR REPLACE INTO wins ({', '.join(cols)}) VALUES ({', '.join(':' + c for c in cols)})", wins)
