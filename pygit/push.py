"""Push logic: send objects to remote, update remote refs (Phase 5)."""

from __future__ import annotations

import zlib
from pathlib import Path
from typing import List, Optional, Set, Tuple

from .constants import OBJ_BLOB, OBJ_COMMIT, OBJ_TAG, OBJ_TREE
from .errors import PygitError
from .objects import Commit, GitObject, Tag, Tree
from .refs import resolve_ref, update_ref_verify
from .repo import Repository
from .transport import LocalTransport, is_local_path


def _reachable_from_tips_local(repo: Repository, tips: List[str]) -> Set[str]:
    """Return set of object SHAs reachable from tip commits (local repo)."""
    result: Set[str] = set()
    stack = list(tips)
    while stack:
        sha = stack.pop()
        if sha in result:
            continue
        result.add(sha)
        try:
            obj = repo.load_object(sha)
        except Exception:
            continue
        if obj.type == OBJ_COMMIT:
            commit = Commit.from_content(obj.content)
            if commit.tree_hash:
                stack.append(commit.tree_hash)
            for p in commit.parent_hashes:
                if p:
                    stack.append(p)
        elif obj.type == OBJ_TREE:
            tree = Tree.from_content(obj.content)
            for _mode, _name, eh in tree.entries:
                if eh:
                    stack.append(eh)
        elif obj.type == OBJ_TAG:
            tag = Tag.from_content(obj.content)
            if tag.object_hash:
                stack.append(tag.object_hash)
    return result


def push(
    repo: Repository,
    remote_name: str,
    src_ref: str,
    dst_ref: str,
    force: bool = False,
) -> None:
    """Push src_ref to remote dst_ref. Refuse non-FF unless force.
    Only local path or file:// URL supported.
    """
    repo.require_repo()
    from .remote import get_remote_url

    url = get_remote_url(repo, remote_name)
    if not url:
        raise PygitError(f"remote {remote_name!r} not found")
    if not is_local_path(url):
        raise PygitError("only local path or file:// URL supported for push")

    from .plumbing import rev_parse

    src_sha = rev_parse(repo, src_ref, peel=True)
    path = Path(url[7:].lstrip("/")) if url.strip().startswith("file://") else Path(url.strip())
    if not path.is_dir():
        raise PygitError(f"remote path is not a directory: {path}")

    remote_repo = Repository(str(path))
    remote_repo.require_repo()
    current_remote = resolve_ref(remote_repo.git_dir, dst_ref)
    if current_remote is not None and not force:
        from .graph import is_ancestor

        if not is_ancestor(remote_repo, current_remote, src_sha):
            raise PygitError(
                f"non-fast-forward: ref {dst_ref} would be updated from {current_remote} to {src_sha}; use --force"
            )

    need_shas = _reachable_from_tips_local(repo, [src_sha])
    transport = LocalTransport(path)
    for sha in need_shas:
        if transport.has_object(sha):
            continue
        raw = repo.odb.get_raw(sha)
        obj = GitObject.deserialize(zlib.compress(raw))
        remote_repo.odb.store(obj)

    old = None if (force or current_remote is None) else current_remote
    update_ref_verify(remote_repo.git_dir, dst_ref, src_sha, old_hash=old)
