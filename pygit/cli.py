"""CLI: argparse and command dispatch."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from .config import get_user_identity
from .errors import (
    AmbiguousRefError,
    InvalidConfigKeyError,
    InvalidRefError,
    NotARepositoryError,
    ObjectNotFoundError,
    PathOutsideRepoError,
    PygitError,
)
from .plumbing import (
    cat_file_pretty,
    cat_file_type,
    commit_tree,
    hash_object,
    ls_tree,
    merge_base,
    rev_list,
    rev_parse,
    show_ref,
    symbolic_ref,
    update_ref_cmd,
    write_tree,
)
from .gc import gc as gc_run, prune as prune_run, repack as repack_run
from .clone import clone as clone_run
from .fetch import fetch as fetch_run
from .stash import stash_apply, stash_list, stash_pop, stash_save
from .rebase import rebase, rebase_abort, rebase_continue
from .push import push as push_run
from .remote import get_remote_url, remote_add, remote_list, remote_remove
from .porcelain import (
    add_path,
    branch_create,
    branch_delete,
    branch_list,
    checkout_branch,
    cherry_pick,
    cherry_pick_abort,
    cherry_pick_continue,
    commit,
    config_get,
    config_list,
    config_set,
    config_unset,
    diff_repo,
    log,
    merge,
    reflog_show,
    reset_hard,
    reset_mixed,
    reset_soft,
    restore,
    rm_paths,
    show_commit,
    status,
    tag_create_annotated,
    tag_create_lightweight,
    tag_delete,
    tag_list,
)
from .repo import Repository


def _repo() -> Repository:
    return Repository(Path.cwd())


def cmd_init(_: argparse.Namespace) -> int:
    repo = _repo()
    if not repo.init():
        print("Repository already exists")
        return 1
    return 0


def cmd_add(args: argparse.Namespace) -> int:
    repo = _repo()
    try:
        repo.require_repo()
    except NotARepositoryError:
        print("Not a git repository")
        return 1
    for path in args.paths:
        try:
            add_path(repo, path, force=getattr(args, "force", False))
        except (FileNotFoundError, PathOutsideRepoError) as e:
            print(f"Error: {e}")
            return 1
    return 0


def cmd_commit(args: argparse.Namespace) -> int:
    repo = _repo()
    try:
        repo.require_repo()
    except NotARepositoryError:
        print("Not a git repository")
        return 1
    author = args.author or get_user_identity(repo) or "PyGit User <user@pygit.com>"
    result = commit(repo, args.message, author)
    return 0 if result else 1


def cmd_config(args: argparse.Namespace) -> int:
    repo = _repo()
    try:
        repo.require_repo()
    except NotARepositoryError:
        print("Not a git repository")
        return 1
    get_ = getattr(args, "get", False) or args.__dict__.get("get", False)
    set_ = getattr(args, "config_set", False)
    unset_ = getattr(args, "unset", False)
    list_ = getattr(args, "list", False)
    count = sum([get_, set_, unset_, list_])
    if count != 1:
        print("Error: exactly one of --get, --set, --unset, --list required")
        return 1
    try:
        if get_:
            if not args.key:
                print("Error: --get requires <key>")
                return 1
            config_get(repo, args.key)
        elif set_:
            if not args.key or args.value is None:
                print("Error: --set requires <key> <value>")
                return 1
            config_set(repo, args.key, args.value)
        elif unset_:
            if not args.key:
                print("Error: --unset requires <key>")
                return 1
            config_unset(repo, args.key)
        else:
            config_list(repo)
    except (PygitError, InvalidConfigKeyError) as e:
        print(f"Error: {e}")
        return 1
    return 0


def cmd_status(_: argparse.Namespace) -> int:
    repo = _repo()
    try:
        status(repo)
    except NotARepositoryError:
        print("Not a git repository")
        return 1
    return 0


def cmd_reflog(args: argparse.Namespace) -> int:
    repo = _repo()
    try:
        repo.require_repo()
    except NotARepositoryError:
        print("Not a git repository")
        return 1
    ref = args.ref
    if ref == "show":
        ref = None
    reflog_show(repo, ref=ref, max_count=args.max_count)
    return 0


def cmd_branch(args: argparse.Namespace) -> int:
    repo = _repo()
    try:
        repo.require_repo()
    except NotARepositoryError:
        print("Not a git repository")
        return 1
    if args.delete and args.name:
        branch_delete(repo, args.name)
        return 0
    if args.name:
        branch_create(repo, args.name)
        return 0
    branch_list(repo)
    return 0


def cmd_checkout(args: argparse.Namespace) -> int:
    repo = _repo()
    try:
        checkout_branch(repo, args.branch, args.create_branch)
    except (NotARepositoryError, InvalidRefError, ObjectNotFoundError) as e:
        print(f"Error: {e}")
        return 1
    return 0


def cmd_cherry_pick(args: argparse.Namespace) -> int:
    repo = _repo()
    try:
        repo.require_repo()
    except NotARepositoryError:
        print("Not a git repository")
        return 1
    abort = getattr(args, "abort", False)
    cont = getattr(args, "cherry_continue", False)
    if abort and cont:
        print("Error: cannot use both --abort and --continue")
        return 1
    if abort:
        try:
            cherry_pick_abort(repo)
        except PygitError as e:
            print(f"Error: {e}")
            return 1
        return 0
    if cont:
        try:
            cherry_pick_continue(repo)
        except PygitError as e:
            print(f"Error: {e}")
            return 1
        return 0
    if not args.commit:
        print("Error: cherry-pick requires a commit")
        return 1
    try:
        cherry_pick(repo, args.commit)
    except PygitError as e:
        print(f"Error: {e}")
        return 1
    return 0


def cmd_merge(args: argparse.Namespace) -> int:
    repo = _repo()
    try:
        repo.require_repo()
        merge(
            repo,
            args.name,
            force=getattr(args, "force", False),
            ff_only=getattr(args, "ff_only", False),
            no_ff=getattr(args, "no_ff", False),
            no_commit=getattr(args, "no_commit", False),
            message=getattr(args, "message", None),
        )
    except NotARepositoryError:
        print("Not a git repository")
        return 1
    except (PygitError, InvalidRefError, ObjectNotFoundError, AmbiguousRefError) as e:
        print(f"Error: {e}")
        return 1
    return 0


def cmd_log(args: argparse.Namespace) -> int:
    repo = _repo()
    try:
        repo.require_repo()
        log(
            repo,
            rev=getattr(args, "rev", None),
            max_count=args.max_count,
            oneline=getattr(args, "oneline", False),
            graph=getattr(args, "graph", False),
        )
    except NotARepositoryError:
        print("Not a git repository")
        return 1
    except (InvalidRefError, ObjectNotFoundError, AmbiguousRefError) as e:
        print(f"Error: {e}")
        return 1
    return 0


def cmd_diff(args: argparse.Namespace) -> int:
    repo = _repo()
    try:
        diff_repo(repo, args.staged)
    except NotARepositoryError:
        print("Not a git repository")
        return 1
    return 0


def cmd_reset(args: argparse.Namespace) -> int:
    repo = _repo()
    try:
        repo.require_repo()
        if args.soft:
            reset_soft(repo, args.commit)
        elif args.hard:
            reset_hard(repo, args.commit)
        else:
            reset_mixed(repo, args.commit)
    except (NotARepositoryError, InvalidRefError, ObjectNotFoundError, AmbiguousRefError) as e:
        print(f"Error: {e}")
        return 1
    return 0


def cmd_rm(args: argparse.Namespace) -> int:
    repo = _repo()
    try:
        rm_paths(repo, args.paths, cached=args.cached, recursive=args.recursive)
    except (NotARepositoryError, PathOutsideRepoError) as e:
        print(f"Error: {e}")
        return 1
    return 0


def cmd_hash_object(args: argparse.Namespace) -> int:
    repo = _repo()
    try:
        h = hash_object(repo, args.path, write=args.write)
        print(h)
    except (NotARepositoryError, FileNotFoundError, PathOutsideRepoError) as e:
        print(f"Error: {e}")
        return 1
    return 0


def cmd_cat_file(args: argparse.Namespace) -> int:
    repo = _repo()
    try:
        if args.type_only:
            t = cat_file_type(repo, args.object)
            print(t)
        else:
            cat_file_pretty(repo, args.object)
    except (NotARepositoryError, InvalidRefError, ObjectNotFoundError, AmbiguousRefError) as e:
        print(f"Error: {e}")
        return 1
    return 0


def cmd_ls_tree(args: argparse.Namespace) -> int:
    repo = _repo()
    try:
        ls_tree(
            repo,
            args.tree_ish,
            recursive=args.recursive,
            name_only=args.name_only,
        )
    except (NotARepositoryError, InvalidRefError, ObjectNotFoundError, AmbiguousRefError) as e:
        print(f"Error: {e}")
        return 1
    return 0


def cmd_write_tree(_: argparse.Namespace) -> int:
    repo = _repo()
    try:
        tree_hash = write_tree(repo)
        print(tree_hash)
    except NotARepositoryError:
        print("Not a git repository")
        return 1
    return 0


def cmd_commit_tree(args: argparse.Namespace) -> int:
    repo = _repo()
    try:
        sha = commit_tree(
            repo,
            args.tree,
            parent_hashes=args.parent or [],
            message=args.message,
            author=args.author,
            committer=args.committer,
        )
        print(sha)
    except (NotARepositoryError, ObjectNotFoundError) as e:
        print(f"Error: {e}")
        return 1
    return 0


def cmd_merge_base(args: argparse.Namespace) -> int:
    repo = _repo()
    try:
        repo.require_repo()
        result = merge_base(repo, args.rev_a, args.rev_b)
        if result is None:
            return 1
        print(result)
    except (NotARepositoryError, InvalidRefError, ObjectNotFoundError, AmbiguousRefError) as e:
        print(f"Error: {e}")
        return 1
    return 0


def cmd_rev_list(args: argparse.Namespace) -> int:
    repo = _repo()
    try:
        repo.require_repo()
        rev_list(
            repo,
            rev=args.rev,
            max_count=args.max_count,
            parents=args.parents,
            all_refs=args.all,
        )
    except (NotARepositoryError, InvalidRefError, ObjectNotFoundError, AmbiguousRefError) as e:
        print(f"Error: {e}")
        return 1
    return 0


def cmd_rev_parse(args: argparse.Namespace) -> int:
    repo = _repo()
    try:
        h = rev_parse(repo, args.name)
        print(h)
    except (NotARepositoryError, InvalidRefError, ObjectNotFoundError, AmbiguousRefError) as e:
        print(f"Error: {e}")
        return 1
    return 0


def cmd_gc(args: argparse.Namespace) -> int:
    repo = _repo()
    try:
        repo.require_repo()
    except NotARepositoryError:
        print("Not a git repository")
        return 1
    pack_sha = gc_run(repo, prune_loose=getattr(args, "prune", False))
    if pack_sha:
        print(f"Pack written: pack-{pack_sha}.pack")
    return 0


def cmd_repack(_: argparse.Namespace) -> int:
    repo = _repo()
    try:
        repo.require_repo()
    except NotARepositoryError:
        print("Not a git repository")
        return 1
    pack_sha = gc_run(repo, prune_loose=False)
    if pack_sha:
        print(f"Pack written: pack-{pack_sha}.pack")
    return 0


def cmd_prune(_: argparse.Namespace) -> int:
    repo = _repo()
    try:
        repo.require_repo()
    except NotARepositoryError:
        print("Not a git repository")
        return 1
    prune_run(repo)
    return 0


def cmd_remote(args: argparse.Namespace) -> int:
    repo = _repo()
    try:
        repo.require_repo()
    except NotARepositoryError:
        print("Not a git repository")
        return 1
    sub = getattr(args, "subcommand", None) or getattr(args, "sub", None)
    if sub == "add":
        if not args.name or not args.url:
            print("Error: remote add <name> <url>")
            return 1
        try:
            remote_add(repo, args.name, args.url)
        except PygitError as e:
            print(f"Error: {e}")
            return 1
        return 0
    if sub == "remove":
        if not args.name:
            print("Error: remote remove <name>")
            return 1
        try:
            remote_remove(repo, args.name)
        except PygitError as e:
            print(f"Error: {e}")
            return 1
        return 0
    # list (default)
    remotes = remote_list(repo)
    if args.verbose or getattr(args, "v", False):
        for name, fetch_url, push_url in remotes:
            print(f"{name}\t{fetch_url} (fetch)")
            print(f"{name}\t{push_url} (push)")
    else:
        for name, _u1, _u2 in remotes:
            print(name)
    return 0


def cmd_fetch(args: argparse.Namespace) -> int:
    repo = _repo()
    try:
        repo.require_repo()
    except NotARepositoryError:
        print("Not a git repository")
        return 1
    refspecs = getattr(args, "refspec", None) or []
    try:
        fetch_run(repo, args.remote, refspecs=refspecs if refspecs else None)
    except PygitError as e:
        print(f"Error: {e}")
        return 1
    return 0


def cmd_push(args: argparse.Namespace) -> int:
    repo = _repo()
    try:
        repo.require_repo()
    except NotARepositoryError:
        print("Not a git repository")
        return 1
    refspec = getattr(args, "refspec", None) or ""
    if not refspec:
        src, dst = "HEAD", "refs/heads/main"
    elif ":" in refspec:
        src, _, dst = refspec.partition(":")
        src, dst = src.strip(), dst.strip()
        if not src or not dst:
            print("Error: push <remote> <src>:<dst>")
            return 1
    else:
        print("Error: push <remote> <src>:<dst>")
        return 1
    try:
        push_run(repo, args.remote, src, dst, force=getattr(args, "force", False))
    except PygitError as e:
        print(f"Error: {e}")
        return 1
    return 0


def cmd_clone(args: argparse.Namespace) -> int:
    try:
        clone_run(args.src, args.dest)
    except PygitError as e:
        print(f"Error: {e}")
        return 1
    return 0


def cmd_stash(args: argparse.Namespace) -> int:
    repo = _repo()
    try:
        repo.require_repo()
    except NotARepositoryError:
        print("Not a git repository")
        return 1
    sub = getattr(args, "stash_subcommand", None)
    if not sub:
        for ref, msg in stash_list(repo):
            print(f"{ref}: {msg}")
        return 0
    try:
        if sub == "save":
            stash_save(repo, message=getattr(args, "message", None))
        elif sub == "list":
            for ref, msg in stash_list(repo):
                print(f"{ref}: {msg}")
        elif sub == "apply":
            stash_apply(repo, ref=getattr(args, "ref", "stash@{0}"))
        elif sub == "pop":
            stash_pop(repo, ref=getattr(args, "ref", "stash@{0}"))
        else:
            print("Usage: pygit stash save|list|apply|pop")
            return 1
    except PygitError as e:
        print(f"Error: {e}")
        return 1
    return 0


def cmd_rebase(args: argparse.Namespace) -> int:
    repo = _repo()
    try:
        repo.require_repo()
    except NotARepositoryError:
        print("Not a git repository")
        return 1
    if getattr(args, "rebase_continue", False):
        try:
            rebase_continue(repo)
        except PygitError as e:
            print(f"Error: {e}")
            return 1
        return 0
    if getattr(args, "abort", False):
        try:
            rebase_abort(repo)
        except PygitError as e:
            print(f"Error: {e}")
            return 1
        return 0
    upstream = getattr(args, "upstream", None)
    if not upstream:
        print("Error: rebase requires upstream (or --continue / --abort)")
        return 1
    try:
        rebase(repo, upstream)
    except PygitError as e:
        print(f"Error: {e}")
        return 1
    return 0


def cmd_compat(args: argparse.Namespace) -> int:
    """Run compat scenario (git vs pygit) from pygit CLI."""
    repo_root = getattr(args, "repo_root", None) or Path(__file__).resolve().parent.parent
    if str(repo_root) not in sys.path:
        sys.path.insert(0, str(repo_root))
    from compat.runner import load_scenario, run_scenario

    scenario_name = getattr(args, "scenario", None)
    if not scenario_name:
        print("Usage: pygit compat <scenario> [--keep] [--verbose] [--failfast] [--repo-root PATH]")
        return 1
    ops = load_scenario(scenario_name)
    if ops is None:
        print(f"Scenario not found: {scenario_name}")
        return 1
    return run_scenario(
        ops,
        repo_root,
        keep=getattr(args, "keep", False),
        verbose=getattr(args, "verbose", False),
        failfast=getattr(args, "failfast", False),
    )


def cmd_show_ref(args: argparse.Namespace) -> int:
    repo = _repo()
    try:
        show_ref(repo, heads_only=args.heads, tags_only=args.tags)
    except NotARepositoryError as e:
        print(f"Error: {e}")
        return 1
    return 0


def cmd_symbolic_ref(args: argparse.Namespace) -> int:
    repo = _repo()
    try:
        symbolic_ref(repo, args.name, args.ref)
    except (NotARepositoryError, InvalidRefError) as e:
        print(f"Error: {e}")
        return 1
    return 0


def cmd_update_ref(args: argparse.Namespace) -> int:
    repo = _repo()
    try:
        update_ref_cmd(repo, args.refname, args.newhash, getattr(args, "oldhash", None))
    except (NotARepositoryError, InvalidRefError) as e:
        print(f"Error: {e}")
        return 1
    return 0


def cmd_show(args: argparse.Namespace) -> int:
    repo = _repo()
    try:
        show_commit(repo, args.commit)
    except (NotARepositoryError, InvalidRefError, ObjectNotFoundError, AmbiguousRefError) as e:
        print(f"Error: {e}")
        return 1
    return 0


def cmd_restore(args: argparse.Namespace) -> int:
    repo = _repo()
    try:
        restore(
            repo,
            args.paths,
            staged=args.staged,
            source=getattr(args, "source", None),
        )
    except (NotARepositoryError, InvalidRefError, ObjectNotFoundError, PathOutsideRepoError) as e:
        print(f"Error: {e}")
        return 1
    return 0


def cmd_tag(args: argparse.Namespace) -> int:
    repo = _repo()
    try:
        repo.require_repo()
    except NotARepositoryError:
        print("Not a git repository")
        return 1
    if args.delete and args.name:
        try:
            tag_delete(repo, args.name)
            print(f"Deleted tag '{args.name}'")
        except InvalidRefError as e:
            print(f"Error: {e}")
            return 1
        return 0
    if args.annotated and args.name:
        message = args.message or ""
        tagger = args.tagger or get_user_identity(repo) or "PyGit User <user@pygit.com>"
        try:
            tag_create_annotated(
                repo,
                args.name,
                target=args.target or "HEAD",
                message=message,
                tagger=tagger,
                force=getattr(args, "force", False),
            )
        except (InvalidRefError, ObjectNotFoundError) as e:
            print(f"Error: {e}")
            return 1
        return 0
    if args.name:
        try:
            tag_create_lightweight(
                repo,
                args.name,
                target=args.target or "HEAD",
                force=getattr(args, "force", False),
            )
        except (InvalidRefError, ObjectNotFoundError) as e:
            print(f"Error: {e}")
            return 1
        return 0
    for t in tag_list(repo):
        print(t)
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(
        prog="pygit",
        description="A minimal git clone (init, add, commit, branch, checkout, log, status, diff, reset, rm, plumbing).",
    )
    sub = parser.add_subparsers(dest="command", help="Commands")

    # init
    sub.add_parser("init", help="Initialize a new repository")

    # add
    p_add = sub.add_parser("add", help="Add files/directories to the staging area")
    p_add.add_argument("paths", nargs="+", help="Paths to add")
    p_add.add_argument("-f", "--force", action="store_true", help="Allow adding ignored files")

    # commit
    p_commit = sub.add_parser("commit", help="Create a commit")
    p_commit.add_argument("-m", "--message", required=True, help="Commit message")
    p_commit.add_argument("--author", help="Author (e.g. Name <email>)")

    # config
    p_config = sub.add_parser("config", help="Read or write config (.git/config)")
    p_config.add_argument("--get", action="store_true", help="Get value for key")
    p_config.add_argument("--set", dest="config_set", action="store_true", help="Set key to value")
    p_config.add_argument("--unset", action="store_true", help="Unset key")
    p_config.add_argument("--list", action="store_true", help="List all key=value")
    p_config.add_argument("key", nargs="?", default=None, help="Config key (section.option)")
    p_config.add_argument("value", nargs="?", default=None, help="Value (for --set)")

    # status
    sub.add_parser("status", help="Show working tree status")

    # reflog
    p_reflog = sub.add_parser("reflog", help="Show reflog for HEAD or ref")
    p_reflog.add_argument("ref", nargs="?", default=None, help="Ref (default: HEAD)")
    p_reflog.add_argument("-n", "--max-count", type=int, default=10, help="Limit entries (default: 10)")

    # branch
    p_branch = sub.add_parser("branch", help="List or create/delete branches")
    p_branch.add_argument("name", nargs="?", help="Branch name")
    p_branch.add_argument("-d", "--delete", action="store_true", help="Delete branch")

    # checkout
    p_checkout = sub.add_parser("checkout", help="Switch branch or create new branch, or detach HEAD")
    p_checkout.add_argument("branch", help="Branch name or commit hash")
    p_checkout.add_argument("-b", "--create-branch", action="store_true", help="Create and switch to new branch")

    # cherry-pick
    p_cherry = sub.add_parser("cherry-pick", help="Apply changes from a commit onto current HEAD")
    p_cherry.add_argument("--abort", action="store_true", help="Abort current cherry-pick")
    p_cherry.add_argument("--continue", dest="cherry_continue", action="store_true", help="Continue after resolving conflicts")
    p_cherry.add_argument("commit", nargs="?", default=None, help="Commit to cherry-pick (ignored with --abort/--continue)")

    # merge
    p_merge = sub.add_parser("merge", help="Merge branch or revision (fast-forward or 3-way)")
    p_merge.add_argument("name", help="Branch name or revision to merge")
    p_merge.add_argument("-f", "--force", action="store_true", help="Proceed even with local changes")
    p_merge.add_argument("--ff-only", action="store_true", help="Refuse non-fast-forward merge")
    p_merge.add_argument("--no-ff", action="store_true", dest="no_ff", help="Always create a merge commit (do not fast-forward)")
    p_merge.add_argument("--no-commit", action="store_true", help="Stage merge but do not commit")
    p_merge.add_argument("-m", "--message", help="Merge commit message")

    # log
    p_log = sub.add_parser("log", help="Show commit log")
    p_log.add_argument("rev", nargs="?", default=None, help="Start from revision (default: HEAD)")
    p_log.add_argument("-n", "--max-count", type=int, default=10, help="Limit number of commits")
    p_log.add_argument("--oneline", action="store_true", help="One line per commit (short hash + message)")
    p_log.add_argument("--graph", action="store_true", help="Prefix with * (merge commits: *   )")

    # diff
    p_diff = sub.add_parser("diff", help="Show changes (working vs index, or index vs HEAD with --staged)")
    p_diff.add_argument("--staged", action="store_true", help="Compare index to HEAD")

    # reset
    p_reset = sub.add_parser("reset", help="Reset HEAD to commit (--soft, --mixed, --hard)")
    p_reset.add_argument("commit", help="Commit to reset to")
    p_reset.add_argument("--soft", action="store_true", help="Only move HEAD")
    p_reset.add_argument("--mixed", action="store_true", help="Reset index too (default)")
    p_reset.add_argument("--hard", action="store_true", help="Reset index and working tree")

    # rm
    p_rm = sub.add_parser("rm", help="Remove from index and optionally working tree")
    p_rm.add_argument("paths", nargs="+", help="Paths to remove")
    p_rm.add_argument("--cached", action="store_true", help="Only remove from index")
    p_rm.add_argument("-r", "--recursive", action="store_true", help="Allow removing directories")

    # hash-object
    p_ho = sub.add_parser("hash-object", help="Compute blob hash (optionally write)")
    p_ho.add_argument("path", help="Path to file")
    p_ho.add_argument("-w", "--write", action="store_true", help="Write object to ODB")

    # cat-file
    p_cat = sub.add_parser("cat-file", help="Show object type or content")
    p_cat.add_argument("-t", "--type", dest="type_only", action="store_true", help="Show type only")
    p_cat.add_argument("-p", "--pretty", action="store_true", help="Pretty-print (default for content)")
    p_cat.add_argument("object", help="Object (hash, ref, or rev)")

    # ls-tree
    p_ls = sub.add_parser("ls-tree", help="List tree contents")
    p_ls.add_argument("-r", "--recursive", action="store_true", help="Recurse into trees")
    p_ls.add_argument("--name-only", action="store_true", help="List names only")
    p_ls.add_argument("tree_ish", help="Tree or commit (e.g. HEAD)")

    # write-tree
    sub.add_parser("write-tree", help="Write index to tree; print tree hash")

    # commit-tree
    p_ct = sub.add_parser("commit-tree", help="Create commit from tree; print commit hash")
    p_ct.add_argument("tree", help="Tree hash")
    p_ct.add_argument("-p", "--parent", action="append", dest="parent", help="Parent commit (repeat for merges)")
    p_ct.add_argument("-m", "--message", required=True, help="Commit message")
    p_ct.add_argument("--author", help="Author")
    p_ct.add_argument("--committer", help="Committer")

    # merge-base
    p_mb = sub.add_parser("merge-base", help="Find common ancestor of two commits")
    p_mb.add_argument("rev_a", help="First revision")
    p_mb.add_argument("rev_b", help="Second revision")

    # rev-list
    p_rl = sub.add_parser("rev-list", help="List commits reachable from revision(s)")
    p_rl.add_argument("rev", nargs="?", default=None, help="Revision (required unless --all)")
    p_rl.add_argument("--max-count", "-n", type=int, default=None, help="Limit number of commits")
    p_rl.add_argument("--parents", action="store_true", help="Print parent hashes on same line")
    p_rl.add_argument("--all", action="store_true", help="List from all refs/heads")

    # rev-parse
    p_rp = sub.add_parser("rev-parse", help="Resolve name to 40-char hash")
    p_rp.add_argument("name", help="Ref or object name")

    # show-ref
    p_sr = sub.add_parser("show-ref", help="List refs (heads and/or tags)")
    p_sr.add_argument("--heads", action="store_true", help="Only refs/heads")
    p_sr.add_argument("--tags", action="store_true", help="Only refs/tags")

    # symbolic-ref
    p_sym = sub.add_parser("symbolic-ref", help="Set symbolic ref (e.g. HEAD)")
    p_sym.add_argument("name", help="Ref name (only HEAD supported)")
    p_sym.add_argument("ref", help="Target ref (e.g. refs/heads/main)")

    # update-ref
    p_ur = sub.add_parser("update-ref", help="Update ref to new hash (optional oldhash check)")
    p_ur.add_argument("refname", help="Ref to update (e.g. refs/heads/main)")
    p_ur.add_argument("newhash", help="New commit hash")
    p_ur.add_argument("oldhash", nargs="?", default=None, help="Current value (optional, for safety)")

    # show
    p_show = sub.add_parser("show", help="Show commit and diff vs parent")
    p_show.add_argument("commit", help="Commit to show (e.g. HEAD)")

    # restore
    p_restore = sub.add_parser("restore", help="Restore working tree or unstage")
    p_restore.add_argument("paths", nargs="+", help="Paths to restore")
    p_restore.add_argument("--staged", action="store_true", help="Unstage (reset index to HEAD)")
    p_restore.add_argument("--source", help="Restore from commit (default: index or HEAD)")

    # tag
    p_tag = sub.add_parser("tag", help="List, create, or delete tags")
    p_tag.add_argument("name", nargs="?", help="Tag name")
    p_tag.add_argument("target", nargs="?", default=None, help="Target commit (default: HEAD)")
    p_tag.add_argument("-a", "--annotated", action="store_true", help="Create annotated tag")
    p_tag.add_argument("-m", "--message", help="Tag message (for annotated)")
    p_tag.add_argument("--tagger", help="Tagger name/email (for annotated)")
    p_tag.add_argument("-d", "--delete", action="store_true", help="Delete tag")
    p_tag.add_argument("-f", "--force", action="store_true", help="Overwrite existing tag")

    # gc / repack / prune (Phase 2)
    p_gc = sub.add_parser("gc", help="Pack reachable objects into a pack file")
    p_gc.add_argument("--prune", action="store_true", help="Remove loose objects that are now in pack")
    sub.add_parser("repack", help="Alias for gc (pack reachable objects)")
    p_prune = sub.add_parser("prune", help="Remove loose objects that exist in a pack")

    # remote (Phase 3)
    p_remote = sub.add_parser("remote", help="Add, list, or remove remotes")
    p_remote.add_argument("-v", "--verbose", action="store_true", help="List with URLs")
    p_remote.add_argument("subcommand", nargs="?", choices=["add", "remove"], help="add or remove")
    p_remote.add_argument("name", nargs="?", help="Remote name (e.g. origin)")
    p_remote.add_argument("url", nargs="?", help="URL or path (for add)")

    # fetch (Phase 4)
    p_fetch = sub.add_parser("fetch", help="Fetch from remote (local path only)")
    p_fetch.add_argument("remote", help="Remote name (e.g. origin)")
    p_fetch.add_argument("refspec", nargs="*", help="Optional refspec(s)")

    # push (Phase 5)
    p_push = sub.add_parser("push", help="Push to remote (local path only)")
    p_push.add_argument("remote", help="Remote name (e.g. origin)")
    p_push.add_argument("refspec", nargs="?", help="src:dst (default HEAD:refs/heads/main)")
    p_push.add_argument("--force", "-f", action="store_true", help="Force non-FF update")

    # clone (Phase 6)
    p_clone = sub.add_parser("clone", help="Clone a repository (local path only)")
    p_clone.add_argument("src", help="Source path or URL")
    p_clone.add_argument("dest", help="Destination directory")

    # stash (Phase C)
    p_stash = sub.add_parser("stash", help="Stash working tree and index")
    stash_sub = p_stash.add_subparsers(dest="stash_subcommand")
    p_stash_save = stash_sub.add_parser("save", help="Save stash (optional -m message)")
    p_stash_save.add_argument("-m", "--message", help="Stash message")
    stash_sub.add_parser("list", help="List stashes")
    p_stash_apply = stash_sub.add_parser("apply", help="Apply stash (default stash@{0})")
    p_stash_apply.add_argument("ref", nargs="?", default="stash@{0}", help="stash@{n}")
    p_stash_pop = stash_sub.add_parser("pop", help="Apply and remove stash")
    p_stash_pop.add_argument("ref", nargs="?", default="stash@{0}", help="stash@{n}")

    # rebase (Phase D)
    p_rebase = sub.add_parser("rebase", help="Replay commits onto upstream")
    p_rebase.add_argument("--continue", dest="rebase_continue", action="store_true", help="Continue after resolving conflicts")
    p_rebase.add_argument("--abort", action="store_true", help="Abort rebase and restore branch")
    p_rebase.add_argument("upstream", nargs="?", default=None, help="Upstream branch or commit")

    # compat (git vs pygit scenario runner)
    p_compat = sub.add_parser("compat", help="Run compat scenario: git vs pygit (requires system git)")
    p_compat.add_argument("scenario", help="Scenario name (e.g. S1_linear_commits)")
    p_compat.add_argument("--keep", action="store_true", help="Keep temp dirs")
    p_compat.add_argument("-v", "--verbose", action="store_true", help="Show commands and PASS per step")
    p_compat.add_argument("--failfast", action="store_true", help="Stop on first failure")
    p_compat.add_argument("--repo-root", type=Path, default=None, help="PyGit repo root (default: parent of pygit package)")

    args = parser.parse_args()
    if not args.command:
        parser.print_help()
        return 0

    handlers = {
        "init": cmd_init,
        "add": cmd_add,
        "commit": cmd_commit,
        "config": cmd_config,
        "status": cmd_status,
        "reflog": cmd_reflog,
        "cherry-pick": cmd_cherry_pick,
        "branch": cmd_branch,
        "checkout": cmd_checkout,
        "log": cmd_log,
        "merge": cmd_merge,
        "diff": cmd_diff,
        "reset": cmd_reset,
        "rm": cmd_rm,
        "restore": cmd_restore,
        "show": cmd_show,
        "tag": cmd_tag,
        "merge-base": cmd_merge_base,
        "rev-list": cmd_rev_list,
        "show-ref": cmd_show_ref,
        "symbolic-ref": cmd_symbolic_ref,
        "update-ref": cmd_update_ref,
        "hash-object": cmd_hash_object,
        "cat-file": cmd_cat_file,
        "ls-tree": cmd_ls_tree,
        "write-tree": cmd_write_tree,
        "commit-tree": cmd_commit_tree,
        "rev-parse": cmd_rev_parse,
        "gc": cmd_gc,
        "repack": cmd_repack,
        "prune": cmd_prune,
        "remote": cmd_remote,
        "fetch": cmd_fetch,
        "push": cmd_push,
        "clone": cmd_clone,
        "stash": cmd_stash,
        "rebase": cmd_rebase,
        "compat": cmd_compat,
    }
    handler = handlers.get(args.command)
    if not handler:
        parser.print_help()
        return 1
    try:
        return handler(args) or 0
    except PygitError as e:
        print(f"Error: {e}")
        return 1


if __name__ == "__main__":
    sys.exit(main())
