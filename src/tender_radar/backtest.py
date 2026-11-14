"""Award-notice backtest: would tender-radar have shown a company the tender it went on to win?

For each company (entity from awards.resolve) with enough wins:
- held-out = its latest win that links (procedure-identifier) to a contract notice we have;
- d = first publication date of that contract notice;
- profile = built exactly like `profile-from-company` (company.profile_from_rows) from the
  company's other wins published before d (no peeking at the future, never the same procedure);
- pool = contract notices open on d (published <= d, deadline >= d; no deadline: open for
  60 days), latest version per (buyer, title), then the product's filters for that profile
  (countries of its past wins). A held-out tender filtered out counts as a miss.
- rank of the held-out tender in each matcher's ranking (ties: expected rank).
Companies are split 50/50 into dev and test; the matcher is chosen on dev, reported on test.
"""

import collections
import datetime as dt
import random
import sqlite3
from dataclasses import dataclass
from pathlib import Path

import numpy as np

from . import build, company, db, match

MIN_WINS = 4  # distinct procedures won, as the brief asks
MIN_TRAIN = 3  # wins left for the profile after removing the held-out and anything later
NO_DEADLINE_OPEN_DAYS = 60
BLEND_WEIGHTS = (0.25, 0.5, 0.75)
CURRENT = "char-tfidf + CPV boost (shipped)"


@dataclass
class Case:
    entity: int
    name: str
    held: dict  # win row
    date: str  # d
    train: list  # win rows, newest first


def make_cases(tenders: list[dict], wins: list[dict], min_wins: int = MIN_WINS) -> tuple[list[Case], collections.Counter]:
    """Backtest cases plus a funnel counter explaining where companies dropped out."""
    first_pub = {}
    for t in tenders:
        if t["procedure_id"]:
            first_pub[t["procedure_id"]] = min(first_pub.get(t["procedure_id"], t["published"]), t["published"])
    by_ent = collections.defaultdict(list)
    for w in wins:
        by_ent[w["entity"]].append(w)
    funnel, cases = collections.Counter(), []
    for ent, ws in sorted(by_ent.items()):
        if len({w["procedure_id"] or w["notice_id"] for w in ws}) < min_wins:
            continue
        funnel[f"companies with {min_wins}+ wins"] += 1
        linked = [w for w in ws if w["procedure_id"] in first_pub]
        if not linked:
            funnel["dropped: no win links to a contract notice"] += 1
            continue
        held = max(linked, key=lambda w: (w["published"], w["notice_id"]))
        d = first_pub[held["procedure_id"]]
        train, seen = [], set()
        for w in sorted(ws, key=lambda w: (w["published"], w["notice_id"]), reverse=True):
            key = w["procedure_id"] or w["notice_id"]
            if w["published"] < d and w["procedure_id"] != held["procedure_id"] and key not in seen:
                seen.add(key)
                train.append(w)
        if len(train) < MIN_TRAIN:
            funnel[f"dropped: fewer than {MIN_TRAIN} wins published before the held-out tender"] += 1
            continue
        funnel["usable cases"] += 1
        name = collections.Counter(w["winner_name"] for w in ws).most_common(1)[0][0]
        cases.append(Case(ent, name, held, d, train))
    return cases, funnel


VARIANTS = {
    "default": "profile from all earlier wins; pool = notices open in the countries of those wins",
    "europe": "same profile, but no country filter: the pool is every open CPV-72 notice in Europe",
    "one-win": "profile from the single most recent earlier win only (cold start); pool as default",
}


def case_profile(c: Case, variant: str = "default") -> match.Profile:
    prof = company.profile_from_rows(c.name, c.train[:1] if variant == "one-win" else c.train)
    if variant == "europe":
        prof["countries"] = []
    return match.Profile(slug=str(c.entity), **prof)


def same_buyer(a: str | None, b: str | None) -> bool:
    """Buyer names are free text; compare them with the winner-name normaliser."""
    from .awards import normalise_name

    return bool(a and b) and normalise_name(a) == normalise_name(b)


