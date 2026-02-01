"""Reflog: append-only logs for HEAD and refs/heads/*."""

from __future__ import annotations

import re
import time
from pathlib import Path
from typing import TYPE_CHECKING, Optional

from .config import get_user_identity
from .util import read_text_safe, timezone_offset_utc

if TYPE_CHECKING:
    from .repo import Repository

ZEROS = "0" * 40
SHA1_HEX_LEN = 40


def reflog_path_for_ref(repo: "Repository", refname: str) -> Path:
    """Path to reflog file for ref. HEAD -> .git/logs/HEAD; refs/heads/X -> .git/logs/refs/heads/X."""
    repo.require_repo()
    if refname == "HEAD":
        return repo.git_dir / "logs" / "HEAD"
    if refname.startswith("refs/heads/"):
        return repo.git_dir / "logs" / refname
    if refname.startswith("refs/tags/"):
        return repo.git_dir / "logs" / refname
    return repo.git_dir / "logs" / refname


def append_reflog(
    repo: "Repository",
    refname: str,
    old: str,
    new: str,
    message: str,
    who: Optional[str] = None,
    timestamp: Optional[int] = None,
    tz: Optional[str] = None,
) -> None:
    """Append one reflog line. Creates log dir if missing. Line: old new who timestamp tz\\tmessage."""
    repo.require_repo()
    path = reflog_path_for_ref(repo, refname)
    path.parent.mkdir(parents=True, exist_ok=True)
    who = who or get_user_identity(repo) or "PyGit User <user@pygit.com>"
    if timestamp is None:
        timestamp = int(time.time())
    if tz is None:
        tz = timezone_offset_utc()
    msg_line = message.replace("\n", " ").replace("\r", " ").strip()
    line = f"{old} {new} {who} {timestamp} {tz}\t{msg_line}\n"
    try:
        with open(path, "a", encoding="utf-8") as f:
            f.write(line)
    except OSError:
        pass


def read_reflog(
    repo: "Repository", refname: str
) -> list[tuple[str, str, str, int, str, str]]:
    """Read reflog entries. Returns [(old, new, who, timestamp, tz, message), ...] file order (oldest first). Skips malformed lines."""
    repo.require_repo()
    path = reflog_path_for_ref(repo, refname)
    content = read_text_safe(path)
    if not content:
        return []
    result: list[tuple[str, str, str, int, str, str]] = []
    for raw in content.splitlines():
        if "\t" not in raw:
            continue
        head, msg = raw.split("\t", 1)
        parts = head.split()
        if len(parts) < 5:
            continue
        old_h, new_h = parts[0], parts[1]
        if len(old_h) != SHA1_HEX_LEN or len(new_h) != SHA1_HEX_LEN:
            continue
        if not re.fullmatch(r"[0-9a-fA-F]{40}", old_h) or not re.fullmatch(r"[0-9a-fA-F]{40}", new_h):
            continue
        try:
            ts = int(parts[-2])
        except (ValueError, IndexError):
            continue
        tz = parts[-1]
        who = " ".join(parts[2:-2])
        result.append((old_h.lower(), new_h.lower(), who, ts, tz, msg))
    return result
