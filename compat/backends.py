"""Backends: run git or pygit in a given workspace. Auto-detect system git."""

from __future__ import annotations

import os
import shutil
import subprocess
from pathlib import Path
from typing import List, Optional, Tuple


def git_available() -> bool:
    """Return True if system git is available."""
    return shutil.which("git") is not None


class Backend:
    """Interface for running git-like operations in a workspace."""

    def run(
        self,
        cwd: Path,
        args: List[str],
        env: Optional[dict] = None,
        timeout: float = 30.0,
    ) -> Tuple[int, str, str]:
        """Run command in cwd. Returns (returncode, stdout, stderr)."""
        raise NotImplementedError

    def name(self) -> str:
        """Backend name for reports (e.g. 'git', 'pygit')."""
        raise NotImplementedError


class GitBackend(Backend):
    """System git: invokes 'git' in the workspace."""

    def __init__(self, git_exe: Optional[str] = None) -> None:
        self._git = git_exe or shutil.which("git")
        if not self._git:
            raise RuntimeError("git not found")

    def run(
        self,
        cwd: Path,
        args: List[str],
        env: Optional[dict] = None,
        timeout: float = 30.0,
    ) -> Tuple[int, str, str]:
        # Match pygit default branch (main) for compat scenarios
        if args == ["init"]:
            args = ["-c", "init.defaultBranch=main", "init"]
        full = [self._git] + args
        e = os.environ.copy()
        if env:
            e.update(env)
        try:
            r = subprocess.run(
                full,
                cwd=cwd,
                capture_output=True,
                text=True,
                timeout=timeout,
                env=e,
            )
            return (r.returncode, r.stdout or "", r.stderr or "")
        except subprocess.TimeoutExpired:
            return (-1, "", "timeout")
        except FileNotFoundError:
            return (-1, "", "git not found")

    def name(self) -> str:
        return "git"


class PyGitBackend(Backend):
    """PyGit CLI: invokes 'python -m pygit' with PYTHONPATH set to repo root."""

    def __init__(self, repo_root: Path) -> None:
        self._repo_root = Path(repo_root).resolve()

    def run(
        self,
        cwd: Path,
        args: List[str],
        env: Optional[dict] = None,
        timeout: float = 30.0,
    ) -> Tuple[int, str, str]:
        full = ["python", "-m", "pygit"] + args
        e = os.environ.copy()
        e["PYTHONPATH"] = str(self._repo_root)
        if env:
            e.update(env)
        try:
            r = subprocess.run(
                full,
                cwd=cwd,
                capture_output=True,
                text=True,
                timeout=timeout,
                env=e,
            )
            return (r.returncode, r.stdout or "", r.stderr or "")
        except subprocess.TimeoutExpired:
            return (-1, "", "timeout")
        except FileNotFoundError:
            return (-1, "", "python not found")

    def name(self) -> str:
        return "pygit"
