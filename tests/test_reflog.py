"""Tests for reflog: commit/checkout/reset/merge write reflog; reflog command output."""

import io
import sys
import tempfile
import unittest
from pathlib import Path

from pygit.config import set_value
from pygit.porcelain import (
    add_path,
    checkout_branch,
    commit,
    merge,
    reflog_show,
    reset_hard,
)
from pygit.reflog import read_reflog
from pygit.repo import Repository


class TestCommitWritesReflog(unittest.TestCase):
    """Commit writes HEAD and branch reflog."""

    def setUp(self) -> None:
        d = tempfile.mkdtemp(prefix="pygit_reflog_commit_")
        self.repo_dir = Path(d)
        self.repo = Repository(str(self.repo_dir))
        self.repo.init()
        set_value(self.repo, "user.name", "Alice")
        set_value(self.repo, "user.email", "alice@example.com")

    def test_commit_writes_head_and_branch_reflog(self) -> None:
        (self.repo_dir / "f").write_text("x")
        add_path(self.repo, "f")
        commit(self.repo, "first", author="Alice <alice@example.com>")
        head_log = self.repo.git_dir / "logs" / "HEAD"
        branch_log = self.repo.git_dir / "logs" / "refs" / "heads" / "main"
        self.assertTrue(head_log.exists(), "logs/HEAD should exist")
        self.assertTrue(branch_log.exists(), "logs/refs/heads/main should exist")
        head_lines = head_log.read_text().strip().splitlines()
        branch_lines = branch_log.read_text().strip().splitlines()
        self.assertEqual(len(head_lines), 1)
        self.assertEqual(len(branch_lines), 1)
        self.assertIn("commit: first", head_lines[0])
        self.assertIn("commit: first", branch_lines[0])
        self.assertRegex(head_lines[0], r"^[0-9a-f]{40} [0-9a-f]{40} ")
        self.assertRegex(branch_lines[0], r"^[0-9a-f]{40} [0-9a-f]{40} ")


class TestCheckoutWritesReflog(unittest.TestCase):
    """Checkout writes HEAD reflog."""

    def setUp(self) -> None:
        d = tempfile.mkdtemp(prefix="pygit_reflog_checkout_")
        self.repo_dir = Path(d)
        self.repo = Repository(str(self.repo_dir))
        self.repo.init()
        set_value(self.repo, "user.name", "Alice")
        set_value(self.repo, "user.email", "alice@example.com")
        (self.repo_dir / "f").write_text("x")
        add_path(self.repo, "f")
        commit(self.repo, "first", author="Alice <alice@example.com>")
        # create second branch
        checkout_branch(self.repo, "feature", create=True)

    def test_checkout_reflog_has_checkout_message(self) -> None:
        entries = read_reflog(self.repo, "HEAD")
        self.assertGreaterEqual(len(entries), 2)  # commit, then checkout -b feature
        messages = [e[5] for e in entries]
        self.assertTrue(
            any("moving from" in m and "feature" in m for m in messages),
            f"Expected checkout message in {messages}",
        )


class TestResetWritesReflog(unittest.TestCase):
    """Reset writes reflog."""

    def setUp(self) -> None:
        d = tempfile.mkdtemp(prefix="pygit_reflog_reset_")
        self.repo_dir = Path(d)
        self.repo = Repository(str(self.repo_dir))
        self.repo.init()
        set_value(self.repo, "user.name", "Alice")
        set_value(self.repo, "user.email", "alice@example.com")
        (self.repo_dir / "f").write_text("1")
        add_path(self.repo, "f")
        commit(self.repo, "first", author="Alice <alice@example.com>")
        (self.repo_dir / "f").write_text("2")
        add_path(self.repo, "f")
        commit(self.repo, "second", author="Alice <alice@example.com>")

    def test_reset_appends_reflog(self) -> None:
        entries_before = read_reflog(self.repo, "HEAD")
        self.assertGreaterEqual(len(entries_before), 2)
        first_hash = entries_before[-1][0]  # old hash of second commit = first commit
        reset_hard(self.repo, first_hash)
        entries = read_reflog(self.repo, "HEAD")
        self.assertGreater(len(entries), len(entries_before))
        messages = [e[5] for e in entries]
        self.assertTrue(
            any("reset: moving to" in m for m in messages),
            f"Expected reset message in {messages}",
        )


class TestMergeWritesReflog(unittest.TestCase):
    """Merge writes reflog."""

    def setUp(self) -> None:
        d = tempfile.mkdtemp(prefix="pygit_reflog_merge_")
        self.repo_dir = Path(d)
        self.repo = Repository(str(self.repo_dir))
        self.repo.init()
        set_value(self.repo, "user.name", "Alice")
        set_value(self.repo, "user.email", "alice@example.com")
        (self.repo_dir / "a").write_text("1")
        add_path(self.repo, "a")
        commit(self.repo, "first", author="Alice <alice@example.com>")
        checkout_branch(self.repo, "feature", create=True)
        (self.repo_dir / "b").write_text("2")
        add_path(self.repo, "b")
        commit(self.repo, "on feature", author="Alice <alice@example.com>")
        checkout_branch(self.repo, "main", create=False)
        (self.repo_dir / "b").unlink(missing_ok=True)  # remove leftover from feature for clean merge

    def test_merge_reflog_contains_merge_message(self) -> None:
        merge(self.repo, "feature")
        entries = read_reflog(self.repo, "HEAD")
        messages = [e[5] for e in entries]
        self.assertTrue(
            any("merge" in m for m in messages),
            f"Expected merge message in {messages}",
        )


class TestReflogCommandOutput(unittest.TestCase):
    """reflog command prints entries in reverse order with @{idx}."""

    def setUp(self) -> None:
        d = tempfile.mkdtemp(prefix="pygit_reflog_cmd_")
        self.repo_dir = Path(d)
        self.repo = Repository(str(self.repo_dir))
        self.repo.init()
        set_value(self.repo, "user.name", "Alice")
        set_value(self.repo, "user.email", "alice@example.com")
        (self.repo_dir / "f").write_text("1")
        add_path(self.repo, "f")
        commit(self.repo, "first", author="Alice <alice@example.com>")
        (self.repo_dir / "f").write_text("2")
        add_path(self.repo, "f")
        commit(self.repo, "second", author="Alice <alice@example.com>")

    def test_reflog_prints_reverse_order_and_at_idx(self) -> None:
        out = io.StringIO()
        old = sys.stdout
        sys.stdout = out
        try:
            reflog_show(self.repo, ref="HEAD", max_count=5)
        finally:
            sys.stdout = old
        lines = out.getvalue().strip().splitlines()
        self.assertGreaterEqual(len(lines), 2)
        self.assertIn("@{0}", lines[0], "Most recent should be @{0}")
        self.assertIn("commit:", lines[0])
        self.assertRegex(lines[0], r"^[0-9a-f]{7} HEAD@\{0\}: ")
