import csv
import datetime as dt

import numpy as np
from test_match import t

from tender_radar import label

TODAY = dt.date(2026, 11, 13)


def test_queue_pools_models_and_samples_random(tmp_path, monkeypatch):
    (tmp_path / "x.yaml").write_text("name: X\ndescription: data\n", encoding="utf-8")
    tenders = [t(str(i), f"tender {i}", buyer=f"b{i}") for i in range(200)]
    # three fake models with different rankings
    monkeypatch.setattr(
        label,
        "candidate_rankers",
        lambda cands, *a: {
            "a": np.arange(len(cands), 0, -1.0),
            "b": np.arange(len(cands), dtype=float),
            "c": np.ones(len(cands)),
        },
    )
    queue, open_ = label.make_queue(tenders, tmp_path, tmp_path, TODAY)
    assert len(queue) == label.PER_PROFILE == len({q["tender_id"] for q in queue})
    pool = {q["tender_id"] for q in queue if q["source"] == "pool"}
    assert len(pool) == label.PER_PROFILE // 2
    assert {"0", "199"} <= pool  # top-1 of model a and of model b both pooled
    assert len(open_) == 200


def test_run_records_labels_and_resumes(tmp_path, monkeypatch):
    (tmp_path / "x.yaml").write_text("name: X\ndescription: data\n", encoding="utf-8")
    ts = [t("1", "a"), t("2", "b"), t("3", "c")]
    q = tmp_path / "q.csv"
    q.write_text("profile,tender_id,source\nx,1,pool\nx,2,random\nx,3,random\n", encoding="utf-8")
    out = tmp_path / "labels.csv"
    answers = iter(["?", "r", "s", "q"])  # invalid key re-prompts, skip, quit
    monkeypatch.setattr("builtins.input", lambda _: next(answers))
    label.run(ts, tmp_path, q, out)
    answers = iter(["n", "u"])  # resume: item 1 is done, 2 and 3 remain
    label.run(ts, tmp_path, q, out)
    rows = list(csv.DictReader(out.open(encoding="utf-8")))
    assert [(r["tender_id"], r["label"]) for r in rows] == [("1", "relevant"), ("2", "not_relevant"), ("3", "unsure")]
