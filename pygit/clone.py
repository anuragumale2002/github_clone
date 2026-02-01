"""Clone logic: init dest repo, add remote, fetch, checkout default branch (Phase 6)."""

from __future__ import annotations

from pathlib import Path
from typing import Optional

from .constants import DEFAULT_BRANCH, REF_HEADS_PREFIX
from .errors import PygitError
from .fetch import fetch
from .refs import resolve_ref, update_ref, write_head_ref
from .repo import Repository
from .transport import is_local_path


def _is_http_url(s: str) -> bool:
    """Return True if s looks like an http(s) URL."""
    t = s.strip()
    return t.startswith("http://") or t.startswith("https://")


def clone(
    src_path: str | Path,
    dest_path: str | Path,
    remote_name: str = "origin",
) -> Repository:
    """Clone src repo into dest_path: init dest, add remote, fetch, checkout default branch.
    Supports local path, file:// URL, or http(s) URL (dumb HTTP).
    """
    dest = Path(dest_path).resolve()
    if dest.exists() and any(dest.iterdir()):
        raise PygitError(f"destination path {dest} already exists and is not an empty directory")

    dest.mkdir(parents=True, exist_ok=True)
    repo = Repository(str(dest))
    repo.init()

    src_str = str(src_path).strip()
    if _is_http_url(src_str):
        url = src_str
    else:
        src = Path(src_path).resolve()
        if not src.is_dir():
            raise PygitError(f"source is not a directory: {src}")
        url = str(src)

    from .remote import remote_add

    remote_add(repo, remote_name, url)
    fetch(repo, remote_name)

    # Point refs/heads/<default> at remote's default branch and checkout
    remote_main_ref = f"refs/remotes/{remote_name}/{DEFAULT_BRANCH}"
    head_sha = resolve_ref(repo.git_dir, remote_main_ref)
    if not head_sha:
        return repo
    update_ref(repo.git_dir, REF_HEADS_PREFIX + DEFAULT_BRANCH, head_sha)
    write_head_ref(repo.git_dir, REF_HEADS_PREFIX + DEFAULT_BRANCH)

    from .porcelain import checkout_branch

    checkout_branch(repo, DEFAULT_BRANCH, create=False)
    return repo
