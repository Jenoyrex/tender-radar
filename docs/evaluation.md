# Evaluation

**Question:** does the matcher put the right tenders at the top, and does a
sentence-transformers model beat a TF-IDF baseline?

**Short answer:** all methods beat random ranking by 2–3×, and **no embedding
model clearly beats TF-IDF**. The site ships **character 3–5-gram TF-IDF**. It
ties the best embedding model on the realistic test (B), is close to the best on
test A, and needs no PyTorch.

## Method

There are no relevance labels for "this tender suits this business", so CPV
codes serve as **weak ground truth**: a tender is relevant to a group if one of
its CPV codes starts with the group's 4-digit prefix (e.g. `7222` = IT
consultancy).

- Corpus: the 5414 CPV-72 competition notices published 2026-09-14 → 2026-11-13.
- The matcher sees **only the original-language title + description**. CPV codes
  and TED's English `notice-title` (which embeds the CPV label) are hidden.
- 11 groups with ≥ 100 tenders.
- **Setting A** (the brief's test): profile = 10 random tenders from the group.
  5 random seeds per group. TF-IDF gets the 10 texts concatenated; embedding
  models get the centroid of the 10 tender vectors (they truncate input at 128
  tokens, so concatenation would hide 9 of the 10 tenders).
- **Setting B** (closer to real use): profile = one English sentence I wrote
  from the CPV label, e.g. *"IT consultancy: systems and technical consulting,
  IT strategy, architecture and project advice."*
- In both settings the sampled tenders **and every other tender from the same
  buyers** are removed from the candidates, so buyers re-publishing near-identical
  notices can't inflate the scores.
- Metric: precision@k = share of the top k that belong to the group, averaged
  over groups. "Random ranking" = the group's share of the candidates.

Reproduce with `tender-radar evaluate` (≈ 1 minute once the embeddings are cached).

## Results

### A. Profile built from 10 sampled tenders of the group

| Method | P@10 | P@50 |
|---|---|---|
| Random ranking | 0.09 | 0.09 |
| TF-IDF words (baseline) | 0.25 | 0.20 |
| TF-IDF char 3-5 grams | 0.22 | 0.21 |
| Embeddings: all-MiniLM-L6-v2 | 0.20 | 0.19 |
| Embeddings: paraphrase-multilingual-MiniLM-L12-v2 | 0.15 | 0.15 |

### B. Profile = one-line English business description

| Method | P@10 | P@50 |
|---|---|---|
| Random ranking | 0.09 | 0.09 |
| TF-IDF words (baseline) | 0.16 | 0.15 |
| TF-IDF char 3-5 grams | 0.21 | 0.21 |
| Embeddings: all-MiniLM-L6-v2 | 0.21 | 0.18 |
| Embeddings: paraphrase-multilingual-MiniLM-L12-v2 | 0.21 | 0.19 |

### Per group, setting B, P@10

| Group | Random ranking | TF-IDF words (baseline) | TF-IDF char 3-5 grams | Embeddings: all-MiniLM-L6-v2 | Embeddings: paraphrase-multilingual-MiniLM-L12-v2 |
|---|---|---|---|---|---|
| 7221 | 0.12 | 0.10 | 0.10 | 0.00 | 0.00 |
| 7222 | 0.12 | 0.40 | 0.40 | 0.60 | 0.60 |
| 7223 | 0.03 | 0.00 | 0.00 | 0.00 | 0.00 |
| 7224 | 0.03 | 0.00 | 0.00 | 0.00 | 0.00 |
| 7225 | 0.12 | 0.20 | 0.10 | 0.30 | 0.20 |
| 7226 | 0.37 | 0.40 | 0.40 | 0.50 | 0.80 |
| 7231 | 0.07 | 0.10 | 0.10 | 0.00 | 0.20 |
| 7232 | 0.02 | 0.10 | 0.40 | 0.00 | 0.10 |
| 7241 | 0.04 | 0.30 | 0.50 | 0.30 | 0.00 |
| 7261 | 0.04 | 0.10 | 0.10 | 0.40 | 0.40 |
| 7270 | 0.02 | 0.10 | 0.20 | 0.20 | 0.00 |

_5414 tenders, 11 CPV groups, 5 seeds for setting A._

## Reading the results honestly

- **Everything is weak in absolute terms.** The best P@10 is about 0.25: 2–3
  relevant tenders in a top 10, against about 1 for random ranking. Part of
  this is the ground truth: 4-digit CPV groups inside IT overlap heavily
  ("software-related services" vs "programming of packaged software" vs
  "custom software development"), and buyers pick codes inconsistently. A
  tender counted "wrong" is often a perfectly reasonable match.
- **Setting A favours lexical methods.** Sampled tenders share the language,
  buyer jargon and boilerplate of their group, which word TF-IDF exploits
  directly. Word TF-IDF wins here (0.25 P@10).
- **Setting B is where multilinguality should help**, since an English sentence
  meets mostly Czech, German, Spanish and Polish text. The multilingual model
  does reach 0.21 P@10, but so do character n-grams, which catch cognates
  (*software, Software, softwaru, informatique/informática*) for free. Word
  TF-IDF drops to 0.16.
- **Setting B is small and noisy.** 11 queries × 10 results: a difference of
  0.05 is about half a hit per query. Per-group results swing a lot, e.g.
  the multilingual model wins `7226` (0.80) but gets `7241` (internet services)
  completely wrong (0.00). I would not call any B difference significant.
- **I picked the shipped model with this same evaluation**, so its numbers are
  slightly optimistic. There is no held-out test set.

## Decision

The fancy model did not beat the baseline, so it is **not** the default. The
site uses character n-gram TF-IDF (`match_method: tfidf` in `config.yaml`).
Embeddings stay available behind `match_method: embeddings` and the optional
`[embeddings]` extra. Dropping PyTorch also cuts the daily run from minutes to
seconds.

Possible next steps, roughly in order of expected value: real relevance labels
(even 100 hand-judged pairs per profile), translating titles to English before
matching (TED's `notice-title` translation includes the CPV label, so a clean
translation would need a local MT model), and a stronger multilingual model
such as `multilingual-e5-base`, which costs about 3× the CPU time.
