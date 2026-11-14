"""Offline evaluation with CPV codes as weak ground truth.

For each 4-digit CPV group G:
  A) "sample" profile: concatenate title + description of 10 random tenders in G.
  B) "short" profile: a one-line English business description of G, hand-written
     from the CPV label (closer to what a real user types).
The matcher never sees CPV codes (tender_text excludes them). Candidates exclude
the sampled tenders and every tender from the same buyers, so near-duplicate
notices from one buyer can't inflate the score. Precision@k = share of the top k
that belong to G. "random" = G's share of the candidate pool.
"""

import random
import statistics
from pathlib import Path

import numpy as np

from . import match

GROUPS = {
    "7221": "We develop and customise packaged software and license business software products.",
    "7222": "IT consultancy: systems and technical consulting, IT strategy, architecture and project advice.",
    "7223": "Custom software development: we design and build bespoke applications for clients.",
    "7224": "Systems analysis and programming services for business information systems.",
    "7225": "IT system and support services: maintenance, helpdesk and application support.",
    "7226": "Software-related services: implementation, integration, upgrades and licences of software.",
    "7231": "Data processing services: data entry, digitisation and processing of records.",
    "7232": "Database services: building, hosting and managing databases.",
    "7241": "Internet service provider: internet access, connectivity and web hosting.",
    "7261": "Technical computer support: on-site IT support for computers and peripherals.",
    "7270": "Computer network services: design, installation and maintenance of networks.",
}
SEEDS = range(5)
SAMPLE = 10
KS = (10, 50)


def in_group(t, g):
    return any(c.startswith(g) for c in t["cpv"].split())


def methods(tenders, emb_cache):
    """Each method: score(short_text, picked_idx, cand_idx) -> similarities for cand_idx.
    picked_idx empty = setting B (use short_text); else setting A (use the picked tenders).

    TF-IDF is fitted once on the whole corpus (no labels involved) for speed.
    Setting A gives embeddings the centroid of the picked tenders' vectors, because
    the models truncate input at 128-512 tokens and would otherwise see one tender only.
    Methods marked "sees CPV" read TED's English title / CPV labels, which leak the
    proxy's answer; their proxy scores are not comparable and are shown for completeness.
    """
    from sklearn.feature_extraction.text import TfidfVectorizer

    labels = match.cpv_label_map(tenders)
    native = [match.tender_text(t) for t in tenders]
    english = [match.english_text(t, labels) for t in tenders]
    out = {}
    for name, docs, kw in (
        ("TF-IDF words (baseline)", native, dict(strip_accents="unicode")),
        ("TF-IDF char 3-5 grams (current)", native, dict(analyzer="char_wb", ngram_range=(3, 5))),
        ("TF-IDF English title + CPV labels (sees CPV)", english, dict(strip_accents="unicode")),
    ):
        vec = TfidfVectorizer(sublinear_tf=True, min_df=2, max_df=0.5, **kw).fit(docs)
        m = vec.transform(docs)

        def score(q, picked, cand, vec=vec, m=m, docs=docs):
            q = " ".join(docs[i][:600] for i in picked) if picked else q
            return (m[cand] @ vec.transform([q]).T).toarray().ravel()

        out[name] = score
    for name, cache in emb_cache.items():
        v = np.stack([cache[t["id"]] for t in tenders])
        e5 = name == match.E5_MODEL

        def score(q, picked, cand, v=v, name=name, e5=e5):
            qv = v[picked].mean(0) if picked else match.embed([q], name, "query: " if e5 else "")[0]
            return v[cand] @ (qv / np.linalg.norm(qv))

        out["e5-small, English title + description (sees CPV)" if e5 else f"Embeddings: {name}"] = score
    char, e5name = "TF-IDF char 3-5 grams (current)", "e5-small, English title + description (sees CPV)"
    if e5name in out:
        z = lambda x: (x - x.mean()) / (x.std() or 1)
        out["Blend 0.5 char-TF-IDF + 0.5 e5 (sees CPV)"] = lambda q, p, c: (
            0.5 * z(out[char](q, p, c)) + 0.5 * z(out[e5name](q, p, c))
        )
    return out


def run(tenders: list[dict], emb_cache: dict) -> dict:
    """-> {setting: {method: {group: {k: precision}}}} plus random baseline."""
    ms = methods(tenders, emb_cache)
    res = {"sample": {}, "short": {}}
    for g, short_text in GROUPS.items():
        members = [i for i, t in enumerate(tenders) if in_group(t, g)]
        for setting in res:
            for seed in SEEDS if setting == "sample" else [0]:
                rng = random.Random(f"{g}-{seed}")
                picked = rng.sample(members, SAMPLE)
                buyers = {tenders[i]["buyer"] for i in picked}
                cand = [i for i, t in enumerate(tenders) if i not in picked and t["buyer"] not in buyers]
                truth = np.array([in_group(tenders[i], g) for i in cand])
                rows = {"Random ranking": {k: truth.mean() for k in KS}}
                for mname, score in ms.items():
                    order = np.argsort(-score(short_text, picked if setting == "sample" else [], cand))
                    rows[mname] = {k: truth[order[:k]].mean() for k in KS}
                for mname, pk in rows.items():
                    acc = res[setting].setdefault(mname, {}).setdefault(g, {k: [] for k in KS})
                    for k in KS:
                        acc[k].append(pk[k])
    return {
        s: {m: {g: {k: statistics.mean(v) for k, v in d.items()} for g, d in gs.items()} for m, gs in ms_.items()}
        for s, ms_ in res.items()
    }


def to_markdown(res: dict, n_tenders: int) -> str:
    lines = []
    for setting, title in (
        ("sample", "A. Profile built from 10 sampled tenders of the group"),
        ("short", "B. Profile = one-line English business description"),
    ):
        lines += [f"### {title}", "", "| Method | P@10 | P@50 |", "|---|---|---|"]
        for m, gs in res[setting].items():
            p10 = statistics.mean(v[10] for v in gs.values())
            p50 = statistics.mean(v[50] for v in gs.values())
            lines.append(f"| {m} | {p10:.2f} | {p50:.2f} |")
        lines.append("")
    lines += [
        "### Per group, setting B, P@10",
        "",
        "| Group | " + " | ".join(res["short"]) + " |",
        "|---" * (len(res["short"]) + 1) + "|",
    ]
    for g in GROUPS:
        lines.append(f"| {g} | " + " | ".join(f"{gs[g][10]:.2f}" for gs in res["short"].values()) + " |")
    return "\n".join(lines) + f"\n\n_{n_tenders} tenders, {len(GROUPS)} CPV groups, {len(SEEDS)} seeds for setting A._\n"


def main(tenders: list[dict], data_dir: Path, models: list[str]) -> str:
    emb = {m: match.cached_embeddings(tenders, Path(data_dir) / f"emb-{m}.npz", m) for m in models if m != match.E5_MODEL}
    if match.E5_MODEL in models:
        emb[match.E5_MODEL] = match.cached_embeddings(
            tenders, Path(data_dir) / "emb-e5-small.npz", match.E5_MODEL, text_fn=match.e5_text, prefix="passage: "
        )
    return to_markdown(run(tenders, emb), len(tenders))
