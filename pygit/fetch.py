"""Fetch logic: discover refs, transfer objects, update remote-tracking refs (Phase 4)."""

from __future__ import annotations

import zlib
from pathlib import Path
from typing import List, Optional, Set, Tuple

from .constants import OBJ_BLOB, OBJ_COMMIT, OBJ_TAG, OBJ_TREE
from .errors import PygitError
from .objects import Commit, GitObject, Tag, Tree
from .remote import get_remote_fetch_refspecs, get_remote_url, parse_refspec, refspec_expand_src_list
from .refs import update_ref
from .repo import Repository
from .http_dumb import HttpDumbTransport
from .transport import LocalTransport, is_local_path


def _reachable_from_tips(transport: LocalTransport | HttpDumbTransport, tips: List[str]) -> Set[str]:
    """Return set of object SHAs reachable from tip commits (using transport.get_object)."""
    result: Set[str] = set()
    stack = list(tips)
    while stack:
        sha = stack.pop()
        if sha in result:
            continue
        result.add(sha)
        try:
            raw = transport.get_object(sha)
        except Exception:
            continue
        null = raw.find(b"\0")
        if null == -1:
            continue
        header = raw[:null].decode()
        content = raw[null + 1 :]
        parts = header.split(" ", 1)
        if len(parts) != 2:
            continue
        obj_type = parts[0]
        if obj_type == OBJ_COMMIT:
            commit = Commit.from_content(content)
            if commit.tree_hash:
                stack.append(commit.tree_hash)
            for p in commit.parent_hashes:
                if p:
                    stack.append(p)
        elif obj_type == OBJ_TREE:
            tree = Tree.from_content(content)
            for _mode, _name, eh in tree.entries:
                if eh:
                    stack.append(eh)
        elif obj_type == OBJ_TAG:
            tag = Tag.from_content(content)
            if tag.object_hash:
                stack.append(tag.object_hash)
    return result


def fetch(
    repo: Repository,
    remote_name: str,
    refspecs: Optional[List[str]] = None,
) -> None:
    """Fetch from remote: discover refs, copy missing objects, update remote-tracking refs.
    Uses local transport only (path or file:// URL).
    """
    repo.require_repo()
    url = get_remote_url(repo, remote_name)
    if not url:
        raise PygitError(f"remote {remote_name!r} not found")
    url = url.strip()
    if is_local_path(url):
        path = Path(url[7:].lstrip("/")) if url.startswith("file://") else Path(url)
        if not path.is_dir():
            raise PygitError(f"remote path is not a directory: {path}")
        transport: LocalTransport | HttpDumbTransport = LocalTransport(path)
    elif url.startswith("http://") or url.startswith("https://"):
        transport = HttpDumbTransport(url)
    else:
        raise PygitError("unsupported URL scheme for fetch; use local path, file://, http://, or https://")
    remote_refs = transport.list_refs()
    refspec_strs = refspecs or get_remote_fetch_refspecs(repo, remote_name)
    if not refspec_strs:
        return

    # Map remote refs -> local refs (dst) via refspecs
    dst_sha_list: List[Tuple[str, str]] = []
    for refspec_str in refspec_strs:
        refspec = parse_refspec(refspec_str)
        src_refs = [r[0] for r in remote_refs]
        for src, dst in refspec_expand_src_list(refspec, src_refs):
            sha = next((s for r, s in remote_refs if r == src), None)
            if sha:
                dst_sha_list.append((dst, sha))

    if not dst_sha_list:
        return

    tips = [sha for _dst, sha in dst_sha_list]
    need_shas = _reachable_from_tips(transport, tips)

    for sha in need_shas:
        if repo.odb.exists(sha):
            continue
        try:
            raw = transport.get_object(sha)
        except Exception:
            continue
        obj = GitObject.deserialize(zlib.compress(raw))
        repo.odb.store(obj)

    for dst, sha in dst_sha_list:
        update_ref(repo.git_dir, dst, sha)
