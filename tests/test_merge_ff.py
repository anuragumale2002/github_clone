"""Tests for fast-forward merge: merge on branch, already up to date, non-FF refused, dirty refused."""

import io
import sys
import tempfile
import unittest
from pathlib import Path

from pygit.errors import PygitError
from pygit.refs import head_commit, resolve_ref
from pygit.repo import Repository
from pygit.porcelain import (
    add_path,
    branch_create,
    checkout_branch,
    commit,
    merge,
)
from pygit.constants import REF_HEADS_PREFIX


class TestMergeFastForwardOnBranch(unittest.TestCase):
    """Fast-forward merge on a branch: main at A, feature at B, merge feature -> main at B."""

    def setUp(self) -> None:
        d = tempfile.mkdtemp(prefix="pygit_merge_ff_")
        self.repo_dir = Path(d)
        self.repo = Repository(str(self.repo_dir))
        self.repo.init()
        (self.repo_dir / "f").write_text("a")
        add_path(self.repo, "f")
        self.hash_a = commit(self.repo, "Commit A", author="PyGit <p@x.com>")
        self.assertIsNotNone(self.hash_a)
        self.hash_a = self.hash_a or ""
        branch_create(self.repo, "feature")
        checkout_branch(self.repo, "feature", create=False)
        (self.repo_dir / "f").write_text("b")
        add_path(self.repo, "f")
        self.hash_b = commit(self.repo, "Commit B", author="PyGit <p@x.com>")
        self.assertIsNotNone(self.hash_b)
        self.hash_b = self.hash_b or ""
        checkout_branch(self.repo, "main", create=False)

    def test_merge_fast_forward_main_ref_equals_b(self) -> None:
        merge(self.repo, "feature")
        main_ref = resolve_ref(self.repo.git_dir, REF_HEADS_PREFIX + "main")
        self.assertEqual(main_ref, self.hash_b)

    def test_merge_fast_forward_head_remains_symbolic(self) -> None:
        merge(self.repo, "feature")
        head = head_commit(self.repo.git_dir)
        self.assertEqual(head, self.hash_b)

    def test_merge_fast_forward_working_tree_matches_b(self) -> None:
        merge(self.repo, "feature")
        self.assertEqual((self.repo_dir / "f").read_text(), "b")

    def test_merge_fast_forward_prints_fast_forward(self) -> None:
        out = io.StringIO()
        old_stdout = sys.stdout
        sys.stdout = out
        try:
            merge(self.repo, "feature")
        finally:
            sys.stdout = old_stdout
        self.assertIn("Fast-forward", out.getvalue())


class TestMergeAlreadyUpToDate(unittest.TestCase):
    """Already up to date: main and feature both at B, merge feature -> no change."""

    def setUp(self) -> None:
        d = tempfile.mkdtemp(prefix="pygit_merge_uptodate_")
        self.repo_dir = Path(d)
        self.repo = Repository(str(self.repo_dir))
        self.repo.init()
        (self.repo_dir / "f").write_text("a")
        add_path(self.repo, "f")
        self.hash_a = commit(self.repo, "Commit A", author="PyGit <p@x.com>") or ""
        (self.repo_dir / "f").write_text("b")
        add_path(self.repo, "f")
        self.hash_b = commit(self.repo, "Commit B", author="PyGit <p@x.com>") or ""
        branch_create(self.repo, "other")

    def test_merge_already_up_to_date_prints_message(self) -> None:
        out = io.StringIO()
        old_stdout = sys.stdout
        sys.stdout = out
        try:
            merge(self.repo, "other")
        finally:
            sys.stdout = old_stdout
        self.assertIn("Already up to date", out.getvalue())

    def test_merge_already_up_to_date_ref_unchanged(self) -> None:
        merge(self.repo, "other")
        main_ref = resolve_ref(self.repo.git_dir, REF_HEADS_PREFIX + "main")
        self.assertEqual(main_ref, self.hash_b)


class TestMergeNonFastForwardRefused(unittest.TestCase):
    """Non-fast-forward: diverged history, merge feature -> error, main unchanged."""

    def setUp(self) -> None:
        d = tempfile.mkdtemp(prefix="pygit_merge_nff_")
        self.repo_dir = Path(d)
        self.repo = Repository(str(self.repo_dir))
        self.repo.init()
        (self.repo_dir / "f").write_text("a")
        add_path(self.repo, "f")
        self.hash_a = commit(self.repo, "Commit A", author="PyGit <p@x.com>") or ""
        branch_create(self.repo, "feature")
        (self.repo_dir / "f").write_text("b")
        add_path(self.repo, "f")
        self.hash_b = commit(self.repo, "Commit B", author="PyGit <p@x.com>") or ""
        checkout_branch(self.repo, "feature", create=False)
        (self.repo_dir / "f").write_text("c")
        add_path(self.repo, "f")
        self.hash_c = commit(self.repo, "Commit C", author="PyGit <p@x.com>") or ""
        checkout_branch(self.repo, "main", create=False)

    def test_merge_ff_only_raises_on_non_ff(self) -> None:
        with self.assertRaises(PygitError):
            merge(self.repo, "feature", ff_only=True)

    def test_merge_ff_only_main_ref_unchanged(self) -> None:
        try:
            merge(self.repo, "feature", ff_only=True)
        except PygitError:
            pass
        main_ref = resolve_ref(self.repo.git_dir, REF_HEADS_PREFIX + "main")
        self.assertEqual(main_ref, self.hash_b)


class TestMergeDirtyRefusedUnlessForce(unittest.TestCase):
    """Dirty working tree: merge refused unless --force."""

    def setUp(self) -> None:
        d = tempfile.mkdtemp(prefix="pygit_merge_dirty_")
        self.repo_dir = Path(d)
        self.repo = Repository(str(self.repo_dir))
        self.repo.init()
        (self.repo_dir / "f").write_text("a")
        add_path(self.repo, "f")
        self.hash_a = commit(self.repo, "Commit A", author="PyGit <p@x.com>") or ""
        branch_create(self.repo, "feature")
        checkout_branch(self.repo, "feature", create=False)
        (self.repo_dir / "f").write_text("b")
        add_path(self.repo, "f")
        self.hash_b = commit(self.repo, "Commit B", author="PyGit <p@x.com>") or ""
        checkout_branch(self.repo, "main", create=False)
        (self.repo_dir / "f").write_text("dirty")
        # do not stage

    def test_merge_dirty_refused(self) -> None:
        with self.assertRaises(PygitError):
            merge(self.repo, "feature")

    def test_merge_force_proceeds(self) -> None:
        merge(self.repo, "feature", force=True)
        main_ref = resolve_ref(self.repo.git_dir, REF_HEADS_PREFIX + "main")
        self.assertEqual(main_ref, self.hash_b)
        self.assertEqual((self.repo_dir / "f").read_text(), "b")
