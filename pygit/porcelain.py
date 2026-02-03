"""Porcelain commands: add, commit, status, branch, checkout, log, reset, rm, diff."""

from __future__ import annotations

import difflib
import time
from dataclasses import dataclass
from pathlib import Path
from typing import List, Optional, Set


@dataclass
class MergeResult:
    """Result of a 3-way merge: conflicts, updated and deleted paths."""

    conflicts: List[str]
    binary_conflicts: List[str]
    updated_paths: List[str]
    deleted_paths: List[str]

from .constants import DEFAULT_BRANCH, MODE_DIR, MODE_FILE, MODE_FILE_EXECUTABLE, OBJ_COMMIT, REF_HEADS_PREFIX, REF_TAGS_PREFIX
from .errors import InvalidConfigKeyError, InvalidRefError, NotARepositoryError, PygitError
from .index import index_entry_for_file, index_entries_unchanged, load_index, save_index
from .objects import Blob, Commit, Tag, Tree
from .plumbing import merge_base, rev_parse
from .refs import (
    current_branch_name,
    head_commit,
    list_branches,
    list_tags,
    read_head,
    resolve_ref,
    update_ref,
    update_ref_verify,
    validate_tag_name,
    write_head_detached,
    write_head_ref,
)
from .reflog import ZEROS, append_reflog, read_reflog
from .graph import is_ancestor
from .ignore import IgnoreMatcher, load_ignore_patterns
from .config import get_user_identity, get_value as config_get_value, list_values as config_list_values, set_value as config_set_value, unset_value as config_unset_value
from .repo import (
    Repository,
    list_tree_paths,
    read_blob_from_tree,
    tree_hash_for_commit,
)
from .util import is_binary, is_executable, read_bytes, read_text_safe, write_bytes_atomic, write_text_atomic


def add_path(repo: Repository, path: str, force: bool = False) -> None:
    """Add file or directory to index. Ignores .git. By default skips ignored files; use force=True to add them."""
    repo.require_repo()
    p = repo.safe_path(path)
    ign = load_ignore_patterns(repo.path)
    if p.is_file():
        if not force and ign.is_ignored(path, is_dir=False):
            return  # skip ignored unless -f
        _add_file(repo, path)
        print(f"Added {path}")
        return
    if p.is_dir():
        count = _add_directory(repo, path, force, ign)
        if count:
            print(f"Added {count} files from directory {path}")
        else:
            print(f"Directory {path} already up to date")
        return
    raise FileNotFoundError(f"Path {path} not found")


def _add_file(repo: Repository, path: str) -> None:
    full = repo.path / path
    content = read_bytes(full)
    blob = Blob(content)
    sha = repo.store_object(blob)
    entries = repo.load_index()
    entries[path] = index_entry_for_file(full, sha)
    repo.save_index(entries)


def _add_directory(
    repo: Repository,
    path: str,
    force: bool,
    ign: IgnoreMatcher,
) -> int:
    full = repo.path / path
    entries = repo.load_index()
    count = 0
    for f in full.rglob("*"):
        if f.is_file() and ".git" not in f.parts:
            rel = str(f.relative_to(repo.path)).replace("\\", "/")
            if not force and ign.is_ignored(rel, is_dir=False):
                continue
            content = f.read_bytes()
            blob = Blob(content)
            sha = repo.store_object(blob)
            entries[rel] = index_entry_for_file(f, sha)
            count += 1
    repo.save_index(entries)
    return count


def commit(
    repo: Repository,
    message: str,
    author: str = "PyGit User <user@pygit.com>",
) -> Optional[str]:
    """Create commit from index; update HEAD/branch. Returns commit hash or None."""
    repo.require_repo()
    tree_hash = repo.create_tree_from_index()
    branch = current_branch_name(repo.git_dir)
    if branch is None:
        branch = DEFAULT_BRANCH  # fallback for init before first commit
    parent_hash = head_commit(repo.git_dir)
    parent_hashes = [parent_hash] if parent_hash else []
    entries = repo.load_index()
    if not entries:
        print("nothing to commit, working tree clean")
        return None
    if parent_hash:
        try:
            parent_obj = repo.load_object(parent_hash)
            parent_commit = Commit.from_content(parent_obj.content)
            if tree_hash == parent_commit.tree_hash:
                print("nothing to commit, working tree clean")
                return None
        except Exception:
            pass
    import os
    from .objects import Commit
    from .util import timestamp_from_env, timestamp_with_tz
    ts, tz = timestamp_from_env("AUTHOR") or timestamp_with_tz(None)
    # Only override author from env when not explicitly set (e.g. compat runs set env)
    author_str = author
    if (not author or author == "PyGit User <user@pygit.com>") and os.environ.get("GIT_AUTHOR_NAME") and os.environ.get("GIT_AUTHOR_EMAIL"):
        author_str = f"{os.environ['GIT_AUTHOR_NAME']} <{os.environ['GIT_AUTHOR_EMAIL']}>"
    committer_str = author_str
    if os.environ.get("GIT_COMMITTER_NAME") and os.environ.get("GIT_COMMITTER_EMAIL"):
        committer_str = f"{os.environ['GIT_COMMITTER_NAME']} <{os.environ['GIT_COMMITTER_EMAIL']}>"
    c = Commit(
        tree_hash=tree_hash,
        parent_hashes=parent_hashes,
        author=author_str,
        committer=committer_str,
        message=message,
        timestamp=ts,
        tz_offset=tz,
    )
    commit_hash = repo.store_object(c)
    refname = f"{REF_HEADS_PREFIX}{branch}"
    old_head = parent_hash or ZEROS
    update_ref(repo.git_dir, refname, commit_hash)
    first_line = message.split("\n")[0].strip()
    append_reflog(repo, "HEAD", old_head, commit_hash, f"commit: {first_line}")
    append_reflog(repo, refname, old_head, commit_hash, f"commit: {first_line}")
    repo.save_index(entries)  # keep index (git does not clear after commit)
    print(f"Created commit {commit_hash[:7]} on branch {branch}")
    return commit_hash


