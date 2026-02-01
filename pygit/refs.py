"""HEAD and refs management: symbolic refs and detached HEAD."""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path
from typing import Literal, Optional

from .constants import DEFAULT_BRANCH, HEAD_FILE, REF_HEADS_PREFIX, REF_TAGS_PREFIX, SHA1_HEX_LEN
from .errors import InvalidRefError
from .util import read_text_safe, write_text_atomic


@dataclass
class HeadState:
    """HEAD state: either symbolic ref or detached commit hash."""
    kind: Literal["ref", "detached"]
    value: str  # refs/heads/main or 40-char commit hash


def _head_file(repo_git: Path) -> Path:
    return repo_git / HEAD_FILE


def _ref_path(repo_git: Path, refname: str) -> Path:
    """Path to ref file for refs/heads/xyz or refs/tags/xyz."""
    return repo_git / refname


def _is_hex_sha(s: str) -> bool:
    return len(s) == SHA1_HEX_LEN and bool(re.fullmatch(r"[0-9a-fA-F]{40}", s))


def read_head(repo_git: Path) -> Optional[HeadState]:
    """Read HEAD; return HeadState or None if no HEAD file."""
    path = _head_file(repo_git)
    raw = read_text_safe(path)
    if raw is None:
        return None
    raw = raw.strip()
    if raw.startswith("ref: "):
        refname = raw[5:].strip()
        return HeadState("ref", refname)
    if _is_hex_sha(raw):
        return HeadState("detached", raw.lower())
    return None


def write_head_ref(repo_git: Path, refname: str) -> None:
    """Set HEAD to symbolic ref (e.g. refs/heads/main)."""
    if not refname.startswith(REF_HEADS_PREFIX):
        raise InvalidRefError(f"symbolic ref must be refs/heads/... (got {refname})")
    content = f"ref: {refname}\n"
    write_text_atomic(_head_file(repo_git), content)


def write_head_detached(repo_git: Path, commit_hash: str) -> None:
    """Set HEAD to detached commit hash (40 hex chars)."""
    if not _is_hex_sha(commit_hash):
        raise InvalidRefError(f"invalid commit hash: {commit_hash}")
    write_text_atomic(_head_file(repo_git), commit_hash.lower() + "\n")


def _read_packed_refs(repo_git: Path) -> dict[str, str]:
    """Read .git/packed-refs; return dict refname -> sha (loose refs override, so we only use when loose missing)."""
    packed = repo_git / "packed-refs"
    if not packed.is_file():
        return {}
    result: dict[str, str] = {}
    try:
        raw = packed.read_text()
    except OSError:
        return {}
    for line in raw.splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        if line.startswith("^"):
            continue  # peeled tag line; previous line was the ref
        parts = line.split(None, 1)
        if len(parts) < 2:
            continue
        sha, refname = parts[0], parts[1]
        if _is_hex_sha(sha):
            result[refname] = sha.lower()
    return result


def resolve_ref(repo_git: Path, refname: str, _packed: Optional[dict[str, str]] = None) -> Optional[str]:
    """Resolve ref to commit hash; return None if ref or target doesn't exist. Checks loose then packed-refs."""
    path = _ref_path(repo_git, refname)
    content = read_text_safe(path)
    if content is None:
        if _packed is None:
            _packed = _read_packed_refs(repo_git)
        content = _packed.get(refname)
        if content is None:
            return None
        # content is sha from packed-refs
        return content.lower() if _is_hex_sha(content) else None
    content = content.strip()
    if _is_hex_sha(content):
        return content.lower()
    # symbolic ref: resolve recursively (we don't store symbolic refs in refs/ normally, only HEAD)
    return resolve_ref(repo_git, content, _packed=_packed)


