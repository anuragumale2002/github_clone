"""Compat runner: run scenario in both git and pygit workspaces, compare after each step."""

from __future__ import annotations

import argparse
import sys
import tempfile
from pathlib import Path
from typing import Any, Dict, List, Optional

from .backends import Backend, GitBackend, PyGitBackend, git_available
from .compare import (
    compare_clean,
    compare_refs,
    compare_rev_list,
    compare_tree_maps,
    get_head_ref,
    get_ls_tree_map,
    get_rev_list_all,
    get_show_ref,
    get_status_clean,
)
from .ops import run_op, op_from_spec


def run_scenario(
    scenario_ops: List[Dict[str, Any]],
    repo_root: Path,
    keep: bool = False,
    verbose: bool = False,
    failfast: bool = False,
) -> int:
    """
    Create two temp workspaces (git and pygit), run each op in both, compare after each step.
    Returns 0 if all steps match, 1 on first diff or error (if failfast), or 1 if any step failed.
    """
    if not git_available():
        print("SKIP: system git not found")
        return 0
    try:
        git_backend = GitBackend()
    except RuntimeError:
        print("SKIP: system git not found")
        return 0
    pygit_backend = PyGitBackend(repo_root)
    # Deterministic author/date so git and pygit produce same commit SHAs
    deterministic_env = {
        "GIT_AUTHOR_DATE": "1577836800 +0000",
        "GIT_COMMITTER_DATE": "1577836800 +0000",
        "GIT_AUTHOR_NAME": "Compat",
        "GIT_AUTHOR_EMAIL": "compat@test",
        "GIT_COMMITTER_NAME": "Compat",
        "GIT_COMMITTER_EMAIL": "compat@test",
    }
    prefix = "pygit_compat_"
    tmp_git = Path(tempfile.mkdtemp(prefix=prefix + "git_"))
    tmp_pygit = Path(tempfile.mkdtemp(prefix=prefix + "pygit_"))
    if keep:
        print(f"git workspace:   {tmp_git}")
        print(f"pygit workspace: {tmp_pygit}")
    try:
        failed = False
        for i, spec in enumerate(scenario_ops):
            op_name, kwargs = op_from_spec(spec)
            if verbose:
                print(f"  step {i + 1}: {op_name} {kwargs}")
            # Pseudo-op: write file in both workspaces (no backend run)
            if op_name == "write":
                path = kwargs.get("path")
                content = kwargs.get("content", "")
                if path:
                    (tmp_git / path).parent.mkdir(parents=True, exist_ok=True)
                    (tmp_git / path).write_text(content)
                    (tmp_pygit / path).parent.mkdir(parents=True, exist_ok=True)
                    (tmp_pygit / path).write_text(content)
                # Compare state after write (refs, head, rev-list, tree, status)
                refs_g = get_show_ref(git_backend, tmp_git)
                refs_p = get_show_ref(pygit_backend, tmp_pygit)
                ok_refs, diff_refs = compare_refs(refs_g, refs_p)
                if not ok_refs:
                    print(f"FAIL step {i + 1} (write): refs differ")
                    for d in diff_refs[:10]:
                        print(f"  {d}")
                    failed = True
                    if failfast:
                        break
                    continue
                head_g = get_head_ref(git_backend, tmp_git)
                head_p = get_head_ref(pygit_backend, tmp_pygit)
                if head_g != head_p:
                    print(f"FAIL step {i + 1} (write): HEAD git={head_g} pygit={head_p}")
                    failed = True
                    if failfast:
                        break
                    continue
                revs_g = get_rev_list_all(git_backend, tmp_git)
                revs_p = get_rev_list_all(pygit_backend, tmp_pygit)
                ok_revs, diff_revs = compare_rev_list(revs_g, revs_p)
                if not ok_revs:
                    print(f"FAIL step {i + 1} (write): rev-list --all differs")
                    failed = True
                    if failfast:
                        break
                    continue
                tree_g = get_ls_tree_map(git_backend, tmp_git)
                tree_p = get_ls_tree_map(pygit_backend, tmp_pygit)
                ok_tree, diff_tree = compare_tree_maps(tree_g, tree_p)
                if not ok_tree:
                    print(f"FAIL step {i + 1} (write): tree snapshot differs")
                    failed = True
                    if failfast:
                        break
                    continue
                clean_g, _ = get_status_clean(git_backend, tmp_git)
                clean_p, _ = get_status_clean(pygit_backend, tmp_pygit)
                ok_clean, diff_clean = compare_clean(clean_g, clean_p)
                if not ok_clean:
                    print(f"FAIL step {i + 1} (write): status clean differs {diff_clean}")
                    failed = True
                    if failfast:
                        break
                    continue
                if verbose:
                    print(f"  PASS step {i + 1}")
                continue
            code_g, out_g, err_g = run_op(
                git_backend, tmp_git, op_name, env=deterministic_env, **kwargs
            )
            code_p, out_p, err_p = run_op(
                pygit_backend, tmp_pygit, op_name, env=deterministic_env, **kwargs
            )
            if code_g != code_p:
                print(f"FAIL step {i + 1} ({op_name}): exit code git={code_g} pygit={code_p}")
                if verbose and (err_g or err_p):
                    print(f"  git stderr: {err_g[:200]}")
                    print(f"  pygit stderr: {err_p[:200]}")
                failed = True
                if failfast:
                    break
                continue
            # Compare state
            refs_g = get_show_ref(git_backend, tmp_git)
            refs_p = get_show_ref(pygit_backend, tmp_pygit)
            ok_refs, diff_refs = compare_refs(refs_g, refs_p)
            if not ok_refs:
                print(f"FAIL step {i + 1} ({op_name}): refs differ")
                for d in diff_refs[:10]:
                    print(f"  {d}")
                if len(diff_refs) > 10:
                    print(f"  ... and {len(diff_refs) - 10} more")
                failed = True
                if failfast:
                    break
                continue
            head_g = get_head_ref(git_backend, tmp_git)
            head_p = get_head_ref(pygit_backend, tmp_pygit)
            if head_g != head_p:
                print(f"FAIL step {i + 1} ({op_name}): HEAD git={head_g} pygit={head_p}")
                failed = True
                if failfast:
                    break
                continue
            revs_g = get_rev_list_all(git_backend, tmp_git)
            revs_p = get_rev_list_all(pygit_backend, tmp_pygit)
            ok_revs, diff_revs = compare_rev_list(revs_g, revs_p)
            if not ok_revs:
                print(f"FAIL step {i + 1} ({op_name}): rev-list --all differs")
                for d in diff_revs[:5]:
                    print(f"  {d}")
                failed = True
                if failfast:
                    break
                continue
            tree_g = get_ls_tree_map(git_backend, tmp_git)
            tree_p = get_ls_tree_map(pygit_backend, tmp_pygit)
            ok_tree, diff_tree = compare_tree_maps(tree_g, tree_p)
            if not ok_tree:
                print(f"FAIL step {i + 1} ({op_name}): tree snapshot differs")
                for d in diff_tree[:10]:
                    print(f"  {d}")
                failed = True
                if failfast:
                    break
                continue
            clean_g, _ = get_status_clean(git_backend, tmp_git)
            clean_p, _ = get_status_clean(pygit_backend, tmp_pygit)
            ok_clean, diff_clean = compare_clean(clean_g, clean_p)
            if not ok_clean:
                print(f"FAIL step {i + 1} ({op_name}): status clean differs {diff_clean}")
                failed = True
                if failfast:
                    break
                continue
            if verbose:
                print(f"  PASS step {i + 1}")
        if not failed:
            print("PASS")
        return 1 if failed else 0
    finally:
        if not keep:
            import shutil
            shutil.rmtree(tmp_git, ignore_errors=True)
            shutil.rmtree(tmp_pygit, ignore_errors=True)