def status(repo: Repository) -> None:
    """Print git-like status: branch/detached, staged, unstaged, untracked, deleted."""
    repo.require_repo()
    branch = current_branch_name(repo.git_dir)
    head = head_commit(repo.git_dir)
    if branch is not None:
        print(f"On branch {branch}")
    else:
        short = head[:7] if head else "???????"
        print(f"HEAD detached at {short}")

    index = repo.load_index()
    head_index: dict = {}
    if head:
        try:
            obj = repo.load_object(head)
            commit = Commit.from_content(obj.content)
            if commit.tree_hash:
                head_index = repo.build_index_from_tree(commit.tree_hash)
        except Exception:
            pass

    ign = load_ignore_patterns(repo.path)
    working: dict = {}
    for f in repo.path.rglob("*"):
        if f.is_file() and ".git" not in f.parts:
            rel = str(f.relative_to(repo.path)).replace("\\", "/")
            if ign.is_ignored(rel, is_dir=False):
                continue
            try:
                blob = Blob(f.read_bytes())
                working[rel] = blob.hash_id()
            except Exception:
                pass

    staged_new = []
    staged_modified = []
    for path in set(index) | set(head_index):
        ent = index.get(path)
        idx_sha = ent.get("sha1", "") if isinstance(ent, dict) else (ent or "")
        head_sha = head_index.get(path, "")
        if idx_sha and not head_sha:
            staged_new.append(path)
        elif idx_sha and head_sha and idx_sha != head_sha:
            staged_modified.append(path)

    unstaged = []
    for path in working:
        if path in index:
            ent = index[path]
            sha = ent.get("sha1", "") if isinstance(ent, dict) else str(ent)
            if working[path] != sha:
                unstaged.append(path)

    untracked = []
    for path in working:
        if path not in index and path not in head_index:
            untracked.append(path)

    deleted = []
    for path in index:
        if path not in working:
            deleted.append(path)

    if staged_new or staged_modified:
        print("\nChanges to be committed:")
        for p in sorted(staged_new):
            print(f"  new file:   {p}")
        for p in sorted(staged_modified):
            print(f"  modified:   {p}")
    if unstaged:
        print("\nChanges not staged for commit:")
        for p in sorted(unstaged):
            print(f"  modified:   {p}")
    if deleted:
        print("\nDeleted files:")
        for p in sorted(deleted):
            print(f"  deleted:   {p}")
    if untracked:
        print("\nUntracked files:")
        for p in sorted(untracked):
            print(f"  {p}")
    if not (staged_new or staged_modified or unstaged or deleted or untracked):
        print("\nnothing to commit, working tree clean")


def _get_index_sha(index: dict, path: str) -> str:
    ent = index.get(path)
    if isinstance(ent, dict):
        return ent.get("sha1", "")
    return str(ent) if ent else ""


def is_dirty(repo: Repository) -> bool:
    """Return True if working tree or index has uncommitted changes (unstaged, staged, deleted, or untracked)."""
    repo.require_repo()
    index = repo.load_index()
    head = head_commit(repo.git_dir)
    head_index: dict = {}
    if head:
        try:
            obj = repo.load_object(head)
            commit = Commit.from_content(obj.content)
            if commit.tree_hash:
                head_index = repo.build_index_from_tree(commit.tree_hash)
        except Exception:
            pass
    ign = load_ignore_patterns(repo.path)
    working: dict = {}
    for f in repo.path.rglob("*"):
        if f.is_file() and ".git" not in f.parts:
            rel = str(f.relative_to(repo.path)).replace("\\", "/")
            if ign.is_ignored(rel, is_dir=False):
                continue
            try:
                blob = Blob(f.read_bytes())
                working[rel] = blob.hash_id()
            except Exception:
                pass
    for path in set(index) | set(head_index):
        ent = index.get(path)
        idx_sha = ent.get("sha1", "") if isinstance(ent, dict) else (ent or "")
        head_sha = head_index.get(path, "")
        if idx_sha != head_sha:
            return True
    for path in working:
        if path in index:
            ent = index[path]
            sha = ent.get("sha1", "") if isinstance(ent, dict) else str(ent)
            if working[path] != sha:
                return True
        else:
            if path not in head_index:
                return True
    for path in index:
        if path not in working:
            return True
    return False


def branch_list(repo: Repository) -> None:
    """List branches with current marked."""
    repo.require_repo()
    current = current_branch_name(repo.git_dir)
    branches = list_branches(repo.git_dir)
    for b in sorted(branches):
        mark = "* " if b == current else "  "
        print(f"{mark}{b}")


def branch_create(repo: Repository, name: str) -> None:
    """Create branch at current HEAD."""
    repo.require_repo()
    h = head_commit(repo.git_dir)
    if not h:
        print("No commits yet, cannot create a branch")
        return
    update_ref(repo.git_dir, f"{REF_HEADS_PREFIX}{name}", h)
    print(f"Created branch {name}")


def branch_delete(repo: Repository, name: str) -> None:
    """Delete branch."""
    repo.require_repo()
    ref = f"{REF_HEADS_PREFIX}{name}"
    path = repo.git_dir / ref
    if not path.exists():
        print(f"Branch {name} not found")
        return
    if current_branch_name(repo.git_dir) == name:
        print(f"Cannot delete current branch {name}")
        return
    path.unlink()
    print(f"Deleted branch {name}")