def update_ref(repo_git: Path, refname: str, new_hash: str) -> None:
    """Write ref to point to new_hash (40 hex)."""
    if not _is_hex_sha(new_hash):
        raise InvalidRefError(f"invalid hash: {new_hash}")
    path = _ref_path(repo_git, refname)
    path.parent.mkdir(parents=True, exist_ok=True)
    write_text_atomic(path, new_hash.lower() + "\n")


def update_ref_verify(
    repo_git: Path,
    refname: str,
    new_hash: str,
    old_hash: Optional[str] = None,
) -> None:
    """Update ref to new_hash; if old_hash given, update only if current value matches. Uses lock file."""
    if not _is_hex_sha(new_hash):
        raise InvalidRefError(f"invalid hash: {new_hash}")
    path = _ref_path(repo_git, refname)
    if old_hash is not None:
        current = resolve_ref(repo_git, refname)
        if current is None or current.lower() != old_hash.lower():
            raise InvalidRefError(f"ref {refname} is not at expected value (expected {old_hash})")
    path.parent.mkdir(parents=True, exist_ok=True)
    lock_path = path.parent / (path.name + ".lock")
    try:
        write_text_atomic(lock_path, new_hash.lower() + "\n")
        lock_path.replace(path)
    finally:
        if lock_path.exists():
            try:
                lock_path.unlink()
            except OSError:
                pass


def current_branch_name(repo_git: Path) -> Optional[str]:
    """Return current branch name (e.g. main) or None if detached."""
    state = read_head(repo_git)
    if state is None:
        return None
    if state.kind == "detached":
        return None
    if state.value.startswith(REF_HEADS_PREFIX):
        return state.value[len(REF_HEADS_PREFIX) :]
    return None


def head_commit(repo_git: Path) -> Optional[str]:
    """Resolve HEAD to commit hash; return None if no HEAD or ref doesn't resolve."""
    state = read_head(repo_git)
    if state is None:
        return None
    if state.kind == "detached":
        return state.value
    return resolve_ref(repo_git, state.value)


def list_branches(repo_git: Path) -> list[str]:
    """List branch names (refs/heads/*) from loose refs only."""
    heads_dir = repo_git / "refs" / "heads"
    if not heads_dir.is_dir():
        return []
    return sorted(
        p.name for p in heads_dir.iterdir() if p.is_file() and not p.name.startswith(".")
    )


def list_ref_names_with_prefix(repo_git: Path, prefix: str) -> list[str]:
    """List full ref names (e.g. refs/heads/main) with given prefix, from loose + packed-refs."""
    loose: list[str] = []
    refs_dir = repo_git / prefix.rstrip("/")
    if refs_dir.is_dir():
        for p in refs_dir.iterdir():
            if p.is_file() and not p.name.startswith("."):
                loose.append(prefix + p.name)
    packed = _read_packed_refs(repo_git)
    packed_refs = [r for r in packed if r.startswith(prefix)]
    return sorted(set(loose) | set(packed_refs))


# Characters disallowed in tag names (git refname rules)
_TAG_FORBIDDEN = set(" ~^:?*[]\\")

def validate_tag_name(name: str) -> None:
    """Raise InvalidRefError if tag name is invalid (spaces, .., leading /, ~^:?*[], etc.)."""
    if not name or name.startswith("/") or name.endswith("/"):
        raise InvalidRefError(f"invalid tag name: {name!r}")
    if ".." in name or "//" in name:
        raise InvalidRefError(f"invalid tag name: {name!r}")
    for c in name:
        if c in _TAG_FORBIDDEN:
            raise InvalidRefError(f"invalid tag name: {name!r}")
    if name.startswith("."):
        raise InvalidRefError(f"invalid tag name: {name!r}")


def list_tags(repo_git: Path) -> list[str]:
    """List tag names (refs/tags/*) from loose refs only."""
    tags_dir = repo_git / "refs" / "tags"
    if not tags_dir.is_dir():
        return []
    return sorted(
        p.name for p in tags_dir.iterdir() if p.is_file() and not p.name.startswith(".")
    )
