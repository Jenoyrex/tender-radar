import ast
from pathlib import Path

import pytest

from tender_radar import util

ROOT = Path(__file__).resolve().parents[1]


def test_write_text_replaces_and_is_utf8(tmp_path):
    p = tmp_path / "sub" / "a.txt"
    util.write_text(p, "Zürich – Łódź")
    util.write_text(p, "Ελλάδα")
    assert p.read_bytes() == "Ελλάδα".encode()
    assert [x.name for x in p.parent.iterdir()] == ["a.txt"]  # no temp files left behind


def test_failed_write_keeps_the_original(tmp_path):
    p = tmp_path / "a.txt"
    util.write_text(p, "original")
    with pytest.raises(RuntimeError), util.atomic_path(p) as tmp:
        tmp.write_text("half", encoding="utf-8")
        raise RuntimeError("disk full halfway")
    assert p.read_text(encoding="utf-8") == "original"
    assert [x.name for x in tmp_path.iterdir()] == ["a.txt"]

    with pytest.raises(TypeError):  # write_text itself failing
        util.write_text(p, object())
    assert p.read_text(encoding="utf-8") == "original"


TEXT_CALLS = {"open", "read_text", "write_text"}


def _missing_encoding(tree: ast.AST):
    """Calls to open()/.open()/.read_text()/.write_text() in text mode without encoding=."""
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        f = node.func
        name = f.id if isinstance(f, ast.Name) else f.attr if isinstance(f, ast.Attribute) else None
        if name not in TEXT_CALLS:
            continue
        owner = f.value.id if isinstance(f, ast.Attribute) and isinstance(f.value, ast.Name) else None
        if owner in ("gzip", "urllib", "np", "os", "util"):  # binary, network, or our UTF-8 helper
            continue
        kw = {k.arg for k in node.keywords}
        if "encoding" in kw:
            continue
        mode_args = [a for a in node.args[1:2] if isinstance(a, ast.Constant)] + [
            k.value for k in node.keywords if k.arg == "mode" and isinstance(k.value, ast.Constant)
        ]
        if any("b" in str(m.value) for m in mode_args):
            continue
        yield node.lineno


@pytest.mark.parametrize(
    "path", sorted((ROOT / "src").rglob("*.py")) + sorted((ROOT / "tests").rglob("*.py")), ids=lambda p: str(p.relative_to(ROOT))
)
def test_all_text_io_names_an_encoding(path):
    tree = ast.parse(path.read_text(encoding="utf-8"))
    assert list(_missing_encoding(tree)) == [], f"{path.name}: text I/O without encoding= at these lines"


def test_the_encoding_check_catches_offenders():
    bad = "from pathlib import Path\nopen('a')\np.read_text()\n(t / 'x').write_text('y')\nopen('a', 'rb')\n"
    assert list(_missing_encoding(ast.parse(bad))) == [2, 3, 4]