def pool(tenders: list[dict], d: str, p: match.Profile) -> list[dict]:
    day = dt.date.fromisoformat(d)
    oldest_undated = (day - dt.timedelta(days=NO_DEADLINE_OPEN_DAYS)).isoformat()
    open_ = [
        t for t in tenders if t["published"] <= d and (t["deadline"] >= d if t["deadline"] else t["published"] >= oldest_undated)
    ]
    return [t for t in build.latest_versions(open_) if match.passes_filters(t, p, day)]


def pool_members(tenders: list[dict], wins: list[dict], min_wins: int = MIN_WINS) -> list[dict]:
    """Every notice that appears in some case's pool: the only ones the e5 matcher needs embedded."""
    cases, _ = make_cases(tenders, wins, min_wins)
    ids = set()
    for c in cases:
        ids |= {t["id"] for t in pool(tenders, c.date, case_profile(c))}
    return [t for t in tenders if t["id"] in ids]


def z(x: np.ndarray) -> np.ndarray:
    return (x - x.mean()) / (x.std() or 1)


def scores(c: Case, p: match.Profile, cands: list[dict], labels: dict, e5_vecs: dict | None, e5_query=None, train=None) -> dict:
    """{matcher: score array over cands}. `train`: the wins the profile was built from (default all)."""
    train = c.train if train is None else train
    char = match.tfidf_similarity(p.description, [match.tender_text(t) for t in cands])
    cpv = np.array([bool(match.cpv_hits(t, p.cpv)) for t in cands], dtype=float)
    english_q = company.profile_text([w["title_en"] or "" for w in train])
    out = {
        "char-tfidf": char,
        CURRENT: char + match.CPV_BOOST * cpv,
        "english-tfidf": match.tfidf_similarity(english_q, [match.english_text(t, labels) for t in cands], analyzer="word"),
        "same-main-cpv": np.array([sum(w["main_cpv"] == t["main_cpv"] for w in train) for t in cands], dtype=float),
        "random": np.random.default_rng(c.entity).random(len(cands)),
    }
    if e5_vecs is not None:
        e5 = np.stack([e5_vecs[t["id"]] for t in cands]) @ e5_query(p.description)
        out["e5"] = e5
        for w in BLEND_WEIGHTS:
            out[f"blend w={w}"] = w * z(char) + (1 - w) * z(e5)
    return out


def rank_of(s: np.ndarray, target: np.ndarray) -> float:
    """Expected 1-based rank of the best target item under random tie-breaking."""
    best = s[target].max()
    above = (s[~target] > best).sum()
    ties = (s[~target] == best).sum()
    return 1 + above + ties / 2


def run(
    tenders: list[dict],
    wins: list[dict],
    e5_vecs: dict | None = None,
    e5_query=None,
    min_wins: int = MIN_WINS,
    variant: str = "default",
):
    """Per-case results: list of {entity, name, part, pool, filtered_out, repeat_buyer, ranks: {matcher: rank}}.
    The same cases (and dev/test split) are used for every variant, so the variants compare directly."""
    cases, funnel = make_cases(tenders, wins, min_wins)
    buyer_of = {}
    for t in tenders:
        if t["procedure_id"]:
            buyer_of.setdefault(t["procedure_id"], t["buyer"])
    labels = match.cpv_label_map(tenders)
    order = [c.entity for c in cases]
    random.Random(0).shuffle(order)
    part = {e: ("dev" if i % 2 == 0 else "test") for i, e in enumerate(order)}
    results = []
    for c in cases:
        p = case_profile(c, variant)
        train = c.train[:1] if variant == "one-win" else c.train
        cands = pool(tenders, c.date, p)
        held_buyer = buyer_of.get(c.held["procedure_id"])
        target = np.array([t["procedure_id"] == c.held["procedure_id"] for t in cands], dtype=bool)
        r = {
            "entity": c.entity,
            "name": c.name,
            "part": part[c.entity],
            "date": c.date,
            "pool": len(cands),
            "train": len(c.train),
            "filtered_out": not target.any(),
            # the held-out tender's buyer already awarded this company one of the wins in its full history
            "repeat_buyer": any(same_buyer(held_buyer, w.get("buyer")) for w in c.train),
            "ranks": {},
        }
        if target.any():
            for m, s in scores(c, p, cands, labels, e5_vecs, e5_query, train).items():
                r["ranks"][m] = rank_of(s, target)
        results.append(r)
    return results, funnel


