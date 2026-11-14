"""Evaluate matchers on hand labels (data/labels*.csv) with a held-out split.

- Labels: the human's where present (data/labels.csv), else Claude's
  (data/labels-claude.csv). Both are reported separately in docs/evaluation.md.
- Candidates: the frozen snapshot the queue was drawn from, with the profile's
  hard filters, so every model ranks exactly the pool that was labelled.
- Condensed lists: each model ranks all candidates; unjudged tenders are
  dropped and precision@k is taken over the first k *judged* tenders.
- Held-out split: judged pairs are split 50/50 per profile (stratified by
  pool/random source, fixed seed). The blend weight and the model choice are
  made on DEV only; TEST numbers are reported for the chosen model.
- relevant = 1, not_relevant = 0, unsure = 0 (strict) or 0.5 (lenient).
"""

import csv
import random
from pathlib import Path

import numpy as np

from . import label, match

KS = (10, 20)
BLEND_WEIGHTS = (0.25, 0.5, 0.75)


def read_labels(data_dir: Path) -> dict:
    out = {}
    for name in ("labels-claude.csv", "labels.csv"):  # human file last: it overrides
        p = Path(data_dir) / name
        if p.exists():
            with open(p, encoding="utf-8") as f:
                for r in csv.DictReader(f):
                    out[(r["profile"], r["tender_id"])] = r["label"]
    return out


def split(queue: list[dict], labels: dict, seed: int = 0) -> dict:
    """{(profile, tender_id): 'dev' | 'test'} for judged pairs."""
    rng = random.Random(seed)
    groups = {}
    for q in queue:
        if (q["profile"], q["tender_id"]) in labels:
            groups.setdefault((q["profile"], q["source"]), []).append((q["profile"], q["tender_id"]))
    out = {}
    for items in groups.values():
        rng.shuffle(items)
        for i, k in enumerate(items):
            out[k] = "dev" if i % 2 == 0 else "test"
    return out


def z(x):
    return (x - x.mean()) / (x.std() or 1)


def scores_for(cands, p, data_dir, all_tenders) -> dict:
    s = label.candidate_rankers(cands, p, data_dir, all_tenders)
    for w in BLEND_WEIGHTS:
        s[f"blend w={w}"] = w * z(s["char-tfidf"]) + (1 - w) * z(s["e5"])
    return s


def precision(ranked_ids, judged: dict, k: int, lenient: bool) -> float:
    gain = {"relevant": 1.0, "unsure": 0.5 if lenient else 0.0, "not_relevant": 0.0}
    top = [judged[i] for i in ranked_ids if i in judged][:k]
    return sum(gain[x] for x in top) / k


def run(data_dir: Path, profiles_dir: Path) -> dict:
    today, snapshot = label.load_snapshot(Path(data_dir) / "label-snapshot.json.gz")
    with open(Path(data_dir) / "label-queue.csv", encoding="utf-8") as f:
        queue = list(csv.DictReader(f))
    labels = read_labels(data_dir)
    parts = split(queue, labels)
    res = {}  # (part, lenient) -> model -> {k: mean precision over profiles}
    base = {}
    for f in sorted(Path(profiles_dir).glob("*.yaml")):
        p = match.Profile.load(f)
        cands = [t for t in snapshot if match.passes_filters(t, p, today)]
        ids = [t["id"] for t in cands]
        for name, s in scores_for(cands, p, data_dir, snapshot).items():
            ranked = [ids[i] for i in np.argsort(-s)]
            for part in ("dev", "test"):
                judged = {tid: labels[(p.slug, tid)] for (pr, tid), sp in parts.items() if pr == p.slug and sp == part}
                for lenient in (False, True):
                    for k in KS:
                        res.setdefault((part, lenient), {}).setdefault(name, {}).setdefault(k, []).append(
                            precision(ranked, judged, k, lenient)
                        )
                    if name == "char-tfidf":
                        rel = [1.0 if v == "relevant" else (0.5 if lenient and v == "unsure" else 0.0) for v in judged.values()]
                        base.setdefault((part, lenient), []).append(sum(rel) / len(rel))
    mean = {key: {m: {k: float(np.mean(v)) for k, v in ks.items()} for m, ks in d.items()} for key, d in res.items()}
    return {
        "precision": mean,
        "base": {k: float(np.mean(v)) for k, v in base.items()},
        "n_judged": len(parts),
        "n_relevant": sum(v == "relevant" for v in labels.values()),
        "n_unsure": sum(v == "unsure" for v in labels.values()),
    }


def choose(res: dict) -> tuple[str, str]:
    """Pick the blend weight, then the model, on DEV (strict P@10, lenient P@10 as tie-break)."""
    dev, devl = res["precision"][("dev", False)], res["precision"][("dev", True)]
    key = lambda m: (dev[m][10], devl[m][10], m == "char-tfidf")  # final tie-break: keep current model
    blend = max((m for m in dev if m.startswith("blend")), key=lambda m: (dev[m][10], devl[m][10], m == "blend w=0.5"))
    models = ["char-tfidf", "english-tfidf", "e5", blend]
    return blend, max(models, key=key)


def to_markdown(res: dict) -> str:
    blend, chosen = choose(res)
    models = ["char-tfidf", "english-tfidf", "e5", blend]
    names = {
        "char-tfidf": "Char 3-5-gram TF-IDF (current)",
        "english-tfidf": "TF-IDF on English title + CPV labels",
        "e5": "multilingual-e5-small on English title + description",
        blend: f"Blend: w × char-TF-IDF + (1−w) × e5, {blend.split()[1]} picked on dev",
    }
    out = []
    for part in ("dev", "test"):
        out += [
            f"#### {part.upper()} half",
            "",
            "| Model | P@10 strict | P@20 strict | P@10 lenient | P@20 lenient |",
            "|---|---|---|---|---|",
        ]
        b, bl = res["base"][(part, False)], res["base"][(part, True)]
        out.append(f"| Share relevant among judged (random baseline) | {b:.2f} | {b:.2f} | {bl:.2f} | {bl:.2f} |")
        for m in models:
            s, le = res["precision"][(part, False)][m], res["precision"][(part, True)][m]
            mark = " ← chosen on dev" if m == chosen and part == "dev" else ""
            out.append(f"| {names[m]}{mark} | {s[10]:.2f} | {s[20]:.2f} | {le[10]:.2f} | {le[20]:.2f} |")
        out.append("")
    out.append(
        f"_{res['n_judged']} judged pairs ({res['n_relevant']} relevant, {res['n_unsure']} unsure), "
        "3 profiles, ~25 judged pairs per profile per half._"
    )
    return "\n".join(out) + "\n"
