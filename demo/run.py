"""Run PyGit demos in isolated temp dirs. Usage: python -m demo.run [demo_name]."""

from __future__ import annotations

import os
import subprocess
import sys
import tempfile
from pathlib import Path


def repo_root() -> Path:
    return Path(__file__).resolve().parent.parent


def run_pygit(cwd: Path, *args: str, env: dict | None = None) -> tuple[int, str, str]:
    e = os.environ.copy()
    e["PYTHONPATH"] = str(repo_root())
    if env:
        e.update(env)
    r = subprocess.run(
        [sys.executable, "-m", "pygit"] + list(args),
        cwd=cwd,
        capture_output=True,
        text=True,
        env=e,
        timeout=30,
    )
    return (r.returncode, r.stdout or "", r.stderr or "")


def demo_basic_workflow(verbose: bool = True) -> int:
    """Init, add files, commit, log, status."""
    tmp = Path(tempfile.mkdtemp(prefix="pygit_demo_basic_"))
    try:
        if verbose:
            print(f"Demo: basic workflow (dir: {tmp})")
        code, out, err = run_pygit(tmp, "init")
        if code != 0:
            print(f"init failed: {err}")
            return 1
        if verbose:
            print(out.strip() or "Repository initialized.")
        (tmp / "hello.txt").write_text("Hello, PyGit!\n")
        (tmp / "readme.md").write_text("# Demo\n")
        code, out, err = run_pygit(tmp, "add", "hello.txt", "readme.md")
        if code != 0:
            print(f"add failed: {err}")
            return 1
        if verbose:
            print(out.strip() or "Files staged.")
        code, out, err = run_pygit(tmp, "commit", "-m", "First commit")
        if code != 0:
            print(f"commit failed: {err}")
            return 1
        if verbose:
            print(out.strip())
        code, out, err = run_pygit(tmp, "log", "-n", "1")
        if verbose:
            print(out.strip() or "(no log)")
        code, out, err = run_pygit(tmp, "status")
        if verbose:
            print(out.strip() or "(status)")
        return 0
    finally:
        import shutil
        shutil.rmtree(tmp, ignore_errors=True)


def demo_branches_and_merge(verbose: bool = True) -> int:
    """Init, commit, create branch, commit on branch, merge."""
    tmp = Path(tempfile.mkdtemp(prefix="pygit_demo_branch_"))
    try:
        if verbose:
            print(f"Demo: branches and merge (dir: {tmp})")
        run_pygit(tmp, "init")
        (tmp / "a").write_text("a\n")
        run_pygit(tmp, "add", "a")
        run_pygit(tmp, "commit", "-m", "First")
        run_pygit(tmp, "checkout", "-b", "feature")
        (tmp / "b").write_text("b\n")
        run_pygit(tmp, "add", "b")
        run_pygit(tmp, "commit", "-m", "On feature")
        run_pygit(tmp, "checkout", "main")
        code, out, err = run_pygit(tmp, "merge", "feature")
        if code != 0 and "conflict" in (out + err).lower():
            print("Merge conflict (expected in some setups)")
            return 0
        if verbose:
            print(out.strip() or "Merge done.")
        return 0
    finally:
        import shutil
        shutil.rmtree(tmp, ignore_errors=True)


def demo_clone_local(verbose: bool = True) -> int:
    """Create source repo, clone it into dest, show log in dest."""
    base = Path(tempfile.mkdtemp(prefix="pygit_demo_clone_"))
    try:
        src = base / "src"
        dest = base / "dest"
        src.mkdir()
        dest.mkdir()
        if verbose:
            print(f"Demo: clone local (src: {src}, dest: {dest})")
        run_pygit(src, "init")
        (src / "f").write_text("file\n")
        run_pygit(src, "add", "f")
        run_pygit(src, "commit", "-m", "Initial")
        code, out, err = run_pygit(base, "clone", str(src), str(dest))
        if code != 0:
            print(f"clone failed: {err}")
            return 1
        if verbose:
            print(out.strip() or "Cloned.")
        code, out, err = run_pygit(dest, "log", "-n", "1")
        if verbose:
            print(out.strip() or "(log)")
        return 0
    finally:
        import shutil
        shutil.rmtree(base, ignore_errors=True)


def demo_tags(verbose: bool = True) -> int:
    """Init, commit, lightweight tag, annotated tag, list tags."""
    tmp = Path(tempfile.mkdtemp(prefix="pygit_demo_tags_"))
    try:
        if verbose:
            print(f"Demo: tags (dir: {tmp})")
        run_pygit(tmp, "init")
        (tmp / "x").write_text("x\n")
        run_pygit(tmp, "add", "x")
        run_pygit(tmp, "commit", "-m", "First")
        run_pygit(tmp, "tag", "v1")
        run_pygit(tmp, "tag", "-a", "v2", "-m", "Annotated v2")
        code, out, err = run_pygit(tmp, "tag")
        if verbose:
            print(out.strip() or "(tags)")
        return 0
    finally:
        import shutil
        shutil.rmtree(tmp, ignore_errors=True)


DEMOS = {
    "basic": ("Init, add, commit, log, status", demo_basic_workflow),
    "branches": ("Branches and merge", demo_branches_and_merge),
    "clone": ("Clone local repo", demo_clone_local),
    "tags": ("Lightweight and annotated tags", demo_tags),
}


def main() -> int:
    import argparse
    p = argparse.ArgumentParser(description="Run PyGit demos")
    p.add_argument("demo", nargs="?", default=None, help="Demo name (basic, branches, clone, tags) or all")
    p.add_argument("-q", "--quiet", action="store_true", help="Less output")
    args = p.parse_args()
    verbose = not args.quiet
    if args.demo is None or args.demo == "all":
        failed = 0
        for name, (desc, fn) in DEMOS.items():
            if verbose:
                print(f"\n--- {name}: {desc} ---")
            if fn(verbose=verbose) != 0:
                failed += 1
        return 1 if failed else 0
    if args.demo not in DEMOS:
        print(f"Unknown demo: {args.demo}. Choose from: {', '.join(DEMOS)}")
        return 1
    _, fn = DEMOS[args.demo]
    return fn(verbose=verbose)


if __name__ == "__main__":
    sys.exit(main())
