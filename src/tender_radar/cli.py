import argparse
import csv
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
    open_ = build.build(tenders, ROOT / "profiles", Path(cfg["site_dir"]), method=method, doc_vecs=vecs)
    # Small, diff-friendly text snapshot that the daily workflow commits (the SQLite DB is not committed).
    cols = ["id", "published", "deadline", "country", "buyer", "cpv", "value", "currency", "value_eur", "title_en"]
    with open(ROOT / "data" / "open-tenders.csv", "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, cols, extrasaction="ignore", lineterminator="\n")
        w.writeheader()
        w.writerows(sorted(open_, key=lambda t: t["id"]))
    log.info("built site in %s with %s matcher (%d tenders)", cfg["site_dir"], method, len(tenders))
    return 0


def cmd_evaluate(cfg, args):
    from . import evaluate
    if args.labels:
        from . import evaluate_labels
        print(evaluate_labels.to_markdown(evaluate_labels.run(Path(cfg["db_path"]).parent, ROOT / "profiles")))
        return 0
    tenders = db.load(db.connect(cfg["db_path"]))
    md = evaluate.main(tenders, Path(cfg["db_path"]).parent, args.models)
    print(md)
    return 0


def _load_days(raw_dir, start, end, kind):
    out, day = [], start
    while day <= end:
        if ted.raw_path(raw_dir, day, kind).exists():
            out += ted.load_raw(raw_dir, day, kind)
        day += dt.timedelta(days=1)
    return out


def cmd_history(cfg, args):
    """Backfill award + competition notices for the backtest into history_db, then resolve winners."""
    from . import awards
    end = dt.date.today()
    a_start = end - dt.timedelta(days=cfg["history_days"])
    c_start = a_start - dt.timedelta(days=cfg["history_lead_days"])
    raw_dir = Path(cfg["raw_dir"])
    failed = []
    if not args.no_fetch:
        failed += ted.collect(a_start, end, cfg, kind="result")[1]
        failed += ted.collect(c_start, end, cfg, kind="competition")[1]
    con = db.connect(cfg["history_db"])
    db.upsert(con, clean.clean_all(_load_days(raw_dir, c_start, end, "competition")))
    raw_awards = _load_days(raw_dir, a_start, end, "result")
    wins = [w for n in raw_awards for w in awards.clean_award(n)]
    awards.store(con, wins)
    print(awards.report(con, len(raw_awards)))
    if failed:
        log.error("failed days: %s", ", ".join(map(str, sorted(failed))))
        return 1
    return 0


def cmd_profile_from_company(cfg, args):
    from . import company
    try:
        prof = company.make_profile(args.name, company.own_wins(args.name, company.search(args.name, cfg)))
    except ValueError as e:
        log.error("%s", e)
        return 1
    text = company.to_yaml(prof)
    if args.write:
        path = ROOT / "profiles" / f"{company.slugify(args.name)}.yaml"
        path.write_text(text, encoding="utf-8")
        log.info("wrote %s", path)
    else:
        sys.stdout.reconfigure(encoding="utf-8")
        print(text)
    return 0


def cmd_label(cfg, args):
    from . import label
    data = Path(cfg["db_path"]).parent
    queue_path, snap_path, labels_path = data / "label-queue.csv", data / "label-snapshot.json.gz", data / "labels.csv"
    if args.make_queue:
        if queue_path.exists() and not args.force:
            log.error("%s exists; pass --force to replace it (existing labels may no longer match)", queue_path)
            return 1
        today = dt.date.today()
        queue, open_ = label.make_queue(db.load(db.connect(cfg["db_path"])), ROOT / "profiles", data, today)
        with open(queue_path, "w", newline="", encoding="utf-8") as f:
            w = csv.DictWriter(f, label.QUEUE_COLS, lineterminator="\n")
            w.writeheader()
            w.writerows(queue)
        label.save_snapshot(snap_path, today, open_)
        log.info("wrote %d pairs to %s", len(queue), queue_path)
        return 0
    _, snapshot = label.load_snapshot(snap_path)
    label.run(snapshot, ROOT / "profiles", queue_path, labels_path)
    return 0


def main(argv=None):
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    p = argparse.ArgumentParser(prog="tender-radar")
    sub = p.add_subparsers(dest="cmd", required=True)
    u = sub.add_parser("update", help="fetch recent notices from TED into the DB")
    u.add_argument("--days", type=int, help="look back this many days (default: backfill_days)")
    sub.add_parser("build", help="generate site pages and RSS feeds")
    e = sub.add_parser("evaluate", help="CPV-based offline evaluation (prints markdown)")
    e.add_argument("--labels", action="store_true", help="evaluate on hand labels instead of the CPV proxy")
    e.add_argument("--models", nargs="*", default=[match.EMBED_MODEL, match.E5_MODEL])
    lb = sub.add_parser("label", help="hand-label (profile, tender) pairs into data/labels.csv")
    lb.add_argument("--make-queue", action="store_true", help="sample a new frozen queue of pairs")
    lb.add_argument("--force", action="store_true")
    h = sub.add_parser("history", help="backfill award notices for the backtest and resolve winners")
    h.add_argument("--no-fetch", action="store_true", help="only rebuild from the raw cache")
    pc = sub.add_parser("profile-from-company", help="build a profile YAML from a company's past TED wins")
    pc.add_argument("name")
    pc.add_argument("--write", action="store_true", help="save to profiles/<slug>.yaml instead of printing")
    args = p.parse_args(argv)
    cfg = load_config()
    for k in ("db_path", "raw_dir", "site_dir", "history_db"):
        cfg[k] = ROOT / cfg[k]
    cmds = {"update": cmd_update, "build": cmd_build, "evaluate": cmd_evaluate, "label": cmd_label,
            "history": cmd_history, "profile-from-company": cmd_profile_from_company}
    sys.exit(cmds[args.cmd](cfg, args))


if __name__ == "__main__":
    main()