def metrics(results: list[dict], matcher: str) -> dict:
    """hit@10, hit@50, median rank over cases (filtered-out held-outs are misses, rank = inf)."""
    ranks = np.array([r["ranks"].get(matcher, np.inf) if not r["filtered_out"] else np.inf for r in results])
    return {
        "n": len(ranks),
        "hit@10": float((ranks <= 10).mean()),
        "hit@50": float((ranks <= 50).mean()),
        "median": float(np.median(ranks)),
    }


def bootstrap_diff(results: list[dict], a: str, b: str, k: int = 10, n: int = 2000, seed: int = 0) -> tuple:
    """hit@k(a) - hit@k(b) with a 95% percentile bootstrap CI, resampling companies."""

    def hits(m):
        return np.array([0.0 if r["filtered_out"] else float(r["ranks"].get(m, np.inf) <= k) for r in results])

    d = hits(a) - hits(b)
    rng = np.random.default_rng(seed)
    boots = [d[rng.integers(0, len(d), len(d))].mean() for _ in range(n)]
    return float(d.mean()), float(np.percentile(boots, 2.5)), float(np.percentile(boots, 97.5))


def matchers(results: list[dict]) -> list[str]:
    seen = {}
    for r in results:
        for m in r["ranks"]:
            seen[m] = None
    return list(seen)


def choose(results: list[dict]) -> str:
    """Pick on DEV: best hit@10, then hit@50, then lower median rank; baselines excluded; ties keep current."""
    dev = [r for r in results if r["part"] == "dev"]
    cands = [m for m in matchers(results) if m not in ("random", "same-main-cpv")]
    blends = [m for m in cands if m.startswith("blend")]
    if blends:  # the blend weight is a dev-only choice too
        best_blend = max(blends, key=lambda m: (metrics(dev, m)["hit@10"], metrics(dev, m)["hit@50"], -metrics(dev, m)["median"]))
        cands = [m for m in cands if not m.startswith("blend")] + [best_blend]

    def key(m):
        x = metrics(dev, m)
        return (x["hit@10"], x["hit@50"], -x["median"], m == CURRENT)

    return max(cands, key=key)


NAMES = {
    CURRENT: "Char 3-5-gram TF-IDF + CPV boost (**shipped**)",
    "char-tfidf": "Char 3-5-gram TF-IDF, no CPV boost",
    "english-tfidf": "Word TF-IDF on English title template + CPV labels",
    "e5": "multilingual-e5-small",
    "same-main-cpv": "Baseline: same main CPV code as past wins",
    "random": "Baseline: random order",
}


