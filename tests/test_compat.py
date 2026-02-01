"""Tests for compat harness: compare helpers and runner smoke."""

import sys
import unittest
from pathlib import Path

# Ensure repo root is on path for compat import
_repo_root = Path(__file__).resolve().parent.parent
if str(_repo_root) not in sys.path:
    sys.path.insert(0, str(_repo_root))

from compat.compare import (
    compare_clean,
    compare_refs,
    compare_rev_list,
    compare_tree_maps,
)
from compat.runner import load_scenario


class TestCompareRefs(unittest.TestCase):
    def test_equal_refs(self) -> None:
        refs = {("refs/heads/main", "a" * 40), ("refs/tags/t1", "b" * 40)}
        ok, diffs = compare_refs(refs, refs)
        self.assertTrue(ok)
        self.assertEqual(diffs, [])

    def test_only_in_a(self) -> None:
        a = {("refs/heads/main", "a" * 40)}
        b: set = set()
        ok, diffs = compare_refs(a, b)
        self.assertFalse(ok)
        self.assertTrue(any("only in B" in d or "only in A" in d for d in diffs))

    def test_different_sha(self) -> None:
        a = {("refs/heads/main", "a" * 40)}
        b = {("refs/heads/main", "b" * 40)}
        ok, diffs = compare_refs(a, b)
        self.assertFalse(ok)
        self.assertTrue(any("ref " in d and "A=" in d for d in diffs))


class TestCompareRevList(unittest.TestCase):
    def test_equal(self) -> None:
        revs = {"a" * 40, "b" * 40}
        ok, diffs = compare_rev_list(revs, revs)
        self.assertTrue(ok)
        self.assertEqual(diffs, [])

    def test_only_in_b(self) -> None:
        a: set = set()
        b = {"a" * 40}
        ok, diffs = compare_rev_list(a, b)
        self.assertFalse(ok)
        self.assertTrue(any("only in B" in d for d in diffs))


class TestCompareTreeMaps(unittest.TestCase):
    def test_equal(self) -> None:
        m = {"a": "x" * 40, "b": "y" * 40}
        ok, diffs = compare_tree_maps(m, m)
        self.assertTrue(ok)
        self.assertEqual(diffs, [])

    def test_different_blob_for_path(self) -> None:
        a = {"f": "a" * 40}
        b = {"f": "b" * 40}
        ok, diffs = compare_tree_maps(a, b)
        self.assertFalse(ok)
        self.assertTrue(any("path f:" in d for d in diffs))


class TestCompareClean(unittest.TestCase):
    def test_both_clean(self) -> None:
        ok, diffs = compare_clean(True, True)
        self.assertTrue(ok)
        self.assertEqual(diffs, [])

    def test_mismatch(self) -> None:
        ok, diffs = compare_clean(True, False)
        self.assertFalse(ok)
        self.assertTrue(any("clean" in d for d in diffs))


class TestLoadScenario(unittest.TestCase):
    def test_s1_returns_ops(self) -> None:
        ops = load_scenario("S1_linear_commits")
        self.assertIsNotNone(ops)
        self.assertIsInstance(ops, list)
        self.assertGreater(len(ops), 0)
        self.assertEqual(ops[0].get("op"), "init")

    def test_s2_branches_returns_ops(self) -> None:
        ops = load_scenario("S2_branches")
        self.assertIsNotNone(ops)
        self.assertEqual(ops[0].get("op"), "init")

    def test_unknown_returns_none(self) -> None:
        self.assertIsNone(load_scenario("nonexistent_scenario_xyz"))


class TestRunnerSmoke(unittest.TestCase):
    """Smoke test: run S1 if system git is available."""

    def test_run_s1_linear_commits(self) -> None:
        from compat.backends import git_available
        from compat.runner import run_scenario

        if not git_available():
            self.skipTest("system git not found")
        ops = load_scenario("S1_linear_commits")
        self.assertIsNotNone(ops)
        code = run_scenario(
            ops,
            _repo_root,
            keep=False,
            verbose=False,
            failfast=True,
        )
        self.assertEqual(code, 0, "S1_linear_commits should pass git vs pygit")
