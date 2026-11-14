# Loop log

One line per ticked item: item | what changed | how verified.

- B1 | added company.py + `tender-radar profile-from-company NAME [--write]` (live TED winner-name search, normalised-name equality filter) | tests/test_company_profile.py (5 pass); real run for 'Esri Polska' (18 wins) and 'Tekies s.r.o.' (40)
- B4 | feedback.py + `tender-radar feedback` → data/feedback.csv (no usernames), step in daily.yml (continue-on-error) | tests/test_feedback.py (3 pass, incl. round trip with build.feedback_url); live run against GitHub API: 0 feedback issues so far
- D2 | util.atomic_path/write_text (temp file + os.replace) for every writer in src; encoding="utf-8" on all text I/O incl. tests; PYTHONUTF8=1 in all 3 workflows; ruff PLW1514 (preview, explicit) | ruff check passes and flags a probe file; tests/test_util.py: AST check over every src/tests file + failed-write-keeps-original tests; 128 pass
- D1 | db.ensure_columns (ALTER TABLE ADD COLUMN) replaces DROP TABLE in db.connect; awards.store migrates wins the same way and refreshes in one transaction (was executescript = implicit commit) | tests/test_db.py: old-schema tenders + wins DBs with rows survive and gain columns; failed refresh keeps old rows; 132 pass
- D3 | signup.check_limits (cap 200, 20/day, account ≥7 days, 1 active feed per user via their sign-up issues) + signup.handle; workflow now sweeps all open requests oldest-first in one concurrency group, 6-hourly sweep, retrying rebase push; README 'Sign-up limits' | pytest -k limit: 5 pass (one per limit + burst-in-one-sweep); all 140 pass; workflow YAML parses. Live run pending merge (B2)
- A1 | 2-year award + 2.5-year contract-notice backfill (history_days/history_lead_days in config.yaml); index on tenders.procedure_id (report went from >10 min to 54 s) | every day in both windows cached (0 missing), history.sqlite: 68,226 contract notices, 59,516 (notice, winner) rows; no ERROR lines in the fetch log (one IncompleteRead retried successfully)
