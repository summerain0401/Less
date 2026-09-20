import hashlib
import os
import tempfile
from pathlib import Path

from less.config import settings


def save_blob(content: bytes) -> str:
    digest = hashlib.sha256(content).hexdigest()
    relative = Path("snapshots") / digest[:2] / digest
    target = settings().data_dir / relative
    target.parent.mkdir(parents=True, exist_ok=True)
    if not target.exists():
        fd, tmp = tempfile.mkstemp(dir=target.parent)
        try:
            with os.fdopen(fd, "wb") as out:
                out.write(content)
                out.flush()
                os.fsync(out.fileno())
            os.replace(tmp, target)
        finally:
            if os.path.exists(tmp):
                os.unlink(tmp)
    return str(relative)


def read_blob(relative: str) -> bytes:
    root = settings().data_dir.resolve()
    path = (root / relative).resolve()
    if not path.is_relative_to(root):
        raise ValueError("Invalid snapshot path")
    content = path.read_bytes()
    if hashlib.sha256(content).hexdigest() != path.name:
        raise ValueError("Snapshot checksum mismatch")
    return content
