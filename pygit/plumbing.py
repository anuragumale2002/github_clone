"""Plumbing commands: hash-object, cat-file, ls-tree, write-tree, commit-tree, rev-parse, merge-base, rev-list."""

from __future__ import annotations

import sys
from collections import deque
from pathlib import Path
from typing import List, Optional

from .constants import OBJ_BLOB, OBJ_COMMIT, OBJ_TAG, OBJ_TREE, REF_HEADS_PREFIX, REF_TAGS_PREFIX
from .errors import AmbiguousRefError, InvalidRefError, ObjectNotFoundError
from .graph import get_commit_parents
from .objects import Blob, Commit, GitObject, Tag, Tree
from .refs import (
    head_commit,
    list_branches,
    list_tags,
    resolve_ref as refs_resolve,
    update_ref_verify,
    write_head_ref,
)
from .repo import Repository
from .reflog import ZEROS, append_reflog
from .util import read_bytes, timestamp_with_tz


def _peel_to_non_tag(repo: Repository, sha: str) -> str:
    """If sha is a tag object, peel to target; repeat until non-tag. Return final hash."""
    while True:
        obj = repo.load_object(sha)
        if obj.type != OBJ_TAG:
            return sha
        tag = Tag.from_content(obj.content)
        sha = tag.object_hash
    return sha


def rev_parse(repo: Repository, name: str, peel: bool = False) -> str:
    """Resolve name to 40-char hash. Supports HEAD~n (n-th first ancestor), rev^n (n-th parent).
    If peel=True or name ends with ^{}, peel tag objects to target."""
    repo.require_repo()
    name = name.strip()
    if name.endswith("^{}"):
        name = name[:-3].strip()
        peel = True

    # rev^n or rev^: n-th parent (1-based); applied right-to-left so HEAD~1^2 = (HEAD~1)^2
    if "^" in name:
        caret_idx = name.rfind("^")
        base = name[:caret_idx].strip()
        num_str = name[caret_idx + 1 :].strip()
        if not base:
            raise InvalidRefError(f"invalid ref or object: {name}")
        if not num_str or num_str.isdigit():
            parent_idx = int(num_str) if num_str.isdigit() else 1
            if parent_idx < 1:
                raise InvalidRefError(f"invalid ref or object: {name}")
            sha = rev_parse(repo, base, peel=True)
            parents = get_commit_parents(repo, sha)
            if parent_idx > len(parents):
                raise InvalidRefError(f"invalid ref or object: {name}")
            sha = parents[parent_idx - 1]
            return sha

    # rev~n or rev~: first parent n times (rev~1 = first parent, rev~2 = first parent of first parent)
    if "~" in name:
        tilde_idx = name.rfind("~")
        base = name[:tilde_idx].strip()
        n_str = name[tilde_idx + 1 :].strip()
        if not base:
            raise InvalidRefError(f"invalid ref or object: {name}")
        n = int(n_str) if n_str.isdigit() else 1
        if n < 0:
            raise InvalidRefError(f"invalid ref or object: {name}")
        sha = rev_parse(repo, base, peel=True)
        for _ in range(n):
            parents = get_commit_parents(repo, sha)
            if not parents:
                raise InvalidRefError(f"invalid ref or object: {name}")
            sha = parents[0]
        return sha

    sha: Optional[str] = None
    # HEAD
    if name == "HEAD":
        from .refs import head_commit
        h = head_commit(repo.git_dir)
        if h is None:
            raise InvalidRefError("HEAD does not resolve to a commit")
        sha = h
    elif not name.startswith("refs/"):
        branch_ref = REF_HEADS_PREFIX + name
        r = refs_resolve(repo.git_dir, branch_ref)
        if r is not None:
            sha = r
        else:
            tag_ref = REF_TAGS_PREFIX + name
            r = refs_resolve(repo.git_dir, tag_ref)
            if r is not None:
                sha = r
    else:
        r = refs_resolve(repo.git_dir, name)
        if r is not None:
            sha = r
    if sha is None:
        if len(name) == 40 and all(c in "0123456789abcdef" for c in name.lower()):
            if repo.odb.exists(name):
                sha = name.lower()
            else:
                raise ObjectNotFoundError(f"object {name} not found")
        else:
            try:
                sha = repo.odb.resolve_prefix(name)
            except AmbiguousRefError:
                raise
            except ObjectNotFoundError:
                raise InvalidRefError(f"invalid ref or object: {name}")
    if peel:
        sha = _peel_to_non_tag(repo, sha)
    return sha