def checkout_branch(repo: Repository, branch: str, create: bool) -> None:
    """Checkout branch; optionally create. Or checkout commit (detached)."""
    repo.require_repo()
    old_commit = head_commit(repo.git_dir)
    from_desc = current_branch_name(repo.git_dir) or (old_commit[:7] if old_commit else "xxx")
    # Detached: branch is 40-char hex?
    if len(branch) == 40 and all(c in "0123456789abcdef" for c in branch.lower()):
        if not repo.odb.exists(branch):
            raise InvalidRefError(f"commit {branch} not found")
        _checkout_detached(repo, branch)
        append_reflog(repo, "HEAD", old_commit or ZEROS, branch, f"checkout: moving from {from_desc} to {branch[:7]}")
        print(f"Switched to detached HEAD at {branch[:7]}")
        return
    ref = f"{REF_HEADS_PREFIX}{branch}"
    path = repo.git_dir / ref
    if not path.exists():
        if create:
            h = head_commit(repo.git_dir)
            if not h:
                print("No commits yet, cannot create a branch")
                return
            update_ref(repo.git_dir, ref, h)
            write_head_ref(repo.git_dir, ref)
            append_reflog(repo, "HEAD", old_commit or ZEROS, h, f"checkout: moving from {from_desc} to {branch}")
            _restore_working_to_commit(repo, h)
            repo.save_index(build_index_from_tree_entries(repo, h))
            print(f"Created and switched to branch {branch}")
        else:
            print(f"Branch '{branch}' not found.")
            print(f"Use 'python -m pygit checkout -b {branch}' to create and switch.")
        return
    # Switch to existing branch
    write_head_ref(repo.git_dir, ref)
    h = head_commit(repo.git_dir)
    append_reflog(repo, "HEAD", old_commit or ZEROS, h or ZEROS, f"checkout: moving from {from_desc} to {branch}")
    if h:
        _restore_working_to_commit(repo, h)
        repo.save_index(build_index_from_tree_entries(repo, h))
    print(f"Switched to branch {branch}")


def _restore_working_to_commit(repo: Repository, commit_hash: str) -> None:
    """Restore working tree to commit; clear previous tracked files."""
    obj = repo.load_object(commit_hash)
    commit = Commit.from_content(obj.content)
    files_before = repo.get_files_from_tree_recursive(commit.tree_hash)
    for rel in sorted(files_before):
        (repo.path / rel).unlink(missing_ok=True)
        parent = (repo.path / rel).parent
        while parent != repo.path and parent.exists() and not any(parent.iterdir()):
            parent.rmdir()
            parent = parent.parent
    repo.restore_tree(commit.tree_hash, repo.path)


def build_index_from_tree_entries(repo: Repository, commit_hash: str) -> dict:
    """Build index dict (path -> entry) from commit tree."""
    obj = repo.load_object(commit_hash)
    commit = Commit.from_content(obj.content)
    flat = repo.build_index_from_tree(commit.tree_hash)
    return {p: {"sha1": s, "mode": "100644", "size": 0, "mtime_ns": 0} for p, s in flat.items()}


def _checkout_detached(repo: Repository, commit_hash: str) -> None:
    """Switch to detached HEAD at commit. Caller should append HEAD reflog."""
    write_head_detached(repo.git_dir, commit_hash)
    _restore_working_to_commit(repo, commit_hash)
    idx = build_index_from_tree_entries(repo, commit_hash)
    repo.save_index(idx)


def log(
    repo: Repository,
    rev: Optional[str] = None,
    max_count: int = 10,
    oneline: bool = False,
    graph: bool = False,
) -> None:
    """Show commit log from rev (default HEAD). First-parent only. -n limits count.
    --oneline: short hash (7) + first line of message.
    --graph: prefix '*' for normal commits, '*   ' for merge commits (2+ parents).
    """
    repo.require_repo()
    if rev is not None:
        h = rev_parse(repo, rev, peel=True)
    else:
        h = head_commit(repo.git_dir)
    if not h:
        print("No commits yet!")
        return
    n = 0
    while h and n < max_count:
        obj = repo.load_object(h)
        commit = Commit.from_content(obj.content)
        prefix = ""
        if graph:
            prefix = "*   " if len(commit.parent_hashes) >= 2 else "* "
        if oneline:
            short = h[:7]
            first_line = commit.message.split("\n")[0].strip()
            print(f"{prefix}{short} {first_line}")
        else:
            print(f"{prefix}commit {h}")
            print(f"Author: {commit.author}")
            print(f"Date:   {time.strftime('%a %b %d %H:%M:%S %Y', time.localtime(commit._timestamp))} {commit._tz_offset}")
            print()
            print(f"    {commit.message.strip()}")
            print()
        h = commit.parent_hashes[0] if commit.parent_hashes else None
        n += 1


def reset_soft(repo: Repository, commit_ish: str) -> None:
    """Move HEAD/branch to commit; keep index and working tree."""
    repo.require_repo()
    sha = rev_parse(repo, commit_ish)
    branch = current_branch_name(repo.git_dir)
    old_head = head_commit(repo.git_dir) or ZEROS
    msg = f"reset: moving to {sha[:7]}"
    if branch is not None:
        refname = f"{REF_HEADS_PREFIX}{branch}"
        update_ref(repo.git_dir, refname, sha)
        append_reflog(repo, "HEAD", old_head, sha, msg)
        append_reflog(repo, refname, old_head, sha, msg)
    else:
        write_head_detached(repo.git_dir, sha)
        append_reflog(repo, "HEAD", old_head, sha, msg)
    print(f"HEAD moved to {sha[:7]}")


def reset_mixed(repo: Repository, commit_ish: str) -> None:
    """Move HEAD and reset index to commit; keep working tree."""
    repo.require_repo()
    sha = rev_parse(repo, commit_ish)
    branch = current_branch_name(repo.git_dir)
    old_head = head_commit(repo.git_dir) or ZEROS
    msg = f"reset: moving to {sha[:7]}"
    if branch is not None:
        refname = f"{REF_HEADS_PREFIX}{branch}"
        update_ref(repo.git_dir, refname, sha)
        append_reflog(repo, "HEAD", old_head, sha, msg)
        append_reflog(repo, refname, old_head, sha, msg)
    else:
        write_head_detached(repo.git_dir, sha)
        append_reflog(repo, "HEAD", old_head, sha, msg)
    idx = build_index_from_tree_entries(repo, sha)
    repo.save_index(idx)
    print(f"HEAD and index reset to {sha[:7]}")


