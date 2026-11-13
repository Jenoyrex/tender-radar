"""Hand-labelling: build a fixed queue of (profile, tender) pairs, then label them
in the terminal. Labels go to data/labels.csv, one row per judgement.

Queue per profile (PER_PROFILE pairs, shuffled, shown blind: no score, no source):
  - half "pool": round-robin from the top-20 of each candidate matcher, so every
    model compared later has most of its top 20 judged (TREC-style pooling);
  - half "random": uniform from the tenders that pass the profile's hard filters.
The queue is frozen in data/label-queue.csv and the open tenders it was drawn from in
data/label-snapshot.json.gz, so the evaluation ranks exactly what was labelled.
"""

import csv
import datetime as dt
import gzip
import json
import random
import textwrap
from pathlib import Path

import numpy as np

from . import build, match

PER_PROFILE = 50
QUEUE_COLS = ["profile", "tender_id", "source"]
LABEL_COLS = ["profile", "tender_id", "label", "labelled_at"]
KEYS = {"r": "relevant", "n": "not_relevant", "u": "unsure"}


def candidate_rankers(cands: list[dict], p: match.Profile, data_dir: Path, all_tenders: list[dict]) -> dict:
    """{name: similarity array over cands} for the models compared in evaluation."""
    labels = match.cpv_label_map(all_tenders)
    out = {
        "char-tfidf": match.tfidf_similarity(p.description, [match.tender_text(t) for t in cands]),
        "english-tfidf": match.tfidf_similarity(p.description, [match.english_text(t, labels) for t in cands], analyzer="word"),
    }
    vecs = match.cached_embeddings(all_tenders, Path(data_dir) / "emb-e5-small.npz", match.E5_MODEL,
                                   text_fn=match.e5_text, prefix="passage: ")
    q = match.embed([p.description], match.E5_MODEL, prefix="query: ")[0]
    out["e5"] = np.stack([vecs[t["id"]] for t in cands]) @ q
    return out


def make_queue(tenders: list[dict], profiles_dir: Path, data_dir: Path, today: dt.date, seed: int = 0) -> list[dict]:
    open_ = build.latest_versions([t for t in tenders if not t["deadline"] or t["deadline"] >= today.isoformat()])
    rng = random.Random(seed)
    queue = []
    for f in sorted(Path(profiles_dir).glob("*.yaml")):
        p = match.Profile.load(f)
        cands = [t for t in open_ if match.passes_filters(t, p, today)]
        sims = candidate_rankers(cands, p, data_dir, tenders)
        tops = [[cands[i]["id"] for i in np.argsort(-s)[:20]] for s in sims.values()]
        pool = []
        for rank in range(20):  # round-robin so every model contributes equally
            for top in tops:
                if top[rank] not in pool:
                    pool.append(top[rank])
        pool = pool[: PER_PROFILE // 2]
        rest = [t["id"] for t in cands if t["id"] not in pool]
        rand = rng.sample(rest, min(PER_PROFILE - len(pool), len(rest)))
        items = [{"profile": p.slug, "tender_id": i, "source": "pool"} for i in pool]
        items += [{"profile": p.slug, "tender_id": i, "source": "random"} for i in rand]
        rng.shuffle(items)
        queue += items
    return queue, open_


def save_snapshot(path: Path, today: dt.date, tenders: list[dict]) -> None:
    with gzip.open(path, "wt", encoding="utf-8") as f:
        json.dump({"date": today.isoformat(), "tenders": tenders}, f, ensure_ascii=False)


def load_snapshot(path: Path) -> tuple[dt.date, list[dict]]:
    with gzip.open(path, "rt", encoding="utf-8") as f:
        d = json.load(f)
    return dt.date.fromisoformat(d["date"]), d["tenders"]


def show(p: match.Profile, t: dict, labels: dict, n: int, total: int) -> None:
    w = lambda s, ind="  ": textwrap.fill(s, 100, initial_indent=ind, subsequent_indent=ind)
    cpvs = [f"{c} {labels.get(c, '')}".strip() for c in (t["cpv"] or "").split()]
    value = "not published" if t["value"] is None else f"{t['value']:,.0f} {t['currency']}" + (
        f" (≈ €{t['value_eur']:,.0f})" if t["value_eur"] and t["currency"] != "EUR" else "")
    print("\n" + "=" * 100)
    print(f"[{n}/{total}]  PROFILE: {p.name}")
    print(w(p.description))
    print("-" * 100)
    print(w(t["title_en"] or t["title"], "TENDER: "))
    if t.get("title_english") and t["title_english"] not in (t["title_en"] or ""):
        print(w(t["title_english"], "  English title: "))
    print(f"  Buyer: {t['buyer']} ({t['country']})   Value: {value}   Deadline: {t['deadline'] or '?'}")
    print(w("CPV: " + "; ".join(cpvs)))
    print(w((t["description"] or "")[:500] + ("…" if len(t["description"] or "") > 500 else "")))
    print(f"  {t['link']}")


def run(tenders: list[dict], profiles_dir: Path, queue_path: Path, labels_path: Path) -> None:
    by_id = {t["id"]: t for t in tenders}
    labels_map = match.cpv_label_map(tenders)
    profiles = {f.stem: match.Profile.load(f) for f in Path(profiles_dir).glob("*.yaml")}
    with open(queue_path, encoding="utf-8") as f:
        queue = list(csv.DictReader(f))
    done = set()
    if Path(labels_path).exists():
        with open(labels_path, encoding="utf-8") as f:
            done = {(r["profile"], r["tender_id"]) for r in csv.DictReader(f)}
    todo = [q for q in queue if (q["profile"], q["tender_id"]) not in done and q["tender_id"] in by_id]
    print(f"{len(done)} labelled, {len(todo)} to go. Keys: r=relevant n=not relevant u=unsure s=skip q=quit")
    new = not Path(labels_path).exists()
    with open(labels_path, "a", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, LABEL_COLS, lineterminator="\n")
        if new:
            w.writeheader()
        for i, q in enumerate(todo, len(done) + 1):
            show(profiles[q["profile"]], by_id[q["tender_id"]], labels_map, i, len(queue))
            while (k := input("  Is this a tender this business would want to bid on? [r/n/u/s/q] ").strip().lower()) not in (*KEYS, "s", "q"):
                pass
            if k == "q":
                break
            if k in KEYS:
                w.writerow({"profile": q["profile"], "tender_id": q["tender_id"], "label": KEYS[k],
                            "labelled_at": dt.datetime.now().isoformat(timespec="seconds")})
                f.flush()  # never lose a judgement
    print(f"Saved to {labels_path}")
