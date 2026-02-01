"""Ignore engine: .gitignore and .git/info/exclude with negation and fnmatch."""

from __future__ import annotations

import fnmatch
from pathlib import Path
from typing import List, Optional

from .util import read_text_safe


def _match_pattern(pat: str, rel_path: str, is_dir: bool) -> bool:
    """Match one pattern: trailing / = dir only; / in pat = path from root; else basename."""
    if not pat:
        return False
    dir_only = pat.endswith("/")
    if dir_only:
        pat = pat[:-1]
    rel_path = rel_path.replace("\\", "/")
    if "/" in pat:
        if rel_path == pat or rel_path.startswith(pat + "/"):
            return not dir_only or is_dir
        comp = pat.replace("**/", "*").replace("/**", "/*").replace("**", "*")
        if fnmatch.fnmatch(rel_path, comp) or fnmatch.fnmatch(rel_path, comp + "/*"):
            return not dir_only or is_dir
        return False
    base = rel_path.split("/")[-1] if "/" in rel_path else rel_path
    if not fnmatch.fnmatch(base, pat):
        return False
    return not dir_only or is_dir


class IgnoreMatcher:
    """Match paths against ignore patterns (blank/# ignored, ! negation, / dir-only, * and ?)."""

    def __init__(self, patterns: List[tuple[bool, str]]) -> None:
        self.patterns = patterns

    def is_ignored(self, rel_path: str, is_dir: bool) -> bool:
        """Return True if rel_path (relative to repo root) should be ignored."""
        rel_path = rel_path.replace("\\", "/")
        if rel_path.startswith(".git/") or rel_path == ".git":
            return True
        result = False
        for negated, pat in self.patterns:
            if _match_pattern(pat, rel_path, is_dir):
                result = not negated
        return result


def _parse_patterns(text: Optional[str]) -> List[tuple[bool, str]]:
    out: List[tuple[bool, str]] = []
    if not text:
        return out
    for line in text.splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        negated = line.startswith("!")
        if negated:
            line = line[1:].strip()
        if not line or line.startswith("#"):
            continue
        out.append((negated, line))
    return out


def load_ignore_patterns(repo_root: Path) -> IgnoreMatcher:
    """Load patterns from .gitignore (repo root) and .git/info/exclude. Precedence: .gitignore then exclude."""
    patterns: List[tuple[bool, str]] = []
    gitignore = repo_root / ".gitignore"
    patterns.extend(_parse_patterns(read_text_safe(gitignore)))
    info_exclude = repo_root / ".git" / "info" / "exclude"
    patterns.extend(_parse_patterns(read_text_safe(info_exclude)))
    return IgnoreMatcher(patterns)