def reset_hard(repo: Repository, commit_ish: str) -> None:
    """Move HEAD, reset index, and overwrite working tree to commit."""
    repo.require_repo()
    sha = rev_parse(repo, commit_ish)
    branch = current_branch_name(repo.git_dir)
    old_head = head_commit(repo.git_dir) or ZEROS
    msg = f"reset: moving to {sha[:7]}"
    if branch is not None:
        refname = f"{REF_HEADS_PREFIX}{branch}"
        update_ref(repo.git_dir, refname, sha)
        append_reflog(repo, "HEAD", old_head, sha, msg)
        append_reflog(repo, refname, old_head, sha, msg)
    else:
        write_head_detached(repo.git_dir, sha)
        append_reflog(repo, "HEAD", old_head, sha, msg)
    _restore_working_to_commit(repo, sha)
    idx = build_index_from_tree_entries(repo, sha)
    repo.save_index(idx)
    print(f"HEAD, index, and working tree reset to {sha[:7]}")


def _merge_file_content(
    base: Optional[bytes], ours: Optional[bytes], theirs: Optional[bytes]
) -> tuple[Optional[bytes], bool]:
    """Compute merged content for one file. Returns (content or None for delete, conflict)."""
    if ours == theirs:
        return (ours, False)
    if base == ours and base != theirs:
        return (theirs, False)
    if base == theirs and base != ours:
        return (ours, False)
    if base is None:
        if ours is None and theirs is not None:
            return (theirs, False)
        if theirs is None and ours is not None:
            return (ours, False)
        if ours is not None and theirs is not None and ours != theirs:
            return (None, True)
        return (ours, False)
    if ours is None and theirs == base:
        return (None, False)
    if theirs is None and ours == base:
        return (None, False)
    if ours is None and theirs != base:
        return (None, True)
    if theirs is None and ours != base:
        return (None, True)
    return (None, True)


def _apply_merge_result(
    repo: Repository,
    path: str,
    content: Optional[bytes],
) -> None:
    """Write merged content to working tree and update index (add/update or remove)."""
    full = repo.path / path
    entries = repo.load_index()
    if content is None:
        full.unlink(missing_ok=True)
        entries.pop(path, None)
        parent = full.parent
        while parent != repo.path and parent.exists() and not any(parent.iterdir()):
            parent.rmdir()
            parent = parent.parent
        repo.save_index(entries)
        return
    full.parent.mkdir(parents=True, exist_ok=True)
    write_bytes_atomic(full, content)
    blob = Blob(content)
    sha = repo.store_object(blob)
    entries[path] = index_entry_for_file(full, sha)
    repo.save_index(entries)


def three_way_apply(
    repo: Repository,
    base_tree: Optional[str],
    ours_tree: Optional[str],
    theirs_tree: Optional[str],
    label_ours: str = "HEAD",
    label_theirs: str = "theirs",
    *,
    update_working: bool = True,
    update_index: bool = True,
) -> MergeResult:
    """Apply 3-way merge (base, ours, theirs) per path. Returns conflicts and path lists."""
    paths_base: Set[str] = set()
    if base_tree:
        paths_base = list_tree_paths(repo, base_tree)
    paths_ours: Set[str] = set()
    if ours_tree:
        paths_ours = list_tree_paths(repo, ours_tree)
    paths_theirs: Set[str] = set()
    if theirs_tree:
        paths_theirs = list_tree_paths(repo, theirs_tree)
    all_paths = paths_base | paths_ours | paths_theirs

    def get_base(p: str) -> Optional[bytes]:
        if base_tree:
            return read_blob_from_tree(repo, base_tree, p)
        return None

    def get_ours(p: str) -> Optional[bytes]:
        if ours_tree:
            return read_blob_from_tree(repo, ours_tree, p)
        return None

    def get_theirs(p: str) -> Optional[bytes]:
        if theirs_tree:
            return read_blob_from_tree(repo, theirs_tree, p)
        return None

    conflicts: List[str] = []
    binary_conflicts: List[str] = []
    updated_paths: List[str] = []
    deleted_paths: List[str] = []

    results: dict[str, Optional[bytes]] = {}

    for path in sorted(all_paths):
        base_c = get_base(path)
        ours_c = get_ours(path)
        theirs_c = get_theirs(path)
        content, conflict = _merge_file_content(base_c, ours_c, theirs_c)
        if conflict:
            ours_bin = is_binary(ours_c) if ours_c else False
            theirs_bin = is_binary(theirs_c) if theirs_c else False
            if ours_bin or theirs_bin:
                binary_conflicts.append(path)
                if update_working or update_index:
                    write_content = ours_c if ours_c else theirs_c or b""
                    full = repo.path / path
                    full.parent.mkdir(parents=True, exist_ok=True)
                    write_bytes_atomic(full, write_content)
                    if update_index:
                        blob = Blob(write_content)
                        sha = repo.store_object(blob)
                        entries = repo.load_index()
                        entries[path] = index_entry_for_file(full, sha)
                        repo.save_index(entries)
            else:
                conflicts.append(path)
                if update_working or update_index:
                    ours_text = (ours_c or b"").decode("utf-8", errors="replace")
                    theirs_text = (theirs_c or b"").decode("utf-8", errors="replace")
                    marker = f"<<<<<<< {label_ours}\n{ours_text}=======\n{theirs_text}>>>>>>> {label_theirs}\n"
                    marker_bytes = marker.encode("utf-8")
                    full = repo.path / path
                    full.parent.mkdir(parents=True, exist_ok=True)
                    write_bytes_atomic(full, marker_bytes)
                    if update_index:
                        blob = Blob(marker_bytes)
                        sha = repo.store_object(blob)
                        entries = repo.load_index()
                        entries[path] = index_entry_for_file(full, sha)
                        repo.save_index(entries)
        else:
            results[path] = content

    for path, content in results.items():
        if content is None:
            deleted_paths.append(path)
        else:
            updated_paths.append(path)
        if update_working or update_index:
            _apply_merge_result(repo, path, content)

    return MergeResult(
        conflicts=conflicts,
        binary_conflicts=binary_conflicts,
        updated_paths=updated_paths,
        deleted_paths=deleted_paths,
    )


