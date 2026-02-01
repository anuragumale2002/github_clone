"""Rebase: replay commits onto upstream (Phase D). Uses cherry-pick; state in .git/pygit/."""

from __future__ import annotations

from pathlib import Path
from typing import List, Optional

from .errors import PygitError
from .graph import get_commit_parents, is_ancestor
from .plumbing import merge_base, rev_parse
from .porcelain import cherry_pick, cherry_pick_continue
from .refs import current_branch_name, head_commit, update_ref, write_head_detached, write_head_ref
from .reflog import append_reflog
from .repo import Repository
from .util import read_text_safe, write_text_atomic

REBASE_ORIG_HEAD = "REBASE_ORIG_HEAD"
REBASE_UPSTREAM = "REBASE_UPSTREAM"
REBASE_BRANCH = "REBASE_BRANCH"
REBASE_TODO = "REBASE_TODO"
PYGIT_STATE_DIR = "pygit"
ZEROS = "0" * 40


def _rebase_state_dir(repo: Repository) -> Path:
    d = repo.git_dir / PYGIT_STATE_DIR
    d.mkdir(parents=True, exist_ok=True)
    return d


def _rebase_in_progress(repo: Repository) -> bool:
    return (repo.git_dir / PYGIT_STATE_DIR / REBASE_ORIG_HEAD).exists()


def _rebase_read_state(repo: Repository) -> Optional[tuple[str, str, str, List[str]]]:
    """Return (orig_head, upstream, branch, todo_list) or None."""
    d = repo.git_dir / PYGIT_STATE_DIR
    if not (d / REBASE_ORIG_HEAD).exists():
        return None
    orig = (read_text_safe(d / REBASE_ORIG_HEAD) or "").strip() or ZEROS
    up = (read_text_safe(d / REBASE_UPSTREAM) or "").strip() or ZEROS
    branch = (read_text_safe(d / REBASE_BRANCH) or "").strip()
    todo_raw = read_text_safe(d / REBASE_TODO) or ""
    todo_list = [h.strip() for h in todo_raw.splitlines() if len(h.strip()) == 40]
    return (orig, up, branch, todo_list)


def _rebase_write_state(
    repo: Repository,
    orig_head: str,
    upstream: str,
    branch: str,
    todo_list: List[str],
) -> None:
    d = _rebase_state_dir(repo)
    write_text_atomic(d / REBASE_ORIG_HEAD, orig_head + "\n")
    write_text_atomic(d / REBASE_UPSTREAM, upstream + "\n")
    write_text_atomic(d / REBASE_BRANCH, branch + "\n")
    write_text_atomic(d / REBASE_TODO, "\n".join(todo_list) + ("\n" if todo_list else ""))


def _rebase_clear_state(repo: Repository) -> None:
    d = repo.git_dir / PYGIT_STATE_DIR
    for name in (REBASE_ORIG_HEAD, REBASE_UPSTREAM, REBASE_BRANCH, REBASE_TODO):
        (d / name).unlink(missing_ok=True)


def _commits_to_replay(repo: Repository, head_sha: str, upstream_sha: str) -> List[str]:
    """Commits reachable from head via first-parent but not from upstream, oldest first."""
    if head_sha == upstream_sha or is_ancestor(repo, head_sha, upstream_sha):
        return []
    collected: List[str] = []
    h = head_sha
    while h and h != upstream_sha and not is_ancestor(repo, h, upstream_sha):
        collected.append(h)
        parents = get_commit_parents(repo, h)
        h = parents[0] if parents else None
    return list(reversed(collected))


