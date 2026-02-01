"""Run PyGit benchmarks. Usage: python -m bench.run [bench_name] [options]."""

from __future__ import annotations

import os
import subprocess
import sys
import tempfile
import time
from pathlib import Path


def repo_root() -> Path:
    return Path(__file__).resolve().parent.parent


def run_pygit(cwd: Path, *args: str) -> tuple[int, str, str]:
    e = os.environ.copy()
    e["PYTHONPATH"] = str(repo_root())
    r = subprocess.run(
        [sys.executable, "-m", "pygit"] + list(args),
        cwd=cwd,
        capture_output=True,
        text=True,
        env=e,
        timeout=120,
    )
    return (r.returncode, r.stdout or "", r.stderr or "")


def bench_n_commits(n: int = 100, verbose: bool = True) -> float:
    """Time creating N commits (one file per commit). Returns elapsed seconds."""
    tmp = Path(tempfile.mkdtemp(prefix="pygit_bench_commits_"))
    try:
        run_pygit(tmp, "init")
        t0 = time.perf_counter()
        for i in range(n):
            (tmp / "f").write_text(f"content {i}\n")
            code, _, err = run_pygit(tmp, "add", "f")
            if code != 0:
                if verbose:
                    print(f"add failed: {err}")
                return -1.0
            code, _, err = run_pygit(tmp, "commit", "-m", f"Commit {i}")
            if code != 0:
                if verbose:
                    print(f"commit failed: {err}")
                return -1.0
        elapsed = time.perf_counter() - t0
        if verbose:
            print(f"bench_n_commits: {n} commits in {elapsed:.2f}s ({elapsed / n * 1000:.1f} ms/commit)")
        return elapsed
    finally:
        import shutil
        shutil.rmtree(tmp, ignore_errors=True)


def bench_status_many_files(n_files: int = 500, verbose: bool = True) -> float:
    """Time status on repo with N tracked files (one commit). Returns elapsed seconds."""
    tmp = Path(tempfile.mkdtemp(prefix="pygit_bench_status_"))
    try:
        run_pygit(tmp, "init")
        for i in range(n_files):
            (tmp / f"f{i}.txt").write_text(f"file {i}\n")
        run_pygit(tmp, "add", ".")
        run_pygit(tmp, "commit", "-m", "Add all")
        t0 = time.perf_counter()
        for _ in range(5):
            run_pygit(tmp, "status")
        elapsed = (time.perf_counter() - t0) / 5
        if verbose:
            print(f"bench_status: {n_files} files, 5 runs avg {elapsed:.3f}s ({elapsed * 1000:.1f} ms/status)")
        return elapsed
    finally:
        import shutil
        shutil.rmtree(tmp, ignore_errors=True)


def bench_clone_local(n_commits: int = 50, verbose: bool = True) -> float:
    """Time cloning a local repo with N commits. Returns elapsed seconds."""
    base = Path(tempfile.mkdtemp(prefix="pygit_bench_clone_"))
    try:
        src = base / "src"
        dest = base / "dest"
        src.mkdir()
        dest.mkdir()
        run_pygit(src, "init")
        (src / "f").write_text("x\n")
        run_pygit(src, "add", "f")
        run_pygit(src, "commit", "-m", "0")
        for i in range(1, n_commits):
            (src / "f").write_text(f"x {i}\n")
            run_pygit(src, "add", "f")
            run_pygit(src, "commit", "-m", str(i))
        t0 = time.perf_counter()
        code, _, err = run_pygit(base, "clone", str(src), str(dest))
        elapsed = time.perf_counter() - t0
        if code != 0:
            if verbose:
                print(f"clone failed: {err}")
            return -1.0
        if verbose:
            print(f"bench_clone: {n_commits} commits, clone in {elapsed:.2f}s")
        return elapsed
    finally:
        import shutil
        shutil.rmtree(base, ignore_errors=True)


BENCHES = {
    "commits": ("N commits (default 100)", bench_n_commits, ["-n"]),
    "status": ("Status with many files (default 500)", bench_status_many_files, ["-f"]),
    "clone": ("Clone local repo (default 50 commits)", bench_clone_local, ["-c"]),
}


def main() -> int:
    import argparse
    p = argparse.ArgumentParser(description="Run PyGit benchmarks")
    p.add_argument("bench", nargs="?", default=None, help="Bench name (commits, status, clone) or all")
    p.add_argument("-n", type=int, default=100, help="Number of commits (commits bench)")
    p.add_argument("-f", "--files", type=int, default=500, dest="files", help="Number of files (status bench)")
    p.add_argument("-c", "--commits", type=int, default=50, dest="clone_commits", help="Commits in source (clone bench)")
    p.add_argument("-q", "--quiet", action="store_true", help="Less output")
    args = p.parse_args()
    verbose = not args.quiet
    if args.bench is None or args.bench == "all":
        for name, (desc, fn, _) in BENCHES.items():
            if verbose:
                print(f"\n--- {name}: {desc} ---")
            if name == "commits":
                fn(args.n, verbose=verbose)
            elif name == "status":
                fn(args.files, verbose=verbose)
            elif name == "clone":
                fn(args.clone_commits, verbose=verbose)
        return 0
    if args.bench not in BENCHES:
        print(f"Unknown bench: {args.bench}. Choose from: {', '.join(BENCHES)}")
        return 1
    _, fn, _ = BENCHES[args.bench]
    if args.bench == "commits":
        fn(args.n, verbose=verbose)
    elif args.bench == "status":
        fn(args.files, verbose=verbose)
    else:
        fn(args.clone_commits, verbose=verbose)
    return 0


if __name__ == "__main__":
    sys.exit(main())