def merge(
    repo: Repository,
    name: str,
    force: bool = False,
    ff_only: bool = False,
    no_ff: bool = False,
    no_commit: bool = False,
    message: Optional[str] = None,
) -> None:
    """Merge branch or revision. Fast-forward when possible (unless no_ff); else 3-way merge.
    Refuse dirty working tree unless force=True. With ff_only, refuse non-FF.
    With no_ff, always create a merge commit (do not fast-forward).
    """
    repo.require_repo()
    target_hash = rev_parse(repo, name, peel=True)
    head_hash = head_commit(repo.git_dir)
    branch = current_branch_name(repo.git_dir)
    head_state = read_head(repo.git_dir)

    if not force and is_dirty(repo):
        raise PygitError("Cannot merge: you have local changes.")

    if head_hash is None:
        old_h = ZEROS
        merge_msg_reflog = f"merge {name}: Fast-forward"
        if head_state is not None and head_state.kind == "ref":
            refname = head_state.value
            if refname.startswith(REF_HEADS_PREFIX):
                update_ref(repo.git_dir, refname, target_hash)
                append_reflog(repo, "HEAD", old_h, target_hash, merge_msg_reflog)
                append_reflog(repo, refname, old_h, target_hash, merge_msg_reflog)
        else:
            write_head_detached(repo.git_dir, target_hash)
            append_reflog(repo, "HEAD", old_h, target_hash, merge_msg_reflog)
        _restore_working_to_commit(repo, target_hash)
        repo.save_index(build_index_from_tree_entries(repo, target_hash))
        short_new = target_hash[:7]
        print(f"Updating 0..{short_new}")
        print("Fast-forward")
        return

    if target_hash == head_hash:
        print("Already up to date.")
        return

    if is_ancestor(repo, head_hash, target_hash) and not no_ff:
        merge_msg_reflog = f"merge {name}: Fast-forward"
        if branch is not None:
            refname = f"{REF_HEADS_PREFIX}{branch}"
            update_ref(repo.git_dir, refname, target_hash)
            append_reflog(repo, "HEAD", head_hash, target_hash, merge_msg_reflog)
            append_reflog(repo, refname, head_hash, target_hash, merge_msg_reflog)
        else:
            write_head_detached(repo.git_dir, target_hash)
            append_reflog(repo, "HEAD", head_hash, target_hash, merge_msg_reflog)
        _restore_working_to_commit(repo, target_hash)
        repo.save_index(build_index_from_tree_entries(repo, target_hash))
        short_old = head_hash[:7]
        short_new = target_hash[:7]
        print(f"Updating {short_old}..{short_new}")
        print("Fast-forward")
        return

    if ff_only:
        raise PygitError("Non-fast-forward merge not implemented (requires 3-way merge).")

    base_hash = merge_base(repo, head_hash, target_hash)
    head_tree = tree_hash_for_commit(repo, head_hash)
    target_tree = tree_hash_for_commit(repo, target_hash)
    base_tree = tree_hash_for_commit(repo, base_hash) if base_hash else None

    result = three_way_apply(
        repo,
        base_tree,
        head_tree,
        target_tree,
        label_ours="HEAD",
        label_theirs=name,
        update_working=True,
        update_index=True,
    )

    if result.conflicts or result.binary_conflicts:
        print("Automatic merge failed; fix conflicts and then commit the result.")
        for p in sorted(result.conflicts):
            print(f"  {p}")
        for p in sorted(result.binary_conflicts):
            print(f"  Binary file conflict: {p}")
        raise PygitError("Merge conflict.")

    if no_commit:
        print("Merge staged; run commit to complete the merge.")
        return

    tree_hash = repo.create_tree_from_index()
    branch = current_branch_name(repo.git_dir)
    merge_msg = message or (
        f"Merge {name} into {branch}" if branch else f"Merge {name}"
    )
    from .util import timestamp_with_tz
    ts, tz = timestamp_with_tz(None)
    c = Commit(
        tree_hash=tree_hash,
        parent_hashes=[head_hash, target_hash],
        author="PyGit User <user@pygit.com>",
        committer="PyGit User <user@pygit.com>",
        message=merge_msg,
        timestamp=ts,
        tz_offset=tz,
    )
    merge_commit_hash = repo.store_object(c)
    merge_msg_reflog = f"merge {name}: Merge made by the 'recursive' strategy."
    if branch is not None:
        refname = f"{REF_HEADS_PREFIX}{branch}"
        update_ref(repo.git_dir, refname, merge_commit_hash)
        append_reflog(repo, "HEAD", head_hash, merge_commit_hash, merge_msg_reflog)
        append_reflog(repo, refname, head_hash, merge_commit_hash, merge_msg_reflog)
    else:
        write_head_detached(repo.git_dir, merge_commit_hash)
        append_reflog(repo, "HEAD", head_hash, merge_commit_hash, merge_msg_reflog)
    print(f"Merge made by 3-way merge. New commit {merge_commit_hash[:7]}")


def rm_paths(repo: Repository, paths: List[str], cached: bool = False, recursive: bool = False) -> None:
    """Remove from index; if not --cached, delete from working dir. -r for dirs."""
    repo.require_repo()
    index = repo.load_index()
    for path in paths:
        p = repo.safe_path(path)
        if p.is_dir():
            if not recursive:
                print(f"error: '{path}' is a directory (use -r)")
                continue
            to_remove = [k for k in index if k == path or k.startswith(path + "/")]
            for k in to_remove:
                del index[k]
                if not cached:
                    full = repo.path / k
                    if full.exists():
                        full.unlink()
            if not cached:
                try:
                    p.rmdir()
                except OSError:
                    pass
        else:
            if path in index:
                del index[path]
                if not cached and p.exists():
                    p.unlink()
            else:
                print(f"error: '{path}' not in index")
    repo.save_index(index)


