"""Helper functions: safe file ops, read/write bytes, time/tz, hashing."""

from __future__ import annotations

import hashlib
import os
import tempfile
import time
from pathlib import Path
from typing import Optional


def sha1_hash(data: bytes) -> str:
    """Compute SHA-1 hex digest of data."""
    return hashlib.sha1(data).hexdigest()


def read_bytes(path: Path) -> bytes:
    """Read file as bytes. Raises FileNotFoundError if not found."""
    return path.read_bytes()


def write_bytes_atomic(path: Path, data: bytes) -> None:
    """Write bytes to file atomically (temp then replace)."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=path.parent, prefix=".tmp_")
    try:
        os.write(fd, data)
        os.close(fd)
        os.replace(tmp, path)
    except Exception:
        try:
            os.close(fd)
        except OSError:
            pass
        if os.path.exists(tmp):
            os.unlink(tmp)
        raise


def write_bytes(path: Path, data: bytes) -> None:
    """Write bytes to file. Uses atomic write (temp then rename). Alias for write_bytes_atomic."""
    write_bytes_atomic(path, data)


def write_text_atomic(path: Path, text: str) -> None:
    """Write text to file atomically."""
    write_bytes(path, text.encode("utf-8"))


def read_text_safe(path: Path) -> Optional[str]:
    """Read file as text; return None if not found or error."""
    try:
        return path.read_text(encoding="utf-8")
    except (FileNotFoundError, OSError):
        return None


def timezone_offset_utc() -> str:
    """Return local timezone offset as string e.g. +0530 or -0800."""
    if time.daylight:
        offset_sec = -time.altzone
    else:
        offset_sec = -time.timezone
    sign = "+" if offset_sec >= 0 else "-"
    abs_sec = abs(offset_sec)
    hours = abs_sec // 3600
    minutes = (abs_sec % 3600) // 60
    return f"{sign}{hours:02d}{minutes:02d}"


def timestamp_with_tz(timestamp: Optional[int] = None) -> tuple[int, str]:
    """Return (timestamp, tz_offset). Uses current time if timestamp is None."""
    ts = int(time.time()) if timestamp is None else timestamp
    return ts, timezone_offset_utc()


def timestamp_from_env(kind: str) -> Optional[tuple[int, str]]:
    """Read GIT_AUTHOR_DATE or GIT_COMMITTER_DATE from env. kind is 'AUTHOR' or 'COMMITTER'.
    Accepts '1234567890 +0000' (unix timestamp + offset). Returns (ts, tz) or None."""
    key = f"GIT_{kind}_DATE"
    val = os.environ.get(key)
    if not val or not val.strip():
        return None
    parts = val.strip().split(None, 1)
    if len(parts) < 2:
        return None
    try:
        ts = int(parts[0])
        tz = parts[1] if len(parts) > 1 else "+0000"
        return (ts, tz)
    except ValueError:
        return None


def normalize_path(repo_root: Path, path: str) -> Path:
    """Resolve path relative to repo root; reject paths escaping root."""
    repo_root = repo_root.resolve()
    resolved = (repo_root / path).resolve()
    try:
        resolved.relative_to(repo_root)
    except ValueError:
        raise ValueError(f"path escapes repository: {path}") from None
    return resolved


def is_executable(path: Path) -> bool:
    """Return True if file has executable bit set (for mode 100755)."""
    try:
        st = path.stat()
        return (st.st_mode & 0o111) != 0
    except OSError:
        return False


def is_binary(data: bytes) -> bool:
    """Heuristic: treat as binary if contains null or many non-printable bytes."""
    if b"\0" in data:
        return True
    non_printable = sum(1 for b in data[:8000] if b < 32 and b not in (9, 10, 13))
    return non_printable > len(data[:8000]) // 4
