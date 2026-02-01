"""Staging area: Git binary index (DIRC v2) with JSON migration."""

from __future__ import annotations

import hashlib
import json
import os
import struct
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict

from .constants import INDEX_FILENAME, MODE_FILE, MODE_FILE_EXECUTABLE
from .errors import IndexChecksumError, IndexCorruptError
from .util import read_text_safe, write_bytes, is_executable

INDEX_CHECKSUM_LEN = 20


DIRC_SIGNATURE = b"DIRC"
INDEX_VERSION_BINARY = 2
FLAGS_NAME_MASK = 0x0FFF  # low 12 bits for name length; 0xFFF = name in extended
MAX_NAME_IN_FLAGS = 0xFFF


@dataclass
class IndexEntry:
    """Single index entry (internal)."""
    path: str
    sha1: str
    mode: str
    size: int
    mtime_ns: int
    ctime_ns: int = 0
    dev: int = 0
    ino: int = 0
    uid: int = 0
    gid: int = 0


def _index_path(repo_git: Path) -> Path:
    return repo_git / INDEX_FILENAME


def _mode_to_int(mode: str) -> int:
    """Git mode string (e.g. 100644) to u32 (octal)."""
    return int(mode, 8)


def _mode_from_int(m: int) -> str:
    """u32 to Git mode string (e.g. 100644, 040000)."""
    if m <= 0:
        return MODE_FILE
    s = f"{m:o}"
    if len(s) == 5 and s.startswith("10"):
        return s  # 100644, 100755
    if len(s) == 5 and s.startswith("4"):
        return "0" + s  # 40000 -> 040000
    return s.zfill(6) if len(s) <= 6 else MODE_FILE