def diff_repo(repo: Repository, staged: bool) -> None:
    """diff: working vs index. diff --staged: index vs HEAD tree."""
    repo.require_repo()
    index = repo.load_index()
    head = head_commit(repo.git_dir)
    head_tree = {}
    if head:
        try:
            obj = repo.load_object(head)
            c = Commit.from_content(obj.content)
            head_tree = repo.build_index_from_tree(c.tree_hash)
        except Exception:
            pass

    if staged:
        # index vs HEAD
        for path in sorted(set(index) | set(head_tree)):
            idx_ent = index.get(path)
            idx_sha = idx_ent.get("sha1", "") if isinstance(idx_ent, dict) else (idx_ent or "")
            head_sha = head_tree.get(path, "")
            if idx_sha == head_sha:
                continue
            if not head_sha:
                try:
                    blob = repo.load_object(idx_sha)
                    _print_diff(path, b"", blob.content, "added")
                except Exception:
                    pass
            elif not idx_sha:
                try:
                    blob = repo.load_object(head_sha)
                    _print_diff(path, blob.content, b"", "deleted")
                except Exception:
                    pass
            else:
                try:
                    a = repo.load_object(head_sha).content
                    b = repo.load_object(idx_sha).content
                    _print_diff(path, a, b, "modified")
                except Exception:
                    pass
    else:
        # working vs index
        for path in sorted(index.keys()):
            full = repo.path / path
            idx_ent = index[path]
            idx_sha = idx_ent.get("sha1", "") if isinstance(idx_ent, dict) else idx_ent
            if not full.exists():
                try:
                    blob = repo.load_object(idx_sha)
                    _print_diff(path, blob.content, b"", "deleted")
                except Exception:
                    pass
                continue
            if full.is_file():
                try:
                    disk = full.read_bytes()
                    blob = Blob(disk)
                    if blob.hash_id() == idx_sha:
                        continue
                    idx_blob = repo.load_object(idx_sha)
                    _print_diff(path, idx_blob.content, disk, "modified")
                except Exception:
                    pass


def _print_diff(path: str, old: bytes, new: bytes, kind: str) -> None:
    if is_binary(old) or is_binary(new):
        print(f"Binary files {path} differ")
        return
    try:
        a = old.decode("utf-8", errors="replace").splitlines(keepends=True)
        b = new.decode("utf-8", errors="replace").splitlines(keepends=True)
    except Exception:
        print(f"Binary files {path} differ")
        return
    print(f"diff --git a/{path} b/{path}")
    if kind == "added":
        print("new file")
    elif kind == "deleted":
        print("deleted file")
    for line in difflib.unified_diff(a, b, fromfile=f"a/{path}", tofile=f"b/{path}", lineterm=""):
        print(line)
    print()


def diff_trees(
    repo: Repository,
    tree_a: dict[str, str],
    tree_b: dict[str, str],
) -> None:
    """Print unified diff between two trees (path -> blob sha)."""
    for path in sorted(set(tree_a) | set(tree_b)):
        sha_a = tree_a.get(path, "")
        sha_b = tree_b.get(path, "")
        if sha_a == sha_b:
            continue
        if not sha_a:
            try:
                blob = repo.load_object(sha_b)
                _print_diff(path, b"", blob.content, "added")
            except Exception:
                pass
        elif not sha_b:
            try:
                blob = repo.load_object(sha_a)
                _print_diff(path, blob.content, b"", "deleted")
            except Exception:
                pass
        else:
            try:
                a = repo.load_object(sha_a).content
                b = repo.load_object(sha_b).content
                _print_diff(path, a, b, "modified")
            except Exception:
                pass


def show_commit(repo: Repository, commit_ish: str) -> None:
    """Show commit info and diff vs first parent (or empty tree)."""
    repo.require_repo()
    sha = rev_parse(repo, commit_ish)
    obj = repo.load_object(sha)
    if obj.type != "commit":
        raise InvalidRefError(f"object {sha} is not a commit")
    commit = Commit.from_content(obj.content)
    print(f"commit {sha}")
    print(f"Author: {commit.author}")
    print(f"Date:   {time.strftime('%a %b %d %H:%M:%S %Y', time.localtime(commit._timestamp))} {commit._tz_offset}")
    print()
    print(commit.message.strip())
    print()
    tree_commit = repo.build_index_from_tree(commit.tree_hash)
    if commit.parent_hashes:
        parent_tree = repo.build_index_from_tree(
            Commit.from_content(repo.load_object(commit.parent_hashes[0]).content).tree_hash
        )
    else:
        parent_tree = {}
    diff_trees(repo, parent_tree, tree_commit)


def restore(
    repo: Repository,
    paths: List[str],
    staged: bool = False,
    source: Optional[str] = None,
) -> None:
    """restore <paths>: restore working tree from index (or HEAD). restore --staged: unstage (index = HEAD)."""
    repo.require_repo()
    index = repo.load_index()
    head = head_commit(repo.git_dir)
    source_commit = source
    if source_commit is None:
        source_commit = head
    head_tree: dict = {}
    if source_commit:
        try:
            obj = repo.load_object(rev_parse(repo, source_commit))
            c = Commit.from_content(obj.content)
            head_tree = repo.build_index_from_tree(c.tree_hash)
        except Exception:
            pass
    if staged:
        for path in paths:
            if path in head_tree:
                blob_sha = head_tree[path]
                index[path] = {"sha1": blob_sha, "mode": "100644", "size": 0, "mtime_ns": 0, "ctime_ns": 0}
            else:
                index.pop(path, None)
        repo.save_index(index)
        return
    for path in paths:
        p = repo.safe_path(path)
        if p.is_dir():
            continue
        idx_sha = index.get(path)
        if idx_sha is not None:
            ent = idx_sha if isinstance(idx_sha, dict) else {"sha1": idx_sha}
            sha = ent.get("sha1", "") if isinstance(ent, dict) else str(ent)
        else:
            sha = head_tree.get(path, "")
        if not sha:
            continue
        try:
            blob = repo.load_object(sha)
            p.parent.mkdir(parents=True, exist_ok=True)
            p.write_bytes(blob.content)
        except Exception:
            pass


def tag_list(repo: Repository) -> List[str]:
    """List tag names (sorted)."""
    repo.require_repo()
    return sorted(list_tags(repo.git_dir))


def tag_create_lightweight(
    repo: Repository,
    name: str,
    target: str = "HEAD",
    force: bool = False,
) -> None:
    """Create lightweight tag (refs/tags/<name> -> target hash). Target is peeled to non-tag."""
    repo.require_repo()
    validate_tag_name(name)
    refname = f"{REF_TAGS_PREFIX}{name}"
    path = repo.git_dir / refname
    if path.exists() and not force:
        raise InvalidRefError(f"tag '{name}' already exists")
    sha = rev_parse(repo, target, peel=True)
    update_ref_verify(repo.git_dir, refname, sha)


