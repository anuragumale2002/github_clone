"""Commit graph helpers: iteration, parents, ancestry."""

from __future__ import annotations

from collections import deque
from typing import Generator

from .constants import OBJ_COMMIT
from .errors import ObjectNotFoundError
from .objects import Commit
from .repo import Repository


def get_commit_parents(repo: Repository, commit_hash: str) -> list[str]:
    """Load commit and return its parent hashes (order as in commit object)."""
    obj = repo.load_object(commit_hash)
    if obj.type != OBJ_COMMIT:
        raise ObjectNotFoundError(f"object {commit_hash} is not a commit")
    commit = Commit.from_content(obj.content)
    return list(commit.parent_hashes)


def iter_commits(
    repo: Repository,
    start_hash: str,
    first_parent_only: bool = True,
) -> Generator[str, None, None]:
    """Walk commits from start_hash following parents. Yields commit hashes in visit order.
    first_parent_only: if True, follow only the first parent; else all parents (for rev-list style).
    Stops at None/missing. Raises ObjectNotFoundError if start_hash is missing or not a commit.
    """
    obj = repo.load_object(start_hash)
    if obj.type != OBJ_COMMIT:
        raise ObjectNotFoundError(f"object {start_hash} is not a commit")
    yield start_hash
    stack: list[str] = list(get_commit_parents(repo, start_hash))
    if first_parent_only and stack:
        stack = stack[:1]
    seen: set[str] = {start_hash}
    while stack:
        h = stack.pop()
        if h in seen or not h:
            continue
        seen.add(h)
        try:
            obj = repo.load_object(h)
        except ObjectNotFoundError:
            continue
        if obj.type != OBJ_COMMIT:
            continue
        yield h
        parents = get_commit_parents(repo, h)
        if first_parent_only and parents:
            parents = parents[:1]
        for p in reversed(parents):
            if p and p not in seen:
                stack.append(p)


def is_ancestor(repo: Repository, anc: str, desc: str) -> bool:
    """Return True if anc is reachable from desc via parent links (anc is ancestor of desc)."""
    visited: set[str] = set()
    queue: deque[str] = deque([desc])
    while queue:
        h = queue.popleft()
        if h in visited:
            continue
        visited.add(h)
        if h == anc:
            return True
        try:
            parents = get_commit_parents(repo, h)
        except ObjectNotFoundError:
            continue
        for p in parents:
            if p and p not in visited:
                queue.append(p)
    return False
