"""Tests for commit graph tooling: merge-base, rev-list, log with rev/oneline/graph."""

import io
import tempfile
import unittest
from pathlib import Path

from pygit.plumbing import merge_base, rev_list
from pygit.porcelain import (
    add_path,
    branch_create,
    checkout_branch,
    commit,
    log,
)
from pygit.repo import Repository


class TestMergeBase(unittest.TestCase):
    def setUp(self) -> None:
        d = tempfile.mkdtemp(prefix="pygit_graph_")
        self.repo_dir = Path(d)
        self.repo = Repository(str(self.repo_dir))
        self.repo.init()
        (self.repo_dir / "f").write_text("a")
        add_path(self.repo, "f")
        self.hash_a = commit(self.repo, "Commit A", author="PyGit <p@x.com>")
        self.assertIsNotNone(self.hash_a)
        self.hash_a = self.hash_a or ""
        branch_create(self.repo, "feature")
        (self.repo_dir / "f").write_text("b")
        add_path(self.repo, "f")
        self.hash_b = commit(self.repo, "Commit B", author="PyGit <p@x.com>") or ""
        checkout_branch(self.repo, "feature", create=False)
        (self.repo_dir / "f").write_text("c")
        add_path(self.repo, "f")
        self.hash_c = commit(self.repo, "Commit C", author="PyGit <p@x.com>") or ""

    def test_merge_base_main_feature_equals_a(self) -> None:
        result = merge_base(self.repo, "main", "feature")
        self.assertIsNotNone(result)
        self.assertEqual(result, self.hash_a)

    def test_merge_base_feature_main_equals_a(self) -> None:
        result = merge_base(self.repo, "feature", "main")
        self.assertIsNotNone(result)
        self.assertEqual(result, self.hash_a)

    def test_merge_base_same_ref(self) -> None:
        result = merge_base(self.repo, "main", "main")
        self.assertEqual(result, self.hash_b)


class TestRevList(unittest.TestCase):
    def setUp(self) -> None:
        d = tempfile.mkdtemp(prefix="pygit_rl_")
        self.repo_dir = Path(d)
        self.repo = Repository(str(self.repo_dir))
        self.repo.init()
        (self.repo_dir / "f").write_text("x")
        add_path(self.repo, "f")
        self.hash_a = commit(self.repo, "First", author="PyGit <p@x.com>") or ""
        (self.repo_dir / "f").write_text("y")
        add_path(self.repo, "f")
        self.hash_b = commit(self.repo, "Second", author="PyGit <p@x.com>") or ""

    def test_rev_list_head_max_count_2(self) -> None:
        out = io.StringIO()
        import sys
        old = sys.stdout
        sys.stdout = out
        try:
            rev_list(self.repo, rev="HEAD", max_count=2)
        finally:
            sys.stdout = old
        lines = [l for l in out.getvalue().strip().split("\n") if l.strip()]
        self.assertEqual(len(lines), 2)
        self.assertEqual(lines[0], self.hash_b)

    def test_rev_list_parents_one_parent(self) -> None:
        out = io.StringIO()
        import sys
        old = sys.stdout
        sys.stdout = out
        try:
            rev_list(self.repo, rev="HEAD", max_count=1, parents=True)
        finally:
            sys.stdout = old
        line = out.getvalue().strip()
        parts = line.split()
        self.assertGreaterEqual(len(parts), 2)
        self.assertEqual(parts[0], self.hash_b)
        self.assertEqual(parts[1], self.hash_a)


class TestLogRevOneline(unittest.TestCase):
    def setUp(self) -> None:
        d = tempfile.mkdtemp(prefix="pygit_log_")
        self.repo_dir = Path(d)
        self.repo = Repository(str(self.repo_dir))
        self.repo.init()
        (self.repo_dir / "f").write_text("a")
        add_path(self.repo, "f")
        self.hash_a = commit(self.repo, "Commit A message", author="PyGit <p@x.com>") or ""
        (self.repo_dir / "f").write_text("b")
        add_path(self.repo, "f")
        self.hash_b = commit(self.repo, "Commit B message", author="PyGit <p@x.com>") or ""

    def test_log_rev_oneline_shows_commit_at_top(self) -> None:
        out = io.StringIO()
        import sys
        old = sys.stdout
        sys.stdout = out
        try:
            log(self.repo, rev=self.hash_a, max_count=1, oneline=True)
        finally:
            sys.stdout = old
        text = out.getvalue().strip()
        self.assertIn(self.hash_a[:7], text)
        self.assertIn("Commit A message", text)

    def test_log_head_oneline(self) -> None:
        out = io.StringIO()
        import sys
        old = sys.stdout
        sys.stdout = out
        try:
            log(self.repo, rev="HEAD", max_count=1, oneline=True)
        finally:
            sys.stdout = old
        text = out.getvalue().strip()
        self.assertIn(self.hash_b[:7], text)
        self.assertIn("Commit B message", text)