def tag_create_annotated(
    repo: Repository,
    name: str,
    target: str = "HEAD",
    message: str = "",
    tagger: Optional[str] = None,
    force: bool = False,
) -> None:
    """Create annotated tag (Tag object in ODB, refs/tags/<name> -> tag hash)."""
    repo.require_repo()
    validate_tag_name(name)
    refname = f"{REF_TAGS_PREFIX}{name}"
    path = repo.git_dir / refname
    if path.exists() and not force:
        raise InvalidRefError(f"tag '{name}' already exists")
    sha = rev_parse(repo, target)
    obj = repo.load_object(sha)
    object_type = obj.type
    tagger_str = tagger or "PyGit User <user@pygit.com>"
    tag = Tag(
        object_hash=sha,
        object_type=object_type,
        tag_name=name,
        tagger=tagger_str,
        message=message,
    )
    tag_hash = repo.store_object(tag)
    update_ref_verify(repo.git_dir, refname, tag_hash)


def tag_delete(repo: Repository, name: str) -> None:
    """Delete tag (remove refs/tags/<name>)."""
    repo.require_repo()
    validate_tag_name(name)
    refname = f"{REF_TAGS_PREFIX}{name}"
    path = repo.git_dir / refname
    if not path.exists():
        raise InvalidRefError(f"tag '{name}' not found")
    path.unlink()


def config_get(repo: Repository, key: str) -> None:
    """Print config value for key. Raises PygitError if key not found."""
    repo.require_repo()
    val = config_get_value(repo, key)
    if val is None:
        raise PygitError(f"Key not found: {key}")
    print(val)


def config_set(repo: Repository, key: str, value: str) -> None:
    """Set config key to value."""
    repo.require_repo()
    config_set_value(repo, key, value)


def config_unset(repo: Repository, key: str) -> None:
    """Unset config key. Raises PygitError if key not found."""
    repo.require_repo()
    if not config_unset_value(repo, key):
        raise PygitError(f"Key not found: {key}")


def config_list(repo: Repository) -> None:
    """Print key=value lines sorted by key."""
    repo.require_repo()
    for k, v in config_list_values(repo):
        print(f"{k}={v}")


def reflog_show(repo: Repository, ref: Optional[str] = None, max_count: int = 10) -> None:
    """Print reflog entries for ref (default HEAD). Most recent first; -n limits."""
    repo.require_repo()
    if ref is None or ref == "show":
        refname = "HEAD"
        display_ref = "HEAD"
    elif ref == "HEAD" or ref.startswith("refs/heads/") or ref.startswith("refs/tags/"):
        refname = ref
        display_ref = ref
    else:
        refname = f"{REF_HEADS_PREFIX}{ref}"
        display_ref = ref
    entries = read_reflog(repo, refname)
    # Most recent last in file; show most recent first
    shown = list(reversed(entries))[:max_count]
    for idx, (_, new, _, _, _, msg) in enumerate(shown):
        short = new[:7]
        print(f"{short} {display_ref}@{{{idx}}}: {msg}")


# Cherry-pick state under .git/pygit/
PYGIT_STATE_DIR = "pygit"
CHERRY_PICK_HEAD = "CHERRY_PICK_HEAD"
CHERRY_PICK_ORIG_HEAD = "CHERRY_PICK_ORIG_HEAD"
CHERRY_PICK_MSG = "CHERRY_PICK_MSG"
CHERRY_PICK_CONFLICTS = "CHERRY_PICK_CONFLICTS"


def _cherry_pick_state_dir(repo: Repository) -> Path:
    """Path to .git/pygit/ state directory."""
    d = repo.git_dir / PYGIT_STATE_DIR
    d.mkdir(parents=True, exist_ok=True)
    return d


def _cherry_pick_in_progress(repo: Repository) -> bool:
    """True if CHERRY_PICK_HEAD exists."""
    return (repo.git_dir / PYGIT_STATE_DIR / CHERRY_PICK_HEAD).exists()


def _cherry_pick_read_state(repo: Repository) -> Optional[tuple[str, str, str, List[str]]]:
    """Read (pick_hash, orig_head, message, conflicts). None if no cherry-pick in progress."""
    d = repo.git_dir / PYGIT_STATE_DIR
    head_f = d / CHERRY_PICK_HEAD
    if not head_f.exists():
        return None
    pick_hash = read_text_safe(head_f)
    orig_f = d / CHERRY_PICK_ORIG_HEAD
    msg_f = d / CHERRY_PICK_MSG
    conflicts_f = d / CHERRY_PICK_CONFLICTS
    pick_hash = (pick_hash or "").strip()
    orig_head = (read_text_safe(orig_f) or "").strip() or ZEROS
    message = (read_text_safe(msg_f) or "").strip()
    conflicts_raw = read_text_safe(conflicts_f) or ""
    conflicts = [p.strip() for p in conflicts_raw.splitlines() if p.strip()]
    return (pick_hash, orig_head, message, conflicts)


def _cherry_pick_write_state(
    repo: Repository,
    pick_hash: str,
    orig_head: str,
    message: str,
    conflicts: Optional[List[str]] = None,
) -> None:
    """Write cherry-pick state files atomically."""
    d = _cherry_pick_state_dir(repo)
    write_text_atomic(d / CHERRY_PICK_HEAD, pick_hash + "\n")
    write_text_atomic(d / CHERRY_PICK_ORIG_HEAD, orig_head + "\n")
    write_text_atomic(d / CHERRY_PICK_MSG, message.replace("\r", "\n"))
    if conflicts:
        write_text_atomic(d / CHERRY_PICK_CONFLICTS, "\n".join(conflicts) + "\n")
    else:
        (d / CHERRY_PICK_CONFLICTS).unlink(missing_ok=True)


def _cherry_pick_clear_state(repo: Repository) -> None:
    """Remove cherry-pick state files."""
    d = repo.git_dir / PYGIT_STATE_DIR
    for name in (CHERRY_PICK_HEAD, CHERRY_PICK_ORIG_HEAD, CHERRY_PICK_MSG, CHERRY_PICK_CONFLICTS):
        (d / name).unlink(missing_ok=True)


