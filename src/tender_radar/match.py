"""Rank tenders for a business profile.

score = text similarity (TF-IDF or embeddings) + CPV_BOOST if a CPV code matches
a preferred prefix. Hard filters (open, country, value, excluded keywords) remove
tenders before scoring. Every result carries human-readable reasons.
"""

import datetime as dt
import re
from dataclasses import dataclass, field
from pathlib import Path

import numpy as np
import yaml
from sklearn.feature_extraction.text import TfidfVectorizer

CPV_BOOST = 0.1
EMBED_MODEL = "paraphrase-multilingual-MiniLM-L12-v2"
WORD = re.compile(r"[^\W\d_]{4,}", re.UNICODE)


@dataclass
class Profile:
    slug: str
    name: str
    description: str
    countries: list[str] = field(default_factory=list)
    cpv: list[str] = field(default_factory=list)
    min_value_eur: float | None = None
    max_value_eur: float | None = None
    exclude_keywords: list[str] = field(default_factory=list)
    signup_issue: int | None = None  # GitHub issue that created it (self-serve sign-up)

    @classmethod
    def load(cls, path: Path) -> "Profile":
        d = yaml.safe_load(Path(path).read_text(encoding="utf-8"))
        return cls(slug=Path(path).stem, **d)


def tender_text(t: dict) -> str:
    """What the matcher reads. Deliberately excludes CPV codes and title_en
    (title_en embeds the CPV label, which would leak the answer in evaluation)."""
    return f"{t['title'] or ''}. {t['description'] or ''}"


E5_MODEL = "intfloat/multilingual-e5-small"


def cpv_label_map(tenders: list[dict]) -> dict:
    """{8-digit CPV: English label}, learned from TED's notice-title template."""
    return {t["main_cpv"]: t["cpv_label"] for t in tenders if t.get("main_cpv") and t.get("cpv_label")}


def english_text(t: dict, labels: dict) -> str:
    """English-only view: TED's English title (country – CPV label – title) plus
    the English labels of all the tender's CPV codes. Contains CPV information,
    so it must not be scored against the CPV proxy without a warning."""
    extra = sorted({labels[c] for c in (t["cpv"] or "").split() if c in labels})
    return f"{t['title_en'] or ''}. {'; '.join(extra)}"


def e5_text(t: dict) -> str:
    return f"{t['title_en'] or ''}. {t['description'] or ''}"


# ---- similarity models -------------------------------------------------------

def tfidf_similarity(query: str, docs: list[str], analyzer: str = "char_wb") -> np.ndarray:
    big = len(docs) >= 50  # document-frequency cut-offs only make sense on a real corpus
    df = dict(min_df=2, max_df=0.5) if big else {}
    if analyzer == "word":
        vec = TfidfVectorizer(strip_accents="unicode", sublinear_tf=True, **df)
    else:  # character n-grams catch cross-language cognates (software/Software/softwaru)
        vec = TfidfVectorizer(analyzer="char_wb", ngram_range=(3, 5), sublinear_tf=True, **df)
    try:
        m = vec.fit_transform(docs + [query])  # rows are L2-normalised: dot = cosine
    except ValueError:  # empty vocabulary
        return np.zeros(len(docs))
    return (m[:-1] @ m[-1].T).toarray().ravel()


_models = {}


def embed(texts: list[str], model_name: str = EMBED_MODEL, prefix: str = "") -> np.ndarray:
    """prefix: e5 models expect "query: " / "passage: "."""
    from sentence_transformers import SentenceTransformer  # optional dependency
    if model_name not in _models:
        _models[model_name] = SentenceTransformer(model_name, device="cpu")
    return _models[model_name].encode([prefix + x for x in texts], batch_size=64, normalize_embeddings=True, show_progress_bar=False)


def cached_embeddings(tenders: list[dict], path: Path, model_name: str = EMBED_MODEL,
                      text_fn=tender_text, prefix: str = "") -> dict:
    """{id: vector}, embedding only tenders not already in the .npz cache at `path`."""
    path = Path(path)
    cache = dict(np.load(path)) if path.exists() else {}
    missing = [t for t in tenders if t["id"] not in cache]
    if missing:
        cache |= dict(zip((t["id"] for t in missing), embed([text_fn(t) for t in missing], model_name, prefix)))
        path.parent.mkdir(parents=True, exist_ok=True)
        np.savez(path, **cache)  # ponytail: never pruned; ~1.5 KB per notice
    return cache


def embedding_similarity(query: str, docs: list[str], model_name: str = EMBED_MODEL, doc_vecs=None) -> np.ndarray:
    if doc_vecs is None:
        doc_vecs = embed(docs, model_name)
    return doc_vecs @ embed([query], model_name)[0]


# ---- filters and explanations ------------------------------------------------

def passes_filters(t: dict, p: Profile, today: dt.date) -> bool:
    if t["deadline"] and t["deadline"] < today.isoformat():
        return False
    if p.countries and t["country"] not in p.countries:
        return False
    v = t["value_eur"]  # unknown value passes: excluding it would hide half of all tenders
    if v is not None and ((p.min_value_eur and v < p.min_value_eur) or (p.max_value_eur and v > p.max_value_eur)):
        return False
    if p.exclude_keywords:
        hay = f"{t['title']} {t['title_en']} {t['description']}".lower()
        if any(k.lower() in hay for k in p.exclude_keywords):
            return False
    return True


def cpv_hits(t: dict, prefixes: list[str]) -> list[str]:
    return [c for c in (t["cpv"] or "").split() if any(c.startswith(p) for p in prefixes)]


def shared_terms(a: str, b: str, n: int = 5) -> list[str]:
    wa = set(w.lower() for w in WORD.findall(a))
    return sorted({w.lower() for w in WORD.findall(b)} & wa, key=len, reverse=True)[:n]


def reasons(t: dict, p: Profile, sim: float) -> list[str]:
    out = [f"text similarity {sim:.2f}"]
    if terms := shared_terms(p.description, tender_text(t)):
        out.append("shared words: " + ", ".join(terms))
    if hits := cpv_hits(t, p.cpv):
        out.append("CPV " + ", ".join(hits[:3]) + " matches your sectors")
    out.append(f"buyer in {t['country']}" + (" (in your countries)" if p.countries else ""))
    if t["value_eur"] is not None and (p.min_value_eur or p.max_value_eur):
        out.append(f"value ≈ €{t['value_eur']:,.0f} is within your range")
    elif t["value_eur"] is None:
        out.append("value not published")
    return out


def rank(tenders: list[dict], p: Profile, method: str = "tfidf", today: dt.date | None = None,
         top: int = 50, doc_vecs: dict | None = None) -> list[dict]:
    """Return the top tenders for a profile, each with 'score' and 'reasons'."""
    today = today or dt.date.today()
    cands = [t for t in tenders if passes_filters(t, p, today)]
    if not cands:
        return []
    docs = [tender_text(t) for t in cands]
    if method == "tfidf":
        sims = tfidf_similarity(p.description, docs)
    else:
        vecs = np.stack([doc_vecs[t["id"]] for t in cands]) if doc_vecs else None
        sims = embedding_similarity(p.description, docs, doc_vecs=vecs)
    scores = sims + CPV_BOOST * np.array([bool(cpv_hits(t, p.cpv)) for t in cands])
    order = np.argsort(-scores)[:top]
    return [cands[i] | {"score": round(float(scores[i]), 3), "reasons": reasons(cands[i], p, float(sims[i]))} for i in order]
