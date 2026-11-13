# Evaluation

## Round 2 (2026-11-13): hand labels + held-out split

**Short answer: no new model clearly beats the current one, so the site keeps
character 3-5-gram TF-IDF.** The model picked on the dev half (TF-IDF on
TED's English title + CPV labels) only *ties* the current model on the test
half (P@10 0.27 vs 0.27 strict) and is slightly worse on the lenient score.
e5 and the blend are a little worse on test.

### Who labelled what (read this first)

- **150 (profile, tender) pairs**, 50 per example profile. Half come from the
  pooled top-20s of the three candidate models (char-TF-IDF, English TF-IDF,
  e5), half are random tenders that pass the profile's filters. Pooling makes
  sure every compared model has its top results judged, not only the current one.
- **144 of 150 labels were made by an AI (Claude), not a human.** The
  project owner labelled 6 pairs and asked Claude to do the rest. Claude labelled
  blind: it saw profile and tender text only, never scores or which model surfaced a
  tender. Human labels override Claude's where both exist
  (`data/labels.csv` overrides `data/labels-claude.csv`).
- **The labels disagree a lot.** On the 6 pairs labelled by both, they agree
  exactly on 2. Claude had also seen the human answers before labelling, so
  real independent agreement is probably no higher. Relevance here is subjective
  ("would this business bid?"). Treat these numbers as *one labeller's
  opinion*, not ground truth.
- **Positives are rare:** 17 relevant and 21 unsure out of 150. The web-studio
  profile has only 2 relevant pairs. One extra hit in a top 10 moves a
  profile's P@10 by 0.10, and the average by 0.03.

### Method

- Candidates = the frozen snapshot the queue was drawn from
  (`data/label-snapshot.json.gz`), after the profile's hard filters.
- Each model ranks all candidates; unjudged tenders are skipped (a *condensed
  list*) and precision@k is computed over the first k judged tenders. **Strict**:
  only "relevant" counts. **Lenient**: "unsure" counts 0.5.
- **Held-out split:** judged pairs are split 50/50 per profile, stratified by
  pool/random, fixed seed. The blend weight (0.25/0.5/0.75) and the model choice
  are made on DEV; TEST is only read afterwards.
- With ~25 judged pairs per profile per half, P@20 covers most of the judged
  list, so it sits close to the base rate by construction. P@10 is the more
  informative number.

Reproduce: `tender-radar evaluate --labels`. Label more: `tender-radar label`.

### Results on the hand labels

#### DEV half

| Model | P@10 strict | P@20 strict | P@10 lenient | P@20 lenient |
|---|---|---|---|---|
| Share relevant among judged (random baseline) | 0.09 | 0.09 | 0.17 | 0.17 |
| Char 3-5-gram TF-IDF (current) | 0.17 | 0.10 | 0.30 | 0.19 |
| TF-IDF on English title + CPV labels ← chosen on dev | 0.20 | 0.12 | 0.32 | 0.21 |
| multilingual-e5-small on English title + description | 0.13 | 0.08 | 0.25 | 0.18 |
| Blend: w × char-TF-IDF + (1−w) × e5, w=0.5 picked on dev | 0.17 | 0.10 | 0.30 | 0.20 |

#### TEST half

| Model | P@10 strict | P@20 strict | P@10 lenient | P@20 lenient |
|---|---|---|---|---|
| Share relevant among judged (random baseline) | 0.14 | 0.14 | 0.20 | 0.20 |
| Char 3-5-gram TF-IDF (current) | 0.27 | 0.17 | 0.35 | 0.23 |
| TF-IDF on English title + CPV labels | 0.27 | 0.15 | 0.33 | 0.22 |
| multilingual-e5-small on English title + description | 0.23 | 0.17 | 0.32 | 0.23 |
| Blend: w × char-TF-IDF + (1−w) × e5, w=0.5 picked on dev | 0.23 | 0.17 | 0.32 | 0.23 |

_150 judged pairs (17 relevant, 21 unsure), 3 profiles, ~25 judged pairs per profile per half._


### Results on the CPV proxy (same models)

Models marked "sees CPV" read TED's English title, which embeds the CPV label,
or the CPV labels directly. On this proxy they are **reading the answer**, which
is why English TF-IDF jumps to 0.6. These rows say nothing about real
quality. The hand labels above show the same model only ties the current one.

#### A. Profile built from 10 sampled tenders of the group

| Method | P@10 | P@50 |
|---|---|---|
| Random ranking | 0.09 | 0.09 |
| TF-IDF words (baseline) | 0.25 | 0.20 |
| TF-IDF char 3-5 grams (current) | 0.22 | 0.21 |
| TF-IDF English title + CPV labels (sees CPV) | 0.59 | 0.49 |
| Embeddings: paraphrase-multilingual-MiniLM-L12-v2 | 0.15 | 0.15 |
| e5-small, English title + description (sees CPV) | 0.18 | 0.17 |
| Blend 0.5 char-TF-IDF + 0.5 e5 (sees CPV) | 0.28 | 0.23 |

#### B. Profile = one-line English business description

| Method | P@10 | P@50 |
|---|---|---|
| Random ranking | 0.09 | 0.09 |
| TF-IDF words (baseline) | 0.16 | 0.15 |
| TF-IDF char 3-5 grams (current) | 0.21 | 0.21 |
| TF-IDF English title + CPV labels (sees CPV) | 0.63 | 0.56 |
| Embeddings: paraphrase-multilingual-MiniLM-L12-v2 | 0.21 | 0.19 |
| e5-small, English title + description (sees CPV) | 0.31 | 0.24 |
| Blend 0.5 char-TF-IDF + 0.5 e5 (sees CPV) | 0.25 | 0.22 |

#### Per group, setting B, P@10

| Group | Random ranking | TF-IDF words (baseline) | TF-IDF char 3-5 grams (current) | TF-IDF English title + CPV labels (sees CPV) | Embeddings: paraphrase-multilingual-MiniLM-L12-v2 | e5-small, English title + description (sees CPV) | Blend 0.5 char-TF-IDF + 0.5 e5 (sees CPV) |
|---|---|---|---|---|---|---|---|
| 7221 | 0.12 | 0.10 | 0.10 | 1.00 | 0.00 | 0.00 | 0.20 |
| 7222 | 0.12 | 0.40 | 0.40 | 0.80 | 0.60 | 0.30 | 0.50 |
| 7223 | 0.03 | 0.00 | 0.00 | 0.60 | 0.00 | 0.40 | 0.00 |
| 7224 | 0.03 | 0.00 | 0.00 | 0.20 | 0.00 | 0.10 | 0.00 |
| 7225 | 0.12 | 0.20 | 0.10 | 0.90 | 0.20 | 0.50 | 0.20 |
| 7226 | 0.37 | 0.40 | 0.40 | 0.70 | 0.80 | 0.70 | 0.50 |
| 7231 | 0.07 | 0.10 | 0.10 | 1.00 | 0.20 | 0.60 | 0.10 |
| 7232 | 0.02 | 0.10 | 0.40 | 0.40 | 0.10 | 0.20 | 0.30 |
| 7241 | 0.04 | 0.30 | 0.50 | 0.70 | 0.00 | 0.10 | 0.50 |
| 7261 | 0.04 | 0.10 | 0.10 | 0.20 | 0.40 | 0.30 | 0.20 |
| 7270 | 0.02 | 0.10 | 0.20 | 0.40 | 0.00 | 0.20 | 0.20 |

_5414 tenders, 11 CPV groups, 5 seeds for setting A._


### Decision

**Ship nothing new.** The rule was "ship the winner only if it clearly beats the
current model on held-out data", and nothing did. The English-label TF-IDF and
e5 code stays in the repo for the next round.

What would actually move this: more and better labels (several human
labellers, more positives per profile, e.g. by pooling deeper for niche
profiles), and visitor feedback from the "relevant / not relevant" links on the
profile pages.

---

## Round 1 (2026-11-13): CPV proxy only

**Question:** does the matcher put the right tenders at the top, and does a
sentence-transformers model beat a TF-IDF baseline?

**Short answer:** all methods beat random ranking by 2–3×, and **no embedding
model clearly beats TF-IDF**. The site ships **character 3–5-gram TF-IDF**. It
ties the best embedding model on the realistic test (B), is close to the best on
test A, and needs no PyTorch.

### Method

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

### Results

#### A. Profile built from 10 sampled tenders of the group

| Method | P@10 | P@50 |
|---|---|---|
| Random ranking | 0.09 | 0.09 |
| TF-IDF words (baseline) | 0.25 | 0.20 |
| TF-IDF char 3-5 grams | 0.22 | 0.21 |
| Embeddings: all-MiniLM-L6-v2 | 0.20 | 0.19 |
| Embeddings: paraphrase-multilingual-MiniLM-L12-v2 | 0.15 | 0.15 |

#### B. Profile = one-line English business description

| Method | P@10 | P@50 |
|---|---|---|
| Random ranking | 0.09 | 0.09 |
| TF-IDF words (baseline) | 0.16 | 0.15 |
| TF-IDF char 3-5 grams | 0.21 | 0.21 |
| Embeddings: all-MiniLM-L6-v2 | 0.21 | 0.18 |
| Embeddings: paraphrase-multilingual-MiniLM-L12-v2 | 0.21 | 0.19 |

#### Per group, setting B, P@10

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

### Reading the results honestly

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

### Decision

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
