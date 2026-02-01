"""Compare two repos using stable signals. Normalize ordering and timestamps."""

from __future__ import annotations

import re
from pathlib import Path
from typing import Dict, List, Optional, Set, Tuple

from .backends import Backend


def _normalize_show_ref(stdout: str) -> Set[Tuple[str, str]]:
    """Parse show-ref output into set of (refname, sha). Sorted refs for stable order."""
    result: Set[Tuple[str, str]] = set()
    for line in stdout.strip().splitlines():
        line = line.strip()
        if not line:
            continue
        parts = line.split(None, 1)
        if len(parts) != 2:
            continue
        sha, refname = parts[0], parts[1]
        if len(sha) == 40 and refname:
            result.add((refname, sha.lower()))
    return result


def _normalize_rev_list(stdout: str) -> Set[str]:
    """Parse rev-list output: one hash per line (ignore --parents extra columns)."""
    hashes: Set[str] = set()
    for line in stdout.strip().splitlines():
        line = line.strip()
        if not line:
            continue
        # First column is always the commit hash
        h = line.split()[0]
        if len(h) == 40:
            hashes.add(h.lower())
    return hashes


def _normalize_ls_tree_name_only(stdout: str) -> Dict[str, str]:
    """Parse 'ls-tree -r --name-only HEAD' and return path -> blob id. Need full ls-tree for blob ids."""
    # We need ls-tree without --name-only to get blob ids; caller should use ls_tree without name_only
    # and we parse mode type sha path
    result: Dict[str, str] = {}
    for line in stdout.strip().splitlines():
        line = line.strip()
        if not line:
            continue
        # git ls-tree output: mode type sha\tpath or path
        parts = line.split("\t", 1)
        if len(parts) == 2:
            meta, path = parts[0], parts[1]
            # meta is "mode type sha" (sha 40 chars)
            tokens = meta.split()
            if len(tokens) >= 3 and len(tokens[2]) == 40:
                result[path] = tokens[2].lower()
        else:
            tokens = line.split()
            if len(tokens) >= 4 and len(tokens[2]) == 40:
                result[tokens[3]] = tokens[2].lower()
    return result


def _normalize_status(stdout: str) -> Tuple[bool, str]:
    """Determine if status indicates clean. Return (is_clean, normalized_summary)."""
    out = stdout.strip()
    # "nothing to commit, working tree clean" -> clean; "No commits yet" + "nothing to commit" -> clean
    is_clean = (
        ("nothing to commit" in out and "working tree clean" in out)
        or ("No commits yet" in out and "nothing to commit" in out)
    )
    # Normalize: strip trailing whitespace, collapse multiple newlines
    summary = "\n".join(l.strip() for l in out.splitlines() if l.strip())
    return (is_clean, summary)


def get_show_ref(backend: Backend, cwd: Path) -> Set[Tuple[str, str]]:
    """Run show-ref (heads + tags), return set of (refname, sha)."""
    code, out, err = backend.run(cwd, ["show-ref"])
    if code != 0:
        return set()
    return _normalize_show_ref(out)


def get_rev_list_all(backend: Backend, cwd: Path, max_count: Optional[int] = None) -> Set[str]:
    """Run rev-list --all, return set of commit hashes."""
    args = ["rev-list", "--all"]
    if max_count is not None:
        args.extend(["--max-count", str(max_count)])
    code, out, err = backend.run(cwd, args)
    if code != 0:
        return set()
    return _normalize_rev_list(out)


def get_head_ref(backend: Backend, cwd: Path) -> Optional[str]:
    """Resolve HEAD to 40-char hash (symbolic or detached)."""
    code, out, err = backend.run(cwd, ["rev-parse", "HEAD"])
    if code != 0:
        return None
    h = out.strip().split()[0] if out.strip() else ""
    return h.lower() if len(h) == 40 else None


