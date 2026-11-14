# Evaluation

## Main evaluation: award-notice backtest (2026-11-14)

**The question:** if a company had used tender-radar, would the tender it went on
to win have been near the top of its list?

**Short answer: yes, often.** The shipped matcher put the tender a company
actually won next in its top 10 for **52%** of 713 held-out companies (random
order: 14%; ranking by "same main CPV code as past wins": 22%), and in its top 50
for **78%**. A blend with multilingual-e5 scored 2 points higher on the test half,
but the 95% confidence interval of that gain includes zero, so **the shipped
matcher stays: character 3-5-gram TF-IDF + a 0.1 CPV boost.**

This replaces the earlier evaluations (below) as the main one: it uses real
behaviour (who won what) instead of a CPV proxy or one AI labeller's opinion.

### Method

Data (`tender-radar history`, see [data-source.md](data-source.md)): every CPV-72
**contract award notice** published on TED from 2024-11-14 to 2026-11-14 (45,190),
and every CPV-72 **contract notice** from 2024-05-18 (68,226), so awards can be
linked back to the call for tender they answered.

1. **Who won what.** Winner names are normalised and grouped into companies
   ([entity-sample.md](entity-sample.md) has the rules and a hand-checked sample).
2. **Link** each award to its contract notice through `procedure-identifier`.
3. **Cases.** For every company with 4+ wins (distinct procedures):
   - *held-out tender* = its latest win that links to a contract notice;
   - *d* = the date that contract notice was first published;
   - *profile* = built exactly like the product's "profile from company name"
     (`company.profile_from_rows`): titles + description starts of the company's
     other wins **published before d** (never the same procedure), its countries
     and top CPV prefixes. At least 3 such wins are required.
4. **Pool** = every contract notice open on *d* (published on or before *d*,
   deadline on or after *d*; notices without a deadline count as open for 60
   days), newest version per (buyer, title), then the product's own filters for
   that profile. If the filters remove the held-out tender, that case is a miss.
5. **Rank** the pool with each matcher and record the held-out tender's rank
   (ties: expected rank). Metrics: hit@10, hit@50, median rank.
6. **Split** companies 50/50 into dev and test (fixed seed). The blend weight and
   the matcher are chosen on dev; test is read once, for the decision.
   Uncertainty: 95% percentile bootstrap over companies (2,000 resamples).

Reproduce: `tender-radar history` (≈1.5 h of polite fetching), then
`tender-radar backtest` (≈50 min, mostly embedding 34k notices with e5 on CPU;
`--no-e5` takes ≈5 min). Results: `data/backtest-results.json`.

### Funnel

| | Companies |
|---|---|
| With 4+ wins | 2,555 |
| … dropped: fewer than 3 wins published before the held-out tender | 957 |
| … dropped: no win links to a contract notice in our history | 171 |
| **Usable cases** | **1,427** (714 dev, 713 test) |

### Results

#### DEV half: 714 companies, median pool 139 open notices; country filter removed the held-out tender in 16 cases (2%)

| Matcher | hit@10 | hit@50 | median rank |
|---|---|---|---|
| Blend 0.75 × char-TF-IDF + 0.25 × e5 (z-scores) ← chosen on dev | 0.555 | 0.801 | 8 |
| Char 3-5-gram TF-IDF, no CPV boost | 0.531 | 0.798 | 8 |
| **Char 3-5-gram TF-IDF + CPV boost (shipped)** | 0.518 | 0.791 | 10 |
| Word TF-IDF on English title template + CPV labels | 0.506 | 0.776 | 10 |
| multilingual-e5-small | 0.424 | 0.742 | 15 |
| Baseline: same main CPV code as past wins | 0.202 | 0.567 | 34 |
| Baseline: random order | 0.099 | 0.451 | 59 |

#### TEST half: 713 companies, median pool 136 open notices; country filter removed the held-out tender in 18 cases (3%)

| Matcher | hit@10 | hit@50 | median rank |
|---|---|---|---|
| Blend 0.75 × char-TF-IDF + 0.25 × e5 (chosen on dev) | 0.544 | 0.791 | 8 |
| Char 3-5-gram TF-IDF, no CPV boost | 0.536 | 0.783 | 9 |
| **Char 3-5-gram TF-IDF + CPV boost (shipped)** | **0.525** | **0.776** | **9** |
| Word TF-IDF on English title template + CPV labels | 0.473 | 0.764 | 12 |
| multilingual-e5-small | 0.442 | 0.752 | 14 |
| Baseline: same main CPV code as past wins | 0.216 | 0.564 | 38 |
| Baseline: random order | 0.136 | 0.502 | 50 |

Differences in hit@10 on the test half (95% bootstrap CI, resampling companies):

| Comparison | Difference | 95% CI | Clear? |
|---|---|---|---|
| Shipped − random | +0.388 | +0.345 to +0.431 | yes |
| Shipped − same main CPV | +0.309 | +0.269 to +0.346 | yes |
| Blend (chosen on dev) − shipped | +0.020 | −0.003 to +0.043 | **no**: the interval includes 0 |