def _read_dirc(repo_git: Path) -> Dict[str, Dict[str, Any]]:
    """Read binary DIRC v2 index; return {path: {sha1, mode, size, mtime_ns}}. Verifies trailing SHA-1 checksum when present; validates entry order."""
    path = _index_path(repo_git)
    data = path.read_bytes()
    if len(data) < 12:
        return {}
    sig = data[:4]
    if sig != DIRC_SIGNATURE:
        return {}
    # Checksum: if file has at least 32 bytes, last 20 must be SHA-1 of preceding content
    if len(data) >= 32:
        body = data[:-INDEX_CHECKSUM_LEN]
        stored = data[-INDEX_CHECKSUM_LEN:]
        if hashlib.sha1(body).digest() != stored:
            raise IndexChecksumError("index checksum mismatch")
    else:
        body = data
    version, count = struct.unpack(">II", body[4:12])
    if version != INDEX_VERSION_BINARY:
        return {}
    result: Dict[str, Dict[str, Any]] = {}
    path_order: list[str] = []
    pos = 12
    for _ in range(count):
        if pos + 62 > len(body):
            raise IndexCorruptError("index truncated or corrupt")
        entry_start = pos
        ctime_s, ctime_ns = struct.unpack(">II", body[pos : pos + 8])
        pos += 8
        mtime_s, mtime_ns = struct.unpack(">II", body[pos : pos + 8])
        pos += 8
        dev, ino = struct.unpack(">II", body[pos : pos + 8])
        pos += 8
        mode, uid, gid = struct.unpack(">III", body[pos : pos + 12])
        pos += 12
        size = struct.unpack(">I", body[pos : pos + 4])[0]
        pos += 4
        sha1_bin = body[pos : pos + 20]
        pos += 20
        flags = struct.unpack(">H", body[pos : pos + 2])[0]
        pos += 2
        name_len = flags & FLAGS_NAME_MASK
        if name_len == MAX_NAME_IN_FLAGS:
            null_idx = body.find(b"\0", pos)
            if null_idx == -1 or null_idx >= len(body):
                raise IndexCorruptError("index truncated or corrupt")
            path_bytes = body[pos:null_idx]
            pos = null_idx + 1
        else:
            path_bytes = body[pos : pos + name_len]
            pos += name_len + 1  # NUL
        path_str = path_bytes.decode("utf-8")
        path_order.append(path_str)
        mtime_ns = mtime_s * 1_000_000_000 + mtime_ns
        ctime_ns_val = ctime_s * 1_000_000_000 + ctime_ns
        result[path_str] = {
            "sha1": sha1_bin.hex(),
            "mode": _mode_from_int(mode),
            "size": size,
            "mtime_ns": mtime_ns,
            "ctime_ns": ctime_ns_val,
        }
        # Align to 8-byte boundary (writer pads each entry to 8 bytes)
        consumed = pos - entry_start
        pos = entry_start + ((consumed + 7) // 8) * 8
    # Git requires entries sorted by path
    if path_order != sorted(path_order):
        raise IndexCorruptError("index entries not sorted by path")
    return result


def _write_dirc(repo_git: Path, entries: Dict[str, Dict[str, Any]]) -> None:
    """Write binary DIRC v2 index (atomic)."""
    path = _index_path(repo_git)
    chunks = [DIRC_SIGNATURE, struct.pack(">II", INDEX_VERSION_BINARY, len(entries))]
    for path_str in sorted(entries.keys()):
        ent = entries[path_str]
        sha1_hex = ent.get("sha1", "")
        mode_str = ent.get("mode", MODE_FILE)
        size = int(ent.get("size", 0))
        mtime_ns = int(ent.get("mtime_ns", 0))
        ctime_ns = int(ent.get("ctime_ns", 0))
        mtime_s, mtime_nsec = divmod(mtime_ns, 1_000_000_000)
        ctime_s, ctime_nsec = divmod(ctime_ns, 1_000_000_000)
        mode = _mode_to_int(mode_str)
        sha1_bin = bytes.fromhex(sha1_hex) if len(sha1_hex) == 40 else b"\0" * 20
        path_bytes = path_str.encode("utf-8")
        name_len = min(len(path_bytes), MAX_NAME_IN_FLAGS)
        flags = name_len
        entry = (
            struct.pack(">II", ctime_s, ctime_nsec)
            + struct.pack(">II", mtime_s, mtime_nsec)
            + struct.pack(">II", 0, 0)  # dev, ino
            + struct.pack(">III", mode, 0, 0)  # uid, gid
            + struct.pack(">I", size)
            + sha1_bin
            + struct.pack(">H", flags)
            + path_bytes
            + b"\0"
        )
        while len(entry) % 8 != 0:
            entry += b"\0"
        chunks.append(entry)
    content = b"".join(chunks)
    write_bytes(path, content + hashlib.sha1(content).digest())


def _parse_json_entries(data: Dict[str, Any]) -> Dict[str, Dict[str, Any]]:
    """Normalize JSON index to {path: {sha1, mode, size, mtime_ns}}."""
    if "version" in data and "entries" in data:
        entries = data["entries"]
        result = {}
        for p, ent in entries.items():
            if isinstance(ent, dict):
                result[p] = {
                    "sha1": ent.get("sha1", ""),
                    "mode": ent.get("mode", MODE_FILE),
                    "size": int(ent.get("size", 0)),
                    "mtime_ns": int(ent.get("mtime_ns", 0)),
                    "ctime_ns": int(ent.get("ctime_ns", 0)),
                }
            else:
                result[p] = {"sha1": str(ent), "mode": MODE_FILE, "size": 0, "mtime_ns": 0, "ctime_ns": 0}
        return result
    result = {}
    for p, val in data.items():
        result[p] = {"sha1": str(val), "mode": MODE_FILE, "size": 0, "mtime_ns": 0, "ctime_ns": 0}
    return result


def load_index(repo_git: Path) -> Dict[str, Dict[str, Any]]:
    """Load index. Binary DIRC -> read binary. JSON -> parse and migrate to binary (with optional backup)."""
    path = _index_path(repo_git)
    if not path.exists():
        return {}
    raw_bytes = path.read_bytes()
    if len(raw_bytes) >= 4 and raw_bytes[:4] == DIRC_SIGNATURE:
        return _read_dirc(repo_git)
    raw = raw_bytes.decode("utf-8", errors="replace")
    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        return {}
    if isinstance(data, list):
        return {}
    entries = _parse_json_entries(data)
    # Migrate: write binary index and optionally backup JSON
    backup = repo_git / "index.json.bak"
    try:
        if path.exists():
            write_bytes(backup, raw_bytes)
    except OSError:
        pass
    _write_dirc(repo_git, entries)
    return entries


def save_index(repo_git: Path, entries: Dict[str, Dict[str, Any]]) -> None:
    """Save index as binary DIRC v2 (atomic)."""
    _write_dirc(repo_git, entries)


def index_entry_for_file(file_path: Path, blob_sha: str) -> Dict[str, Any]:
    """Build index entry dict for a file (mode from +x, size, mtime_ns)."""
    try:
        st = file_path.stat()
        mode = MODE_FILE_EXECUTABLE if is_executable(file_path) else MODE_FILE
        mtime_ns = getattr(st, "st_mtime_ns", int(st.st_mtime * 1_000_000_000))
        ctime_ns = getattr(st, "st_ctime_ns", int(st.st_ctime * 1_000_000_000))
        return {
            "sha1": blob_sha,
            "mode": mode,
            "size": st.st_size,
            "mtime_ns": mtime_ns,
            "ctime_ns": ctime_ns,
        }
    except OSError:
        return {
            "sha1": blob_sha,
            "mode": MODE_FILE,
            "size": 0,
            "mtime_ns": 0,
            "ctime_ns": 0,
        }


def index_entries_unchanged(
    repo_root: Path,
    path: str,
    entry: Dict[str, Any],
) -> bool:
    """Return True if file on disk matches index (size and mtime_ns). If PYGIT_PARANOID=1, always return False."""
    if os.environ.get("PYGIT_PARANOID") == "1":
        return False
    full = repo_root / path
    if not full.is_file():
        return False
    try:
        st = full.stat()
        mtime_ns = getattr(st, "st_mtime_ns", int(st.st_mtime * 1_000_000_000))
        return st.st_size == entry.get("size", 0) and mtime_ns == entry.get("mtime_ns", 0)
    except OSError:
        return False
