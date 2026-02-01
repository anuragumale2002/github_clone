"""Operation primitives for compat scenarios. All ops are deterministic (no interactive prompts)."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, List, Optional

from .backends import Backend


def run_op(
    backend: Backend,
    cwd: Path,
    op: str,
    env: Optional[dict] = None,
    **kwargs: Any,
) -> tuple[int, str, str]:
    """Execute one operation. Returns (returncode, stdout, stderr). env is passed to backend.run for deterministic commits."""
    if op == "init":
        return backend.run(cwd, ["init"], env=env)
    if op == "add":
        paths = kwargs.get("paths", [])
        force = kwargs.get("force", False)
        args = ["add"]
        if force:
            args.append("-f")
        args.extend(paths)
        return backend.run(cwd, args, env=env)
    if op == "commit":
        msg = kwargs.get("message", "commit")
        author = kwargs.get("author")
        args = ["commit", "-m", msg]
        if author:
            args.extend(["--author", author])
        return backend.run(cwd, args, env=env)
    if op == "status":
        return backend.run(cwd, ["status"], env=env)
    if op == "log":
        n = kwargs.get("max_count", 20)
        rev = kwargs.get("rev")
        args = ["log", "-n", str(n)]
        if rev:
            args.append(rev)
        return backend.run(cwd, args, env=env)
    if op == "branch":
        name = kwargs.get("name")
        delete = kwargs.get("delete", False)
        if delete and name:
            return backend.run(cwd, ["branch", "-d", name], env=env)
        if name:
            return backend.run(cwd, ["branch", name], env=env)
        return backend.run(cwd, ["branch"], env=env)
    if op == "checkout":
        target = kwargs.get("target")
        create_branch = kwargs.get("create_branch", False)
        if not target:
            return (1, "", "checkout requires target")
        args = ["checkout"]
        if create_branch:
            args.extend(["-b", target])
        else:
            args.append(target)
        return backend.run(cwd, args, env=env)
    if op == "merge":
        name = kwargs.get("name")
        ff_only = kwargs.get("ff_only", False)
        no_commit = kwargs.get("no_commit", False)
        message = kwargs.get("message")
        if not name:
            return (1, "", "merge requires name")
        args = ["merge", name]
        if ff_only:
            args.append("--ff-only")
        if no_commit:
            args.append("--no-commit")
        if message:
            args.extend(["-m", message])
        return backend.run(cwd, args, env=env)
    if op == "reset":
        commit = kwargs.get("commit", "HEAD")
        mode = kwargs.get("mode", "mixed")  # soft, mixed, hard
        if mode == "soft":
            args = ["reset", "--soft", commit]
        elif mode == "hard":
            args = ["reset", "--hard", commit]
        else:
            args = ["reset", "--mixed", commit]
        return backend.run(cwd, args, env=env)
    if op == "restore":
        paths = kwargs.get("paths", [])
        staged = kwargs.get("staged", False)
        source = kwargs.get("source")
        if not paths:
            return (1, "", "restore requires paths")
        args = ["restore"]
        if staged:
            args.append("--staged")
        if source:
            args.extend(["--source", source])
        args.extend(paths)
        return backend.run(cwd, args, env=env)
    if op == "tag":
        name = kwargs.get("name")
        target = kwargs.get("target", "HEAD")
        annotated = kwargs.get("annotated", False)
        message = kwargs.get("message", "")
        delete = kwargs.get("delete", False)
        if delete and name:
            return backend.run(cwd, ["tag", "-d", name], env=env)
        if annotated and name:
            args = ["tag", "-a", name, "-m", message or "tag", target]
            return backend.run(cwd, args, env=env)
        if name:
            return backend.run(cwd, ["tag", name, target], env=env)
        return backend.run(cwd, ["tag"], env=env)
    if op == "stash_save":
        msg = kwargs.get("message")
        args = ["stash", "save"]
        if msg:
            args.extend(["-m", msg])
        return backend.run(cwd, args, env=env)
    if op == "stash_list":
        return backend.run(cwd, ["stash", "list"], env=env)
    if op == "stash_apply":
        ref = kwargs.get("ref", "stash@{0}")
        return backend.run(cwd, ["stash", "apply", ref], env=env)
    if op == "stash_pop":
        ref = kwargs.get("ref", "stash@{0}")
        return backend.run(cwd, ["stash", "pop", ref], env=env)
    if op == "rebase":
        upstream = kwargs.get("upstream")
        if not upstream:
            return (1, "", "rebase requires upstream")
        return backend.run(cwd, ["rebase", upstream], env=env)
    if op == "rebase_continue":
        return backend.run(cwd, ["rebase", "--continue"], env=env)
    if op == "rebase_abort":
        return backend.run(cwd, ["rebase", "--abort"], env=env)
    if op == "gc":
        prune = kwargs.get("prune", False)
        args = ["gc"]
        if prune:
            args.append("--prune")
        return backend.run(cwd, args, env=env)
    if op == "repack":
        return backend.run(cwd, ["repack"], env=env)
    if op == "prune":
        return backend.run(cwd, ["prune"], env=env)
    if op == "show_ref":
        heads = kwargs.get("heads_only", False)
        tags = kwargs.get("tags_only", False)
        args = ["show-ref"]
        if heads:
            args.append("--heads")
        if tags:
            args.append("--tags")
        return backend.run(cwd, args, env=env)
    if op == "rev_list":
        rev = kwargs.get("rev", "HEAD")
        all_refs = kwargs.get("all", False)
        max_count = kwargs.get("max_count")
        parents = kwargs.get("parents", False)
        args = ["rev-list"]
        if all_refs:
            args.append("--all")
        else:
            args.append(rev)
        if max_count is not None:
            args.extend(["--max-count", str(max_count)])
        if parents:
            args.append("--parents")
        return backend.run(cwd, args, env=env)
    if op == "rev_parse":
        name = kwargs.get("name", "HEAD")
        return backend.run(cwd, ["rev-parse", name], env=env)
    if op == "ls_tree":
        tree_ish = kwargs.get("tree_ish", "HEAD")
        recursive = kwargs.get("recursive", True)
        name_only = kwargs.get("name_only", True)
        args = ["ls-tree"]
        if recursive:
            args.append("-r")
        if name_only:
            args.append("--name-only")
        args.append(tree_ish)
        return backend.run(cwd, args, env=env)
    return (1, "", f"unknown op: {op}")


def op_from_spec(spec: Dict[str, Any]) -> tuple[str, Dict[str, Any]]:
    """Parse a spec dict into (op_name, kwargs). spec must have 'op' key."""
    spec = dict(spec)
    op = spec.pop("op")
    return (op, spec)