By company size (TED's `winner-size`, most common value per company; dev + test,
shipped matcher):

| Size | Companies | hit@10 | hit@50 | Random hit@10 | Median pool |
|---|---|---|---|---|---|
| micro / small | 112 | 0.57 | 0.86 | 0.21 | 77 |
| medium | 157 | 0.63 | 0.89 | 0.19 | 58 |
| SME (unspecified) | 243 | 0.57 | 0.84 | 0.15 | 110 |
| large | 416 | 0.40 | 0.67 | 0.10 | 208 |
| not stated | 499 | 0.55 | 0.81 | 0.08 | 122 |

### Decision

**Keep the shipped matcher.** The rule was: ship a challenger only if it clearly
beats the current matcher on the test half. The dev-chosen blend gains +0.020
hit@10 with a confidence interval that crosses zero, and it would add PyTorch and
a ~470 MB model download (measured) to a daily job that now runs in 3 minutes on the free tier. The
CPV boost itself is not clearly useful either (no boost: 0.536 vs 0.525), but
the difference is smaller still; it stays because it is visible in each result's
reasons and helps profiles that only have a short description.

Both baselines are beaten clearly, so the ranking does real work: on a typical
day's list of ~136 open tenders in the company's countries, the tender it later
won was in the top 10 about half the time.

### Stress tests (2026-11-14, round 2)

Three questions the headline number cannot answer on its own. Same 1,427 companies
and dev/test split; no e5 (`tender-radar backtest --no-e5 --variant …`).

**1. How much is repeat business?** For 396 of the 1,427 companies (28%), the
held-out tender's buyer had already awarded the company a contract in its history
(buyer names compared after normalisation). Those are easy: same buyer, often a
near-identical title.

| Held-out tender's buyer (dev + test) | Companies | Shipped hit@10 | Same-CPV hit@10 | Random hit@10 | Shipped hit@50 |
|---|---|---|---|---|---|
| Already awarded this company a contract (repeat) | 396 | 0.682 | 0.374 | 0.179 | 0.884 |
| New to this company | 1,031 | 0.460 | 0.145 | 0.094 | 0.745 |

Repeat business does inflate the headline, but for **new buyers** the matcher
still puts the won tender in the top 10 for 46% of companies, +0.37 over random
(95% CI +0.33 to +0.40).

**2. Europe-wide lists.** The headline lists are short because the profile only
keeps the countries of the company's past wins. With no country filter, every open
CPV-72 notice in Europe is in the pool:

| TEST half, Europe-wide pool (median 2,243 open notices) | hit@10 | hit@50 | median rank |
|---|---|---|---|
| Char TF-IDF, no CPV boost | 0.477 | 0.722 | 12 |
| **Shipped** | **0.468** | **0.711** | 13 |
| Word TF-IDF on English title template + CPV labels (chosen on dev) | 0.447 | 0.703 | 15 |
| Baseline: same main CPV code | 0.041 | 0.122 | 766 |
| Baseline: random order | 0.007 | 0.020 | 1,137 |

With 16 times more candidates, hit@10 only drops from 0.525 to 0.468, while random
falls to under 1%: shipped − random +0.461 (95% CI +0.424 to +0.498). For new buyers
it is 0.388 (repeat buyers 0.659). The short headline lists were not doing most of
the work; the text match was. The English-label TF-IDF won on dev here but is
2 points worse on test (CI −0.059 to +0.015), so it would not be shipped either.

**3. Cold start.** A newcomer has no history and types a few sentences. The closest
test available is a profile built from **one** earlier win (its title and the start of
its description) instead of all of them:

| TEST half, profile from one past win | hit@10 | hit@50 | median rank |
|---|---|---|---|
| **Shipped** | **0.419** | **0.687** | 17 |
| Char TF-IDF, no CPV boost | 0.405 | 0.689 | 18 |
| Word TF-IDF on English title template + CPV labels | 0.318 | 0.631 | 27 |
| Baseline: same main CPV code | 0.140 | 0.471 | 58 |
| Baseline: random order | 0.140 | 0.508 | 49 |

A thin profile loses about 11 points of hit@10 (0.525 → 0.419) but stays far above
both baselines (+0.28 over each; 95% CIs +0.24 to +0.32). For new buyers it is 0.36.
This is still a profile made of a real tender's words, not a person's own
description, so it is an optimistic stand-in for a first-time user.

### Limitations (read before quoting the 52%)

- **Easier than real life in one way: small pools.** The profile's countries come
  from the company's own past wins, so the pool is usually one or two countries
  (median 136 notices). Random order already gets 14% in the top 10. Europe-wide
  lists are measured in the stress tests above.
- **Harder than real life in another: one right answer.** Only the tender the
  company actually won counts. Other tenders in its top 10 that it could have won
  (or bid on and lost) count as misses. The numbers are a lower bound on
  "useful suggestions" and say nothing about precision.