def to_markdown(results: list[dict], funnel: collections.Counter) -> str:
    chosen = choose(results)
    ms = [m for m in matchers(results) if not m.startswith("blend") or m == chosen]
    if not any(m.startswith("blend") for m in ms):
        blends = [m for m in matchers(results) if m.startswith("blend")]
        if blends:
            dev = [r for r in results if r["part"] == "dev"]
            ms.append(max(blends, key=lambda m: (metrics(dev, m)["hit@10"], metrics(dev, m)["hit@50"])))
    out = ["Funnel:", ""] + [f"- {k}: {v:,}" for k, v in funnel.items()] + [""]
    for part in ("dev", "test"):
        rs = [r for r in results if r["part"] == part]
        pools = [r["pool"] for r in rs]
        filt = sum(r["filtered_out"] for r in rs)
        out += [
            f"#### {part.upper()} half: {len(rs)} companies, median pool {np.median(pools):.0f} open notices; "
            f"held-out tender removed by the profile's filters (country, deadline) for {filt} ({100 * filt / max(len(rs), 1):.0f}%)",
            "",
            "| Matcher | hit@10 | hit@50 | median rank |",
            "|---|---|---|---|",
        ]
        for m in sorted(ms, key=lambda m: -metrics(rs, m)["hit@10"]):
            x = metrics(rs, m)
            name = NAMES[m] if m in NAMES else f"Blend {m.split()[1]} × char-TF-IDF + rest × e5"
            mark = " ← chosen on dev" if m == chosen and part == "dev" else ""
            med = "∞ (miss)" if x["median"] == np.inf else f"{x['median']:.0f}"
            out.append(f"| {name}{mark} | {x['hit@10']:.3f} | {x['hit@50']:.3f} | {med} |")
        out.append("")
    test = [r for r in results if r["part"] == "test"]
    if chosen != CURRENT:
        diff, lo, hi = bootstrap_diff(test, chosen, CURRENT)
        out.append(
            f"Test, {chosen} minus shipped, hit@10: {diff:+.3f} (95% bootstrap CI {lo:+.3f} to {hi:+.3f}, "
            f"2,000 resamples of companies)."
        )
    for base in ("random", "same-main-cpv"):
        diff, lo, hi = bootstrap_diff(test, CURRENT, base)
        out.append(f"Test, shipped minus {base}, hit@10: {diff:+.3f} (95% CI {lo:+.3f} to {hi:+.3f}).")
    if results and "repeat_buyer" in results[0]:
        out += ["", repeat_split(results)]
    return "\n".join(out) + "\n"


def repeat_split(results: list[dict]) -> str:
    """Dev + test, by whether the held-out tender's buyer had already awarded the company a contract."""
    out = [
        "#### Repeat business vs new buyer (dev + test)",
        "",
        "| Held-out tender's buyer | Companies | Shipped hit@10 | Same-CPV hit@10 | Random hit@10 | Shipped hit@50 |",
        "|---|---|---|---|---|---|",
    ]
    for label, flag in (("already awarded this company a win (repeat)", True), ("new to this company", False)):
        rs = [r for r in results if r["repeat_buyer"] == flag]
        if not rs:
            continue
        m, c, rnd = metrics(rs, CURRENT), metrics(rs, "same-main-cpv"), metrics(rs, "random")
        out.append(f"| {label} | {len(rs)} | {m['hit@10']:.3f} | {c['hit@10']:.3f} | {rnd['hit@10']:.3f} | {m['hit@50']:.3f} |")
    new = [r for r in results if not r["repeat_buyer"]]
    if new:
        diff, lo, hi = bootstrap_diff(new, CURRENT, "random")
        out.append("")
        out.append(f"New buyers only, shipped minus random, hit@10: {diff:+.3f} (95% CI {lo:+.3f} to {hi:+.3f}).")
    return "\n".join(out)


def summary(results: list[dict]) -> dict:
    """Test-half headline for the home page (data/backtest-summary.json). CURRENT is the matcher
    config.yaml ships; if that ever changes, change both together (docs/evaluation.md)."""
    test = [r for r in results if r["part"] == "test"]
    m = metrics(test, CURRENT)
    out = {
        "companies": m["n"],
        "hit10": m["hit@10"],
        "hit50": m["hit@50"],
        "median": m["median"],
        "hit10_random": metrics(test, "random")["hit@10"],
        "hit10_cpv": metrics(test, "same-main-cpv")["hit@10"],
        "matcher": CURRENT,
    }
    new = [r for r in test if r.get("repeat_buyer") is False]
    if new:  # tenders from a buyer the company had never won from: the harder, more useful case
        out["hit10_new_buyer"] = metrics(new, CURRENT)["hit@10"]
        out["repeat_share"] = 1 - len(new) / len(test)
    return out


def load(history_db: Path) -> tuple[list[dict], list[dict]]:
    con = db.connect(history_db)
    con.row_factory = sqlite3.Row
    return db.load(con), [dict(r) for r in con.execute("SELECT * FROM wins")]