def get_ls_tree_map(backend: Backend, cwd: Path, tree_ish: str = "HEAD") -> Dict[str, str]:
    """Run ls-tree -r (full output with blob ids), return path -> blob sha."""
    code, out, err = backend.run(cwd, ["ls-tree", "-r", tree_ish])
    if code != 0:
        return {}
    result: Dict[str, str] = {}
    for line in out.strip().splitlines():
        line = line.strip()
        if not line:
            continue
        # git: "mode type sha\tpath" (one tab); pygit: "mode kind\tsha\tpath" (two tabs)
        parts_tab = line.split("\t")
        if len(parts_tab) == 1:
            tokens = line.split()
            if len(tokens) >= 4 and len(tokens[2]) == 40:
                result[tokens[3]] = tokens[2].lower()
        elif len(parts_tab) == 2:
            meta, path = parts_tab[0], parts_tab[1]
            tokens = meta.split()
            if len(tokens) >= 3 and len(tokens[2]) == 40:
                result[path] = tokens[2].lower()
        else:
            # pygit: mode kind\tsha\tpath
            if len(parts_tab) >= 3 and len(parts_tab[1]) == 40:
                result[parts_tab[2]] = parts_tab[1].lower()
    return result


def get_status_clean(backend: Backend, cwd: Path) -> Tuple[bool, str]:
    """Run status, return (is_clean, normalized_output)."""
    code, out, err = backend.run(cwd, ["status"])
    return _normalize_status(out)


def compare_refs(
    refs_a: Set[Tuple[str, str]],
    refs_b: Set[Tuple[str, str]],
) -> Tuple[bool, List[str]]:
    """Compare two ref sets. Return (equal, list of diff messages)."""
    by_name_a = {r: sha for r, sha in refs_a}
    by_name_b = {r: sha for r, sha in refs_b}
    all_refs = set(by_name_a) | set(by_name_b)
    diffs: List[str] = []
    for r in sorted(all_refs):
        sha_a = by_name_a.get(r)
        sha_b = by_name_b.get(r)
        if sha_a is None:
            diffs.append(f"only in B: {r} -> {sha_b}")
        elif sha_b is None:
            diffs.append(f"only in A: {r} -> {sha_a}")
        elif sha_a != sha_b:
            diffs.append(f"ref {r}: A={sha_a} B={sha_b}")
    return (len(diffs) == 0, diffs)


def compare_rev_list(
    revs_a: Set[str],
    revs_b: Set[str],
) -> Tuple[bool, List[str]]:
    """Compare two rev-list sets. Return (equal, list of diff messages)."""
    diffs: List[str] = []
    only_a = revs_a - revs_b
    only_b = revs_b - revs_a
    for h in only_a:
        diffs.append(f"only in A rev-list: {h}")
    for h in only_b:
        diffs.append(f"only in B rev-list: {h}")
    return (len(diffs) == 0, diffs)


def compare_tree_maps(
    map_a: Dict[str, str],
    map_b: Dict[str, str],
) -> Tuple[bool, List[str]]:
    """Compare two path->blob maps. Return (equal, list of diff messages)."""
    diffs: List[str] = []
    all_paths = set(map_a) | set(map_b)
    for p in sorted(all_paths):
        sha_a = map_a.get(p)
        sha_b = map_b.get(p)
        if sha_a is None:
            diffs.append(f"path only in B: {p} -> {sha_b}")
        elif sha_b is None:
            diffs.append(f"path only in A: {p} -> {sha_a}")
        elif sha_a != sha_b:
            diffs.append(f"path {p}: A={sha_a} B={sha_b}")
    return (len(diffs) == 0, diffs)


def compare_clean(
    clean_a: bool,
    clean_b: bool,
) -> Tuple[bool, List[str]]:
    """Compare working tree cleanliness. Return (equal, list of diff messages)."""
    if clean_a == clean_b:
        return (True, [])
    return (False, [f"clean A={clean_a} B={clean_b}"])
