"""Garbage collection: reachability, repack, gc, prune (Phase 2)."""

from __future__ import annotations

from pathlib import Path
from typing import Set

from .constants import OBJ_BLOB, OBJ_COMMIT, OBJ_TAG, OBJ_TREE, REF_HEADS_PREFIX, REF_TAGS_PREFIX
from .errors import ObjectNotFoundError
from .idx import write_idx
from .objects import Commit, Tag, Tree
from .pack import write_pack
from .refs import list_ref_names_with_prefix, resolve_ref
from .repo import Repository
from .util import write_bytes_atomic


def _peel_to_commit(repo: Repository, sha: str) -> str | None:
    """If sha is a tag object, peel to target until commit; return commit sha or None."""
    try:
        obj = repo.load_object(sha)
        while obj.type == OBJ_TAG:
            tag = Tag.from_content(obj.content)
            sha = tag.object_hash
            obj = repo.load_object(sha)
        if obj.type == OBJ_COMMIT:
            return sha
    except ObjectNotFoundError:
        pass
    return None


def reachable_objects(repo: Repository) -> Set[str]:
    """Return set of object SHAs reachable from refs/heads/* and refs/tags/* (loose + packed)."""
    repo.require_repo()
    refnames = list_ref_names_with_prefix(repo.git_dir, REF_HEADS_PREFIX) + list_ref_names_with_prefix(
        repo.git_dir, REF_TAGS_PREFIX
    )
    commit_tips: list[str] = []
    tag_object_shas: set[str] = set()

    for refname in refnames:
        sha = resolve_ref(repo.git_dir, refname)
        if not sha:
            continue
        try:
            obj = repo.load_object(sha)
            if obj.type == OBJ_COMMIT:
                commit_tips.append(sha)
            elif obj.type == OBJ_TAG:
                tag_object_shas.add(sha)
                commit_sha = _peel_to_commit(repo, sha)
                if commit_sha:
                    commit_tips.append(commit_sha)
        except ObjectNotFoundError:
            pass

    # Rev-list style: all commits reachable from tips
    commit_hashes: set[str] = set()
    stack = list(commit_tips)
    seen: set[str] = set()
    while stack:
        h = stack.pop()
        if h in seen:
            continue
        seen.add(h)
        try:
            obj = repo.load_object(h)
            if obj.type != OBJ_COMMIT:
                continue
            commit_hashes.add(h)
            commit = Commit.from_content(obj.content)
            for p in commit.parent_hashes:
                if p and p not in seen:
                    stack.append(p)
        except ObjectNotFoundError:
            pass

    # All trees and blobs from those commits
    tree_blob_hashes: set[str] = set()
    for c in commit_hashes:
        try:
            obj = repo.load_object(c)
            commit = Commit.from_content(obj.content)
            tree_sha = commit.tree_hash
            if tree_sha:
                stack = [tree_sha]
                while stack:
                    th = stack.pop()
                    if th in tree_blob_hashes:
                        continue
                    tree_blob_hashes.add(th)
                    obj = repo.load_object(th)
                    if obj.type == OBJ_TREE:
                        tree = Tree.from_content(obj.content)
                        for _mode, _name, eh in tree.entries:
                            if eh and eh not in tree_blob_hashes:
                                stack.append(eh)
                    elif obj.type == OBJ_BLOB:
                        pass
        except ObjectNotFoundError:
            pass

    return commit_hashes | tree_blob_hashes | tag_object_shas


def repack(
    repo: Repository,
    object_ids: list[str],
    prune_loose: bool = False,
) -> str:
    """Pack given object IDs into .git/objects/pack/pack-<sha>.pack + .idx. Returns pack SHA (hex).
    object_ids must be reachable; deterministic order (sorted). If prune_loose, remove loose copies.
    """
    repo.require_repo()
    if not object_ids:
        raise ValueError("repack requires at least one object")
    objects_dir = repo.objects_dir
    pack_dir = objects_dir / "pack"
    pack_dir.mkdir(parents=True, exist_ok=True)

    def get_raw(sha: str) -> bytes:
        return repo.odb.get_raw(sha)

    pack_bytes, entries = write_pack(Path("."), object_ids, get_raw)
    pack_sha_hex = pack_bytes[-20:].hex()

    pack_path = pack_dir / f"pack-{pack_sha_hex}.pack"
    idx_path = pack_dir / f"pack-{pack_sha_hex}.idx"
    write_bytes_atomic(pack_path, pack_bytes)
    write_idx(idx_path, pack_sha_hex, entries)
    repo.odb.rescan_packs()

    if prune_loose:
        for sha in object_ids:
            loose_path = objects_dir / sha[:2] / sha[2:]
            if loose_path.exists():
                try:
                    loose_path.unlink()
                except OSError:
                    pass

    return pack_sha_hex


def gc(repo: Repository, prune_loose: bool = False) -> str | None:
    """Compute reachable objects, pack them into one pack. Keep loose by default.
    Returns pack SHA (hex) or None if nothing to pack.
    """
    repo.require_repo()
    reachable = reachable_objects(repo)
    if not reachable:
        return None
    object_ids = sorted(reachable)
    return repack(repo, object_ids, prune_loose=prune_loose)


def prune(repo: Repository) -> None:
    """Remove loose objects that exist in any pack (redundant copies). Safe: only deletes loose
    objects that are present in a pack file.
    """
    repo.require_repo()
    objects_dir = repo.objects_dir
    for two in range(256):
        sub = objects_dir / f"{two:02x}"
        if not sub.is_dir():
            continue
        for f in sub.iterdir():
            if not f.is_file() or len(f.name) != 38:
                continue
            sha = f"{two:02x}{f.name}"
            if repo.odb.is_in_any_pack(sha):
                try:
                    f.unlink()
                except OSError:
                    pass