def hash_object(repo: Repository, path: str, write: bool) -> str:
    """Compute blob hash of file; optionally write to ODB. Return hash."""
    repo.require_repo()
    p = repo.safe_path(path)
    if not p.is_file():
        raise FileNotFoundError(f"path {path} is not a file")
    content = read_bytes(p)
    blob = Blob(content)
    if write:
        return repo.store_object(blob)
    return blob.hash_id()


def cat_file_type(repo: Repository, obj_ref: str) -> str:
    """Print object type (blob, tree, commit)."""
    repo.require_repo()
    sha = rev_parse(repo, obj_ref)
    obj = repo.load_object(sha)
    return obj.type


def cat_file_pretty(repo: Repository, obj_ref: str) -> None:
    """Pretty-print object: commit (headers + message), tree (mode sha name), blob (raw)."""
    repo.require_repo()
    sha = rev_parse(repo, obj_ref)
    obj = repo.load_object(sha)
    if obj.type == OBJ_COMMIT:
        commit = Commit.from_content(obj.content)
        print(f"tree {commit.tree_hash}")
        for p in commit.parent_hashes:
            print(f"parent {p}")
        print(f"author {commit.author} {commit._timestamp} {commit._tz_offset}")
        print(f"committer {commit.committer} {commit._timestamp} {commit._tz_offset}")
        print()
        print(commit.message, end="" if commit.message.endswith("\n") else "\n")
    elif obj.type == OBJ_TREE:
        tree = Tree.from_content(obj.content)
        for mode, name, ent_sha in tree.entries:
            print(f"{mode} {ent_sha} {name}")
    elif obj.type == OBJ_TAG:
        tag = Tag.from_content(obj.content)
        print(f"object {tag.object_hash}")
        print(f"type {tag.object_type}")
        print(f"tag {tag.tag_name}")
        print(f"tagger {tag.tagger} {tag._timestamp} {tag._tz_offset}")
        print()
        print(tag.message, end="" if tag.message.endswith("\n") else "\n")
    else:
        sys.stdout.buffer.write(obj.content)


def _ls_tree_rec(
    repo: Repository,
    tree: Tree,
    prefix: str,
    name_only: bool,
    recursive: bool,
) -> None:
    for mode, name, ent_sha in sorted(tree.entries, key=lambda e: (not e[0].startswith("04"), e[1])):
        if name_only:
            print(prefix + name)
        else:
            kind = "tree" if mode.startswith("04") else "blob"
            print(f"{mode} {kind}\t{ent_sha}\t{prefix}{name}")
        if recursive and mode.startswith("04"):
            child = repo.load_object(ent_sha)
            sub = Tree.from_content(child.content)
            _ls_tree_rec(repo, sub, prefix + name + "/", name_only, recursive)


def ls_tree(
    repo: Repository,
    tree_ish: str,
    recursive: bool = False,
    name_only: bool = False,
) -> None:
    """List tree; tree_ish can be commit hash, tree hash, branch, HEAD."""
    repo.require_repo()
    sha = rev_parse(repo, tree_ish)
    obj = repo.load_object(sha)
    if obj.type == OBJ_COMMIT:
        commit = Commit.from_content(obj.content)
        tree_sha = commit.tree_hash
    else:
        tree_sha = sha
    tree_obj = repo.load_object(tree_sha)
    tree = Tree.from_content(tree_obj.content)
    _ls_tree_rec(repo, tree, "", name_only, recursive)


def write_tree(repo: Repository) -> str:
    """Build tree from current index; print tree hash. Does not create a commit."""
    repo.require_repo()
    tree_hash = repo.create_tree_from_index()
    return tree_hash


def commit_tree(
    repo: Repository,
    tree_hash: str,
    parent_hashes: List[str],
    message: str,
    author: Optional[str] = None,
    committer: Optional[str] = None,
) -> str:
    """Create commit object; print commit hash. Does not update refs."""
    repo.require_repo()
    if not repo.odb.exists(tree_hash):
        raise ObjectNotFoundError(f"tree {tree_hash} not found")
    author = author or "PyGit User <user@pygit.com>"
    committer = committer or author
    ts, tz = timestamp_with_tz(None)
    commit = Commit(
        tree_hash=tree_hash,
        parent_hashes=parent_hashes,
        author=author,
        committer=committer,
        message=message,
        timestamp=ts,
        tz_offset=tz,
    )
    sha = repo.store_object(commit)
    return sha


def show_ref(
    repo: Repository,
    heads_only: bool = False,
    tags_only: bool = False,
) -> None:
    """Print <hash> <refname> per line. Default: heads and tags; --heads / --tags filter."""
    repo.require_repo()
    if not tags_only:
        for name in sorted(list_branches(repo.git_dir)):
            refname = REF_HEADS_PREFIX + name
            h = refs_resolve(repo.git_dir, refname)
            if h:
                print(f"{h} {refname}")
    if not heads_only:
        for name in sorted(list_tags(repo.git_dir)):
            refname = REF_TAGS_PREFIX + name
            h = refs_resolve(repo.git_dir, refname)
            if h:
                print(f"{h} {refname}")