def rebase(repo: Repository, upstream: str) -> None:
    """Rebase current branch onto upstream. Refuse if detached HEAD. Uses cherry-pick per commit."""
    repo.require_repo()
    if _rebase_in_progress(repo):
        raise PygitError(
            "Cannot rebase: rebase already in progress. "
            "Use 'pygit rebase --continue' or 'pygit rebase --abort'."
        )
    from .porcelain import is_dirty
    if is_dirty(repo):
        raise PygitError("Cannot rebase: you have local changes.")

    branch = current_branch_name(repo.git_dir)
    if not branch:
        raise PygitError("Cannot rebase: HEAD is detached. Checkout a branch first.")

    head_sha = head_commit(repo.git_dir)
    if not head_sha:
        raise PygitError("Cannot rebase: no HEAD commit.")
    upstream_sha = rev_parse(repo, upstream, peel=True)
    fork_point = merge_base(repo, head_sha, upstream_sha)
    if fork_point is None:
        raise PygitError("Cannot rebase: no common ancestor.")
    to_replay = _commits_to_replay(repo, head_sha, upstream_sha)
    if not to_replay:
        print("Already up to date.")
        return

    orig_head_file = repo.git_dir / "ORIG_HEAD"
    write_text_atomic(orig_head_file, head_sha + "\n")
    append_reflog(repo, "HEAD", head_sha, upstream_sha, f"rebase: start onto {upstream[:7]}")
    write_head_detached(repo.git_dir, upstream_sha)
    from .porcelain import reset_hard
    reset_hard(repo, upstream_sha)
    _rebase_write_state(repo, head_sha, upstream_sha, branch, to_replay)

    for i, commit_sha in enumerate(to_replay):
        try:
            cherry_pick(repo, commit_sha)
        except PygitError:
            _rebase_write_state(repo, head_sha, upstream_sha, branch, to_replay[i + 1 :])
            raise

    new_head = head_commit(repo.git_dir)
    if new_head:
        refname = f"refs/heads/{branch}"
        update_ref(repo.git_dir, refname, new_head)
        write_head_ref(repo.git_dir, refname)
        append_reflog(repo, "HEAD", upstream_sha, new_head, "rebase: complete")
        append_reflog(repo, refname, head_sha, new_head, "rebase: complete")
    _rebase_clear_state(repo)
    if orig_head_file.exists():
        orig_head_file.unlink(missing_ok=True)
    print("Rebase complete.")


def rebase_continue(repo: Repository) -> None:
    """Resume rebase after resolving conflicts (finish current cherry-pick, then apply rest)."""
    repo.require_repo()
    state = _rebase_read_state(repo)
    if state is None:
        raise PygitError("No rebase in progress.")
    orig_head, upstream_sha, branch, todo_list = state

    cherry_pick_continue(repo)
    remaining = list(todo_list)
    while remaining:
        next_commit = remaining[0]
        remaining = remaining[1:]
        _rebase_write_state(repo, orig_head, upstream_sha, branch, remaining)
        try:
            cherry_pick(repo, next_commit)
        except PygitError:
            raise
    new_head = head_commit(repo.git_dir)
    if new_head and branch:
        refname = f"refs/heads/{branch}"
        update_ref(repo.git_dir, refname, new_head)
        write_head_ref(repo.git_dir, refname)
        append_reflog(repo, refname, orig_head, new_head, "rebase: complete")
    _rebase_clear_state(repo)
    (repo.git_dir / "ORIG_HEAD").unlink(missing_ok=True)
    print("Rebase complete.")


def rebase_abort(repo: Repository) -> None:
    """Abort rebase and restore ORIG_HEAD and branch."""
    repo.require_repo()
    state = _rebase_read_state(repo)
    if state is None:
        raise PygitError("No rebase in progress.")
    orig_head, _upstream, branch, _todo = state
    if orig_head == ZEROS:
        raise PygitError("Cannot abort: ORIG_HEAD is missing.")

    from .porcelain import reset_hard
    d = repo.git_dir / PYGIT_STATE_DIR
    for name in ("CHERRY_PICK_HEAD", "CHERRY_PICK_ORIG_HEAD", "CHERRY_PICK_MSG", "CHERRY_PICK_CONFLICTS"):
        (d / name).unlink(missing_ok=True)
    pre_head = head_commit(repo.git_dir) or ZEROS
    reset_hard(repo, orig_head)
    if branch:
        refname = f"refs/heads/{branch}"
        update_ref(repo.git_dir, refname, orig_head)
        write_head_ref(repo.git_dir, refname)
    append_reflog(repo, "HEAD", pre_head, orig_head, "rebase: abort")
    _rebase_clear_state(repo)
    (repo.git_dir / "ORIG_HEAD").unlink(missing_ok=True)
    print("Rebase aborted.")