def cherry_pick(repo: Repository, rev: str) -> None:
    """Apply changes introduced by commit onto current HEAD. Raises PygitError on conflict."""
    repo.require_repo()
    if _cherry_pick_in_progress(repo):
        raise PygitError(
            "Cannot cherry-pick: you have a cherry-pick in progress. "
            "Use 'pygit cherry-pick --continue' or 'pygit cherry-pick --abort'."
        )
    if is_dirty(repo):
        raise PygitError("Cannot cherry-pick: you have local changes.")

    pick_hash = rev_parse(repo, rev, peel=True)
    obj = repo.load_object(pick_hash)
    if obj.type != OBJ_COMMIT:
        raise PygitError(f"Object {pick_hash[:7]} is not a commit.")
    pick_commit = Commit.from_content(obj.content)
    parent_hash = pick_commit.parent_hashes[0] if pick_commit.parent_hashes else None

    head_hash = head_commit(repo.git_dir)
    ours_tree = tree_hash_for_commit(repo, head_hash) if head_hash else None
    base_tree = tree_hash_for_commit(repo, parent_hash) if parent_hash else None
    theirs_tree = pick_commit.tree_hash or None

    orig_head = head_hash or ZEROS
    message = (pick_commit.message or "").strip()
    _cherry_pick_write_state(repo, pick_hash, orig_head, message, conflicts=None)

    label_theirs = rev[:7] if len(rev) >= 7 else pick_hash[:7]
    result = three_way_apply(
        repo,
        base_tree,
        ours_tree,
        theirs_tree,
        label_ours="HEAD",
        label_theirs=label_theirs,
        update_working=True,
        update_index=True,
    )

    if result.conflicts or result.binary_conflicts:
        all_conflicts = sorted(result.conflicts) + sorted(result.binary_conflicts)
        _cherry_pick_write_state(repo, pick_hash, orig_head, message, conflicts=all_conflicts)
        subject = (message.split("\n")[0] or "").strip()
        print(f"error: could not apply {pick_hash[:7]} {subject}")
        print("hint: fix conflicts and run 'pygit cherry-pick --continue'")
        print("hint: use 'pygit cherry-pick --abort' to cancel")
        raise PygitError("Cherry-pick conflict.")

    # No conflicts: create commit and clear state
    from .util import timestamp_with_tz
    tree_hash = repo.create_tree_from_index()
    branch = current_branch_name(repo.git_dir)
    author = get_user_identity(repo) or "PyGit User <user@pygit.com>"
    ts, tz = timestamp_with_tz(None)
    c = Commit(
        tree_hash=tree_hash,
        parent_hashes=[head_hash] if head_hash else [],
        author=author,
        committer=author,
        message=message,
        timestamp=ts,
        tz_offset=tz,
    )
    new_hash = repo.store_object(c)
    refname = f"{REF_HEADS_PREFIX}{branch}" if branch else None
    old_head = head_hash or ZEROS
    reflog_msg = f"cherry-pick: {(message.split(chr(10))[0] or '').strip()}"
    if branch:
        update_ref(repo.git_dir, refname, new_hash)
        append_reflog(repo, "HEAD", old_head, new_hash, reflog_msg)
        append_reflog(repo, refname, old_head, new_hash, reflog_msg)
    else:
        write_head_detached(repo.git_dir, new_hash)
        append_reflog(repo, "HEAD", old_head, new_hash, reflog_msg)
    _cherry_pick_clear_state(repo)
    print(f"Created commit {new_hash[:7]} (cherry-pick of {pick_hash[:7]})")


def cherry_pick_continue(repo: Repository) -> None:
    """Finish cherry-pick after resolving conflicts. Raises PygitError if nothing to continue."""
    repo.require_repo()
    state = _cherry_pick_read_state(repo)
    if state is None:
        raise PygitError("No cherry-pick in progress.")
    pick_hash, _orig_head, message, _conflicts = state

    head_hash = head_commit(repo.git_dir)
    entries = repo.load_index()
    if not entries:
        raise PygitError("nothing to commit, working tree clean (cannot continue cherry-pick)")

    from .util import timestamp_with_tz
    tree_hash = repo.create_tree_from_index()
    branch = current_branch_name(repo.git_dir)
    author = get_user_identity(repo) or "PyGit User <user@pygit.com>"
    ts, tz = timestamp_with_tz(None)
    c = Commit(
        tree_hash=tree_hash,
        parent_hashes=[head_hash] if head_hash else [],
        author=author,
        committer=author,
        message=message,
        timestamp=ts,
        tz_offset=tz,
    )
    new_hash = repo.store_object(c)
    refname = f"{REF_HEADS_PREFIX}{branch}" if branch else None
    old_head = head_hash or ZEROS
    subject = (message.split("\n")[0] or "").strip()
    reflog_msg = f"cherry-pick: {subject}"
    if branch:
        update_ref(repo.git_dir, refname, new_hash)
        append_reflog(repo, "HEAD", old_head, new_hash, reflog_msg)
        append_reflog(repo, refname, old_head, new_hash, reflog_msg)
    else:
        write_head_detached(repo.git_dir, new_hash)
        append_reflog(repo, "HEAD", old_head, new_hash, reflog_msg)
    _cherry_pick_clear_state(repo)
    print(f"Created commit {new_hash[:7]} (cherry-pick continued)")


def cherry_pick_abort(repo: Repository) -> None:
    """Abort cherry-pick and restore state. Raises PygitError if no cherry-pick in progress."""
    repo.require_repo()
    state = _cherry_pick_read_state(repo)
    if state is None:
        raise PygitError("No cherry-pick in progress.")
    _pick_hash, orig_head, _message, _conflicts = state
    if orig_head == ZEROS:
        raise PygitError("Cannot abort: ORIG_HEAD is missing.")
    pre_head = head_commit(repo.git_dir) or ZEROS
    reset_hard(repo, orig_head)
    _cherry_pick_clear_state(repo)
    append_reflog(repo, "HEAD", pre_head, orig_head, "cherry-pick: abort")
    print("Cherry-pick aborted.")
