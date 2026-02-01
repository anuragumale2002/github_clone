"""Stash: save/list/apply/pop working tree and index (Phase C)."""

from __future__ import annotations

from pathlib import Path
from typing import Optional

from .errors import PygitError
from .plumbing import commit_tree
from .porcelain import reset_hard
from .refs import head_commit, resolve_ref, update_ref
from .reflog import ZEROS, append_reflog, read_reflog
from .repo import Repository


STASH_REF = "refs/stash"


def stash_save(repo: Repository, message: Optional[str] = None) -> None:
    """Save current index and working tree to stash; reset to HEAD."""
    repo.require_repo()
    head = head_commit(repo.git_dir)
    if not head:
        raise PygitError("nothing to stash (no HEAD commit)")
    index_tree = repo.create_tree_from_index()
    worktree_tree = repo.create_tree_from_workdir()
    branch = _current_branch_for_message(repo)
    index_msg = "index on " + (branch or "detached HEAD") + ": ..."
    index_commit = commit_tree(
        repo,
        index_tree,
        [head],
        index_msg,
    )
    stash_msg = message or ("WIP on " + (branch or "detached HEAD") + ": ...")
    stash_commit = commit_tree(
        repo,
        worktree_tree,
        [head, index_commit],
        stash_msg,
    )
    old_stash = resolve_ref(repo.git_dir, STASH_REF)
    update_ref(repo.git_dir, STASH_REF, stash_commit)
    append_reflog(repo, STASH_REF, old_stash or ZEROS, stash_commit, stash_msg)
    reset_hard(repo, head)


def stash_list(repo: Repository) -> list[tuple[str, str]]:
    """Return [(stash_ref, message), ...] for stash@{0}, stash@{1}, ... (newest first)."""
    repo.require_repo()
    entries = read_reflog(repo, STASH_REF)
    result: list[tuple[str, str]] = []
    for i, (old_h, new_h, _who, _ts, _tz, msg) in enumerate(reversed(entries)):
        result.append((f"stash@{{{i}}}", msg.strip()))
    return result


def _stash_commit_for_ref(repo: Repository, ref: str) -> Optional[str]:
    """Resolve stash@{n} or stash to commit hash."""
    if ref == "stash" or ref == "stash@{}":
        return resolve_ref(repo.git_dir, STASH_REF)
    if ref.startswith("stash@{") and ref.endswith("}"):
        try:
            n = int(ref[7:-1])
        except ValueError:
            return None
        entries = read_reflog(repo, STASH_REF)
        if n < 0 or n >= len(entries):
            return None
        # entries oldest first; stash@{0} = newest = last entry
        _, new_h, _, _, _, _ = entries[-(1 + n)]
        return new_h
    return None


def stash_apply(repo: Repository, ref: Optional[str] = None) -> None:
    """Restore index and working tree from stash (default stash@{0}); keep stash entry."""
    repo.require_repo()
    stash_sha = _stash_commit_for_ref(repo, ref or "stash@{0}") if (ref or "stash@{0}") else resolve_ref(repo.git_dir, STASH_REF)
    if not stash_sha:
        raise PygitError("stash not found" + (f": {ref}" if ref else ""))
    _restore_stash(repo, stash_sha)


def stash_pop(repo: Repository, ref: Optional[str] = None) -> None:
    """Restore from stash and remove that stash entry (default stash@{0})."""
    repo.require_repo()
    ref_key = ref or "stash@{0}"
    stash_sha = _stash_commit_for_ref(repo, ref_key)
    if not stash_sha:
        raise PygitError("stash not found" + (f": {ref}" if ref else ""))
    _restore_stash(repo, stash_sha)
    _drop_stash_entry(repo, ref_key)


def _restore_stash(repo: Repository, stash_commit_sha: str) -> None:
    """Restore index and worktree from stash commit (2 parents: head, index commit)."""
    from .objects import Commit
    obj = repo.load_object(stash_commit_sha)
    if obj.type != "commit":
        raise PygitError("stash entry is not a commit")
    commit = Commit.from_content(obj.content)
    if len(commit.parent_hashes) < 2:
        raise PygitError("invalid stash entry (expected 2 parents)")
    index_commit_sha = commit.parent_hashes[1]
    index_tree = _tree_hash_for_commit(repo, index_commit_sha)
    worktree_tree = commit.tree_hash
    if not index_tree or not worktree_tree:
        raise PygitError("invalid stash entry")
    repo.restore_index_from_tree(index_tree)
    repo.restore_tree(worktree_tree, repo.path)


def _tree_hash_for_commit(repo: Repository, commit_sha: str) -> Optional[str]:
    from .objects import Commit
    obj = repo.load_object(commit_sha)
    if obj.type != "commit":
        return None
    return Commit.from_content(obj.content).tree_hash


def _drop_stash_entry(repo: Repository, ref_key: str) -> None:
    """Remove stash@{0} by updating ref and rewriting reflog."""
    entries = read_reflog(repo, STASH_REF)
    if not entries:
        return
    if ref_key != "stash@{0}" and ref_key != "stash":
        try:
            n = int(ref_key[7:-1])
            if n != 0:
                raise PygitError("stash pop only supports stash@{0} for now")
        except ValueError:
            return
    if len(entries) <= 1:
        path = repo.git_dir / STASH_REF
        if path.exists():
            path.unlink()
    else:
        _, next_sha, _, _, _, _ = entries[-(1 + 1)]
        update_ref(repo.git_dir, STASH_REF, next_sha)
    path = repo.git_dir / "logs" / STASH_REF
    if not path.exists():
        return
    new_lines: list[str] = []
    for i, (old_h, new_h, who, ts, tz, msg) in enumerate(entries):
        if i == len(entries) - 1:
            continue
        new_lines.append(f"{old_h} {new_h} {who} {ts} {tz}\t{msg}\n")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("".join(new_lines))


def _current_branch_for_message(repo: Repository) -> Optional[str]:
    from .refs import current_branch_name
    return current_branch_name(repo.git_dir)
