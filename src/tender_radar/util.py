"""Safe file writing: always UTF-8, and never leave a half-written file behind.

Writes go to a temp file in the same directory, which then replaces the target with
os.replace (atomic on POSIX and Windows). If anything fails mid-write, the original
file is untouched and the temp file is removed.
"""

import os
import tempfile
from contextlib import contextmanager
from pathlib import Path


@contextmanager
def atomic_path(path):
    """Yield a temp path next to `path`; on success it replaces `path`, on error it is deleted."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=path.parent, prefix=f".{path.name}.", suffix=".tmp")
    os.close(fd)
    try:
        yield Path(tmp)
        os.replace(tmp, path)
    except BaseException:
        Path(tmp).unlink(missing_ok=True)
        raise


def write_text(path, text: str) -> None:
    with atomic_path(path) as tmp:
        tmp.write_text(text, encoding="utf-8")
