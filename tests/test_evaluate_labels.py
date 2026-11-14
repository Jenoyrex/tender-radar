from tender_radar import evaluate_labels as E


def test_precision_condensed_list():
    judged = {"a": "relevant", "b": "not_relevant", "c": "unsure"}
    ranked = ["x", "a", "y", "c", "b"]  # x, y unjudged: skipped
    assert E.precision(ranked, judged, 2, lenient=False) == 0.5
    assert E.precision(ranked, judged, 2, lenient=True) == 0.75
    assert E.precision(ranked, judged, 10, lenient=False) == 0.1  # divide by k, not by judged count


def test_split_is_stratified_and_deterministic():
    queue = [{"profile": "p", "tender_id": str(i), "source": "pool" if i < 10 else "random"} for i in range(20)]
    labels = {("p", str(i)): "relevant" for i in range(20) if i != 3}  # one unjudged
    s1, s2 = E.split(queue, labels), E.split(queue, labels)
    assert s1 == s2 and ("p", "3") not in s1
    for src in ("pool", "random"):
        parts = [s1[("p", q["tender_id"])] for q in queue if q["source"] == src and ("p", q["tender_id"]) in s1]
        assert abs(parts.count("dev") - parts.count("test")) <= 1


def test_human_labels_override(tmp_path):
    (tmp_path / "labels-claude.csv").write_text(
        "profile,tender_id,label,labelled_at\np,1,not_relevant,x\np,2,unsure,x\n", encoding="utf-8"
    )
    (tmp_path / "labels.csv").write_text("profile,tender_id,label,labelled_at\np,1,relevant,x\n", encoding="utf-8")
    assert E.read_labels(tmp_path) == {("p", "1"): "relevant", ("p", "2"): "unsure"}
