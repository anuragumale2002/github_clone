"""Remote config, refspec parsing, and remote-tracking refs (Phase 3)."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, List, Optional, Tuple

if TYPE_CHECKING:
    from .repo import Repository

from .config import read_config, write_config
from .constants import REF_HEADS_PREFIX, REF_REMOTES_PREFIX
from .errors import InvalidRefError, PygitError

REMOTE_SECTION_PREFIX = 'remote "'


def _remote_section(name: str) -> str:
    """Config section for remote: [remote "name"]"""
    return f'remote "{name}"'


def _validate_remote_name(name: str) -> None:
    """Raise InvalidRefError if remote name is invalid."""
    if not name or name.startswith("/") or " " in name or ".." in name:
        raise InvalidRefError(f"invalid remote name: {name!r}")


def remote_add(repo: "Repository", name: str, url: str, fetch_refspec: Optional[str] = None) -> None:
    """Add remote <name> with <url>. Default fetch refspec: +refs/heads/*:refs/remotes/<name>/*"""
    repo.require_repo()
    _validate_remote_name(name)
    cfg = read_config(repo)
    section = _remote_section(name)
    if cfg.has_section(section):
        raise PygitError(f"remote {name!r} already exists")
    cfg.add_section(section)
    cfg.set(section, "url", url.strip())
    if fetch_refspec is None:
        fetch_refspec = f"+{REF_HEADS_PREFIX}*:{REF_REMOTES_PREFIX}{name}/*"
    cfg.set(section, "fetch", fetch_refspec)
    write_config(repo, cfg)
    # Ensure refs/remotes/<name>/ exists (empty dir for later fetch)
    (repo.git_dir / REF_REMOTES_PREFIX.rstrip("/") / name).mkdir(parents=True, exist_ok=True)


def remote_remove(repo: "Repository", name: str) -> None:
    """Remove remote <name> from config. Does not delete remote-tracking refs."""
    repo.require_repo()
    _validate_remote_name(name)
    cfg = read_config(repo)
    section = _remote_section(name)
    if not cfg.has_section(section):
        raise PygitError(f"remote {name!r} does not exist")
    cfg.remove_section(section)
    write_config(repo, cfg)


def remote_list(repo: "Repository") -> List[Tuple[str, str, str]]:
    """List remotes. Returns [(name, fetch_url, push_url), ...]. push_url defaults to fetch url."""
    repo.require_repo()
    cfg = read_config(repo)
    result: List[Tuple[str, str, str]] = []
    for section in cfg.sections():
        if not section.startswith(REMOTE_SECTION_PREFIX) or not section.endswith('"'):
            continue
        name = section[len(REMOTE_SECTION_PREFIX) : -1]
        url = cfg.get(section, "url") if cfg.has_option(section, "url") else ""
        pushurl = cfg.get(section, "pushurl") if cfg.has_option(section, "pushurl") else url
        result.append((name, url, pushurl))
    return sorted(result, key=lambda t: t[0])


def get_remote_url(repo: "Repository", name: str) -> Optional[str]:
    """Return fetch URL for remote, or None if not configured."""
    repo.require_repo()
    cfg = read_config(repo)
    section = _remote_section(name)
    if not cfg.has_section(section) or not cfg.has_option(section, "url"):
        return None
    return cfg.get(section, "url")


def get_remote_fetch_refspecs(repo: "Repository", name: str) -> List[str]:
    """Return list of fetch refspecs for remote (e.g. +refs/heads/*:refs/remotes/origin/*)."""
    repo.require_repo()
    cfg = read_config(repo)
    section = _remote_section(name)
    if not cfg.has_section(section):
        return []
    refspecs: List[str] = []
    if cfg.has_option(section, "fetch"):
        # Git allows multiple fetch = lines; we store one, optionally multiple via get with raw
        val = cfg.get(section, "fetch")
        if val:
            refspecs.append(val)
    return refspecs


# --- Refspec parsing ---


@dataclass
class Refspec:
    """Parsed refspec: optional force (+), src pattern, dst pattern, optional wildcard."""

    force: bool
    src: str
    dst: str
    wildcard: bool  # True if src/dst contain *


def parse_refspec(refspec_str: str) -> "Refspec":
    """Parse a refspec string: [+][src]:[dst]. * in src/dst means wildcard.
    Raises InvalidRefError if invalid.
    """
    refspec_str = refspec_str.strip()
    if not refspec_str:
        raise InvalidRefError("empty refspec")
    force = refspec_str.startswith("+")
    if force:
        refspec_str = refspec_str[1:].strip()
    if ":" not in refspec_str:
        raise InvalidRefError(f"refspec must have src:dst: {refspec_str!r}")
    src, _, dst = refspec_str.partition(":")
    src, dst = src.strip(), dst.strip()
    if not src or not dst:
        raise InvalidRefError(f"refspec src and dst must be non-empty: {refspec_str!r}")
    wildcard = "*" in src or "*" in dst
    if wildcard and (src.count("*") != 1 or dst.count("*") != 1):
        raise InvalidRefError(f"refspec wildcard must appear once in src and dst: {refspec_str!r}")
    return Refspec(force=force, src=src, dst=dst, wildcard=wildcard)


def refspec_expand(refspec: "Refspec", src_ref: str) -> Optional[str]:
    """Map source ref to destination ref using refspec. Returns None if src doesn't match."""
    if refspec.wildcard:
        star = refspec.src.index("*")
        prefix, suffix = refspec.src[:star], refspec.src[star + 1 :]
        if not src_ref.startswith(prefix) or not src_ref.endswith(suffix):
            return None
        mid = src_ref[len(prefix) : -len(suffix)] if suffix else src_ref[len(prefix) :]
        star_d = refspec.dst.index("*")
        return refspec.dst[: star_d] + mid + refspec.dst[star_d + 1 :]
    if refspec.src == src_ref:
        return refspec.dst
    return None


def refspec_expand_src_list(refspec: "Refspec", src_refs: List[str]) -> List[Tuple[str, str]]:
    """For each src ref that matches refspec, return (src, dst)."""
    result: List[Tuple[str, str]] = []
    for src in src_refs:
        dst = refspec_expand(refspec, src)
        if dst is not None:
            result.append((src, dst))
    return result