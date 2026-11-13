from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[2]


def load(path: Path = ROOT / "config.yaml") -> dict:
    return yaml.safe_load(path.read_text(encoding="utf-8"))