- **Repeat business.** Companies often win follow-up contracts from the same buyer
  with near-identical titles. Measured above: 28% of cases; top 10 for 68% of
  repeat cases vs 46% for new buyers.
- **Name matching.** Entity resolution is rule-based (see [entity-sample.md](entity-sample.md):
  19 of 20 sampled groups are one firm, 1 is one corporate group). Missed merges
  shrink a company's history; wrong merges mix two firms' profiles.
- **Missing links.** Only 66% of award notices link back to a contract notice we
  have (older notices, pre-eForms or national-only procedures). Companies whose
  wins never link are excluded.
- **Winners skew large.** Companies with 4+ wins are more often large firms (29%
  vs 16% of all winners) and less often micro/small (8% vs 15%), the opposite of
  the product's audience. Large firms are where the matcher does worst (0.40),
  micro/small firms are near the average (0.57), but on only 112 companies.
- **Only winners.** Companies that bid and never won, or never bid, are invisible
  to TED, so the backtest cannot say how the product works for a first-time bidder
  who only types a description.
- **Profiles from wins, not descriptions.** The backtest profile is built from past
  winning notices (same as "profile from company name"), not from the few sentences
  a person would type. The one-win stress test above is the closest proxy (0.42);
  the earlier evaluations below cover typed descriptions, weakly.

### Entity resolution numbers

From `tender-radar history` on the same data:

| | |
|---|---|
| Award notices (CPV 72), 2024-11-14 to 2026-11-14 | 45,190 |
| … naming at least one winner | 40,929 (91%) |
| … linked to their contract notice via `procedure-identifier` | 26,718 (65%) |
| … carrying `previous-notice-id-proc` | 18,251 (45%); found in our history: 5,971 |
| … linked by either route | 27,069 (66%) |
| (notice, winner) rows | 59,516, of which 43,103 (72%) with a usable national ID |
| Distinct raw winner names (per country) | 26,691 |
| Distinct normalised names (per country) | 22,262 |
| **Companies** after entity resolution | **23,312** |
| Companies with 4+ wins (distinct procedures) | **2,555** |
| … with 4+ wins linked to a contract notice | **1,751** |

"Companies" exceeds "normalised names" because names of 4 characters or fewer are
split by national ID, and the same name with and without a winner country counts
once per country. The brief's gate (at least 100 companies with 4+ wins) passes
by a wide margin, so no widening to other CPV codes or to 3+ wins was needed.

---

## Earlier evaluations (secondary)

Both earlier rounds measured the matcher against weaker ground truth. They reached
the same decision (keep character TF-IDF) and are kept in short form. The full
version with all tables is in git history
([docs/evaluation.md at 7942573](https://github.com/Jenoyrex/tender-radar/blob/7942573/docs/evaluation.md)).

### Round 2 (2026-11-13): 150 labelled (profile, tender) pairs

- 50 pairs per example profile, half pooled from the candidate models' top-20s,
  half random. **144 of the 150 labels were made by an AI (Claude), 6 by a human.**
  On the 6 pairs both labelled, they agreed on 2, and Claude had seen the human
  answers first. Positives were rare (17 relevant, 21 unsure). Treat it as one
  labeller's opinion, not ground truth.
- Held-out split 50/50 per profile; model chosen on dev.

TEST half, precision@10 over judged tenders:

| Model | P@10 strict | P@10 lenient |
|---|---|---|
| Share relevant among judged (random baseline) | 0.14 | 0.20 |
| Char 3-5-gram TF-IDF (current) | 0.27 | 0.35 |
| TF-IDF on English title + CPV labels (chosen on dev) | 0.27 | 0.33 |
| multilingual-e5-small | 0.23 | 0.32 |
| Blend 0.5 char-TF-IDF + 0.5 e5 | 0.23 | 0.32 |

Decision then: nothing clearly beat the current model; keep it.
Reproduce: `tender-radar evaluate --labels`.

### Round 1 (2026-11-13): CPV codes as weak ground truth

A profile built from one CPV group's tenders (A) or one English sentence about the
group (B) should pull that group's tenders to the top; the matcher never sees CPV
codes. Precision@10 averaged over 11 IT sub-sectors, 5,414 tenders:

| Method | A: 10 sampled tenders | B: one sentence |
|---|---|---|
| Random ranking | 0.09 | 0.09 |
| TF-IDF words | 0.25 | 0.16 |
| TF-IDF character 3-5-grams (shipped) | 0.22 | 0.21 |
| all-MiniLM-L6-v2 (English) | 0.20 | 0.21 |
| paraphrase-multilingual-MiniLM-L12-v2 | 0.15 | 0.21 |

All methods were only 2–3× better than random and no embedding model beat TF-IDF,
so the site shipped character n-gram TF-IDF, which handles 20+ languages without
PyTorch. Reproduce: `tender-radar evaluate`.
