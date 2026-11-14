# Definition of done

Each item is ticked only after its check has been run and passed. `py` below is
`.venv/Scripts/python.exe` locally (`python` in CI).

## A. Award backtest
- [x] **A1** Award + contract-notice backfill complete; `data/history.sqlite` exists.
  Check: `tender-radar history --no-fetch` prints the report; no "failed days" line; days cached = days in window.
- [x] **A2** Entity report (distinct winners, companies with 4+ wins); gate ≥100 companies with 4+ linked wins
  (else widen and record); `docs/entity-sample.md` has 20 random groups, ≤2 of 20 judged wrongly merged.
  Check: report output pasted in docs/evaluation.md; my verdict per group written in entity-sample.md.
- [ ] **A3** Backtest: profile = all wins but the latest; pool = notices open on the held-out notice's
  publication date, product filters; hit@10, hit@50, median rank for char-TF-IDF, English TF-IDF, e5, blend,
  random, same-main-CPV; dev/test split by company. Check: `tender-radar backtest` prints both tables; `pytest tests/test_backtest.py`.
- [ ] **A4** New matcher shipped only if it clearly beats current on test, with bootstrap 95% CI on the difference.
  Check: CI printed in evaluation.md; `config.yaml` / `match.py` agree with the decision.
- [ ] **A5** docs/evaluation.md: backtest is the main section, label results secondary, limitations listed.
  Check: read the file top to bottom.
- [x] **A6** award-backtest merged into main after tests + CI pass.
  Check: `gh run list --branch award-backtest` green; `git log main` contains the merge.

## B. Product
- [x] **B1** Profile from company name. Check: `tender-radar profile-from-company "<name>"` prints YAML; `pytest tests/test_company_profile.py`.
- [x] **B2** Issue-form sign-up → Action validates, writes `profiles/<slug>.yaml`, builds, comments links, closes; rejects invalid/spam.
  Check: `pytest tests/test_signup.py`; a real test issue on GitHub gets a comment and is closed.
- [x] **B3** Removal via issue form → profile deleted. Check: `pytest tests/test_signup.py -k remove`; real issue closes the test profile.
- [x] **B4** Feedback issues → `data/feedback.csv` + counts; in the daily workflow.
  Check: `pytest tests/test_feedback.py`; `tender-radar feedback` runs against GitHub; step present in daily.yml.
- [ ] **B5** Home page explains what/who/how to sign up and shows the backtest headline.
  Check: open the built `site/index.html` and read it.

## C. Quality
- [ ] **C1** All tests pass locally and in CI; every new module has tests. Check: `py -m pytest`; `gh run list -w tests` green.
- [ ] **C2** Daily workflow green end to end; runtime recorded in README. Check: `gh run list -w daily`; `gh run view` timing.
- [x] **C3** `ruff check` and `ruff format --check` pass, run in CI. Check: both commands; tests.yml step.
- [x] **C4** Live site: index, every profile page and feed load, no broken links, fits 375px; link checker in CI.
  Check: `py -m tender_radar.linkcheck https://jenoyrex.github.io/tender-radar/`; 375px screenshot.
- [ ] **C5** README final (pitch, live link, screenshot, diagram, headline, sign-up, local run, attribution, limitations, licence).
  Check: read README against this list; image file exists.
- [ ] **C6** docs/WRITEUP.md, 600–900 words, honest. Check: word count; read it.
- [ ] **C7** v1.0.0 release with notes. Check: `gh release view v1.0.0`.

## D. Robustness (added 2026-11-14)
- [x] **D1** Non-destructive schema changes: `db.connect` never drops a table with data (ALTER TABLE ADD COLUMN);
  same for history.sqlite. Check: `pytest tests/test_db.py` opens an old-schema DB with rows, rows survive.
- [x] **D2** UTF-8 everywhere: explicit `encoding="utf-8"` on all text I/O, `PYTHONUTF8=1` in workflows, a ruff rule
  catching missing encodings, atomic writes (temp file + rename). Check: `ruff check` with the rule enabled;
  `pytest tests/test_util.py` (failed write leaves the original intact); grep of workflows.
- [x] **D3** Sign-up abuse limits: 1 active profile per GitHub user, ≤20 new sign-ups/day, hard cap 200, issue author
  account ≥7 days old, concurrency group (no racing commits). Check: `pytest tests/test_signup.py -k limit`; README section.

## Blocked
(none yet)