def load_scenario(name: str) -> Optional[List[Dict[str, Any]]]:
    """Load scenario by name from compat/scenarios/."""
    compat_dir = Path(__file__).resolve().parent
    scenarios_dir = compat_dir / "scenarios"
    # name can be "S1_linear_commits" or "S1" (try both)
    for stem in (name, name.replace("_", ""), name.split("_")[0]):
        path = scenarios_dir / f"{stem}.py"
        if path.is_file():
            break
    else:
        path = scenarios_dir / f"{name}.py"
    if not path.is_file():
        return None
    import importlib.util
    spec = importlib.util.spec_from_file_location("scenario", path)
    if spec is None or spec.loader is None:
        return None
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return getattr(mod, "OPS", None)


def main() -> int:
    parser = argparse.ArgumentParser(description="Run compat scenario: git vs pygit")
    parser.add_argument("scenario", help="Scenario name (e.g. S1_linear_commits)")
    parser.add_argument("--keep", action="store_true", help="Keep temp dirs")
    parser.add_argument("--verbose", "-v", action="store_true", help="Show commands and PASS per step")
    parser.add_argument("--failfast", action="store_true", help="Stop on first failure")
    parser.add_argument("--repo-root", type=Path, default=Path.cwd(), help="PyGit repo root (for PYTHONPATH)")
    args = parser.parse_args()
    ops = load_scenario(args.scenario)
    if ops is None:
        print(f"Scenario not found: {args.scenario}")
        return 1
    return run_scenario(
        ops,
        args.repo_root,
        keep=args.keep,
        verbose=args.verbose,
        failfast=args.failfast,
    )


if __name__ == "__main__":
    sys.exit(main())
