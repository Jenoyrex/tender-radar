import argparse
import datetime as dt
import logging
import sys
from pathlib import Path

from . import build, clean, db, match, ted
from .config import ROOT, load as load_config

log = logging.getLogger("tender_radar")


def cmd_update(cfg, args):
    end = dt.date.today()
    start = end - dt.timedelta(days=args.days or cfg["backfill_days"])
    fetched, failed = ted.collect(start, end, cfg)
    raw_dir = Path(cfg["raw_dir"])
    notices = []
    day = start
    while day <= end:
        if ted.raw_path(raw_dir, day).exists():
            notices += ted.load_raw(raw_dir, day)
        day += dt.timedelta(days=1)
    rows = clean.clean_all(notices)  # raises SchemaError before anything is written
    con = db.connect(cfg["db_path"])
    db.upsert(con, rows)
    total = con.execute("SELECT count(*) FROM tenders").fetchone()[0]
    log.info("fetched %d days, %d failed; %d notices in window, %d in DB", len(fetched), len(failed), len(rows), total)
    if failed:
        log.error("failed days: %s", ", ".join(map(str, failed)))
        return 1
    return 0


def cmd_build(cfg, args):
    tenders = db.load(db.connect(cfg["db_path"]))
    method = cfg.get("match_method", "tfidf")
    vecs = None
    if method == "embeddings":
        vecs = match.cached_embeddings(tenders, Path(cfg["db_path"]).parent / f"emb-{match.EMBED_MODEL}.npz")
    build.build(tenders, ROOT / "profiles", Path(cfg["site_dir"]), method=method, doc_vecs=vecs)
    log.info("built site in %s with %s matcher (%d tenders)", cfg["site_dir"], method, len(tenders))
    return 0


def cmd_evaluate(cfg, args):
    from . import evaluate
    tenders = db.load(db.connect(cfg["db_path"]))
    md = evaluate.main(tenders, Path(cfg["db_path"]).parent, args.models)
    print(md)
    return 0


def main(argv=None):
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    p = argparse.ArgumentParser(prog="tender-radar")
    sub = p.add_subparsers(dest="cmd", required=True)
    u = sub.add_parser("update", help="fetch recent notices from TED into the DB")
    u.add_argument("--days", type=int, help="look back this many days (default: backfill_days)")
    sub.add_parser("build", help="generate site pages and RSS feeds")
    e = sub.add_parser("evaluate", help="CPV-based offline evaluation (prints markdown)")
    e.add_argument("--models", nargs="*", default=["all-MiniLM-L6-v2", match.EMBED_MODEL])
    args = p.parse_args(argv)
    cfg = load_config()
    for k in ("db_path", "raw_dir", "site_dir"):
        cfg[k] = ROOT / cfg[k]
    sys.exit({"update": cmd_update, "build": cmd_build, "evaluate": cmd_evaluate}[args.cmd](cfg, args))


if __name__ == "__main__":
    main()