def symbolic_ref(repo: Repository, name: str, refname: str) -> None:
    """Set symbolic ref (only HEAD supported). Writes ref: refname."""
    repo.require_repo()
    if name != "HEAD":
        raise InvalidRefError("symbolic-ref only supports HEAD")
    if not refname.startswith(REF_HEADS_PREFIX):
        raise InvalidRefError(f"refname must be refs/heads/... (got {refname})")
    old_commit = head_commit(repo.git_dir)
    write_head_ref(repo.git_dir, refname)
    new_commit = refs_resolve(repo.git_dir, refname) or ZEROS
    append_reflog(repo, "HEAD", old_commit or ZEROS, new_commit, f"symbolic-ref: {refname}")


def update_ref_cmd(
    repo: Repository,
    refname: str,
    new_hash: str,
    old_hash: Optional[str] = None,
) -> None:
    """Update ref to new_hash; if old_hash given, update only if current matches."""
    repo.require_repo()
    current = refs_resolve(repo.git_dir, refname)
    update_ref_verify(repo.git_dir, refname, new_hash, old_hash)
    if refname.startswith(REF_HEADS_PREFIX):
        append_reflog(repo, refname, current or ZEROS, new_hash, f"update-ref: {refname}")


def _ancestors_bfs(repo: Repository, start: str) -> set[str]:
    """Collect all ancestors of start (BFS, parent order from commit object)."""
    result: set[str] = set()
    queue: deque[str] = deque([start])
    while queue:
        h = queue.popleft()
        if h in result:
            continue
        result.add(h)
        try:
            for p in get_commit_parents(repo, h):
                if p and p not in result:
                    queue.append(p)
        except ObjectNotFoundError:
            pass
    return result


def merge_base(repo: Repository, a: str, b: str) -> Optional[str]:
    """Find a best common ancestor of a and b (first found LCA in BFS order from b).
    Resolve a and b with rev_parse (peel to commit). Returns None if no common ancestor.
    """
    repo.require_repo()
    sha_a = rev_parse(repo, a, peel=True)
    sha_b = rev_parse(repo, b, peel=True)
    ancestors_a = _ancestors_bfs(repo, sha_a)
    queue: deque[str] = deque([sha_b])
    seen: set[str] = set()
    while queue:
        h = queue.popleft()
        if h in seen:
            continue
        seen.add(h)
        if h in ancestors_a:
            return h
        try:
            parents = get_commit_parents(repo, h)
            for p in parents:
                if p and p not in seen:
                    queue.append(p)
        except ObjectNotFoundError:
            pass
    return None


def rev_list(
    repo: Repository,
    rev: Optional[str] = None,
    max_count: Optional[int] = None,
    parents: bool = False,
    all_refs: bool = False,
) -> None:
    """List commit hashes reachable from rev (or from all refs/heads when --all).
    Traversal: all parents (not first-parent only), DFS with parents in reverse order for determinism.
    Output: one hash per line; with --parents: 'hash parent1 parent2 ...' per line.
    """
    repo.require_repo()
    tips: List[str] = []
    if all_refs:
        for name in sorted(list_branches(repo.git_dir)):
            refname = REF_HEADS_PREFIX + name
            h = refs_resolve(repo.git_dir, refname)
            if h:
                try:
                    peeled = _peel_to_non_tag(repo, h)
                    obj = repo.load_object(peeled)
                    if obj.type == OBJ_COMMIT:
                        tips.append(peeled)
                except ObjectNotFoundError:
                    pass
        if not tips:
            return
    else:
        if not rev:
            raise InvalidRefError("rev-list requires <rev> or --all")
        tips = [rev_parse(repo, rev, peel=True)]
    seen: set[str] = set()
    stack: List[str] = list(tips)
    count = 0
    while stack:
        h = stack.pop()
        if h in seen:
            continue
        seen.add(h)
        try:
            obj = repo.load_object(h)
            if obj.type != OBJ_COMMIT:
                continue
            commit = Commit.from_content(obj.content)
            par = list(commit.parent_hashes)
            for p in reversed(par):
                if p and p not in seen:
                    stack.append(p)
            if parents:
                line = f"{h} " + " ".join(par) if par else h
                print(line)
            else:
                print(h)
            count += 1
            if max_count is not None and count >= max_count:
                return
        except ObjectNotFoundError:
            pass
