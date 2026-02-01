"""Tests for cherry-pick: clean apply, conflict, continue, abort."""

import tempfile
import unittest
from pathlib import Path

from pygit.config import set_value
from pygit.errors import PygitError
from pygit.plumbing import rev_parse
from pygit.porcelain import (
    add_path,
    cherry_pick,
    cherry_pick_abort,
    cherry_pick_continue,
    checkout_branch,
    commit,
)
from pygit.reflog import read_reflog
from pygit.repo import Repository


class TestCherryPickClean(unittest.TestCase):
    """Clean cherry-pick applies commit onto HEAD."""

    def setUp(self) -> None:
        d = tempfile.mkdtemp(prefix="pygit_cherry_clean_")
        self.repo_dir = Path(d)
        self.repo = Repository(str(self.repo_dir))
        self.repo.init()
        set_value(self.repo, "user.name", "Alice")
        set_value(self.repo, "user.email", "alice@example.com")

    def test_clean_cherry_pick_applies_commit(self) -> None:
        (self.repo_dir / "file.txt").write_text("base\n")
        add_path(self.repo, "file.txt")
        commit(self.repo, "commit A", author="Alice <alice@example.com>")
        hash_a = rev_parse(self.repo, "HEAD")

        checkout_branch(self.repo, "feature", create=True)
        (self.repo_dir / "file.txt").write_text("feature\n")
        add_path(self.repo, "file.txt")
        commit(self.repo, "commit B", author="Alice <alice@example.com>")
        hash_b = rev_parse(self.repo, "HEAD")

        checkout_branch(self.repo, "main", create=False)
        cherry_pick(self.repo, hash_b)

        head_after = rev_parse(self.repo, "HEAD")
        self.assertNotEqual(head_after, hash_a)

        obj = self.repo.load_object(head_after)
        from pygit.objects import Commit
        c = Commit.from_content(obj.content)
        self.assertEqual(len(c.parent_hashes), 1)
        self.assertEqual(c.parent_hashes[0], hash_a)
        self.assertIn("commit B", c.message)

        self.assertEqual((self.repo_dir / "file.txt").read_text(), "feature\n")

        reflog = read_reflog(self.repo, "HEAD")
        messages = [e[5] for e in reflog]
        self.assertTrue(any("cherry-pick" in m for m in messages))


class TestCherryPickConflict(unittest.TestCase):
    """Conflict cherry-pick stops and writes markers."""

    def setUp(self) -> None:
        d = tempfile.mkdtemp(prefix="pygit_cherry_conflict_")
        self.repo_dir = Path(d)
        self.repo = Repository(str(self.repo_dir))
        self.repo.init()
        set_value(self.repo, "user.name", "Alice")
        set_value(self.repo, "user.email", "alice@example.com")

    def test_conflict_stops_and_writes_markers(self) -> None:
        (self.repo_dir / "conflict.txt").write_text("base\n")
        add_path(self.repo, "conflict.txt")
        commit(self.repo, "A", author="Alice <alice@example.com>")

        checkout_branch(self.repo, "feature", create=True)
        (self.repo_dir / "conflict.txt").write_text("theirs\n")
        add_path(self.repo, "conflict.txt")
        commit(self.repo, "B", author="Alice <alice@example.com>")
        hash_b = rev_parse(self.repo, "HEAD")

        checkout_branch(self.repo, "main", create=False)
        (self.repo_dir / "conflict.txt").write_text("ours\n")
        add_path(self.repo, "conflict.txt")
        commit(self.repo, "M", author="Alice <alice@example.com>")
        hash_m = rev_parse(self.repo, "HEAD")

        with self.assertRaises(PygitError):
            cherry_pick(self.repo, hash_b)

        self.assertEqual(rev_parse(self.repo, "HEAD"), hash_m)

        content = (self.repo_dir / "conflict.txt").read_text()
        self.assertIn("<<<<<<<", content)
        self.assertIn("=======", content)
        self.assertIn(">>>>>>>", content)
        self.assertIn("ours", content)
        self.assertIn("theirs", content)

        pygit_dir = self.repo.git_dir / "pygit"
        self.assertTrue((pygit_dir / "CHERRY_PICK_HEAD").exists())
        self.assertTrue((pygit_dir / "CHERRY_PICK_ORIG_HEAD").exists())
        self.assertTrue((pygit_dir / "CHERRY_PICK_MSG").exists())


class TestCherryPickContinue(unittest.TestCase):
    """Continue after conflict resolution."""

    def setUp(self) -> None:
        d = tempfile.mkdtemp(prefix="pygit_cherry_continue_")
        self.repo_dir = Path(d)
        self.repo = Repository(str(self.repo_dir))
        self.repo.init()
        set_value(self.repo, "user.name", "Alice")
        set_value(self.repo, "user.email", "alice@example.com")

    def test_continue_after_resolution(self) -> None:
        (self.repo_dir / "conflict.txt").write_text("base\n")
        add_path(self.repo, "conflict.txt")
        commit(self.repo, "A", author="Alice <alice@example.com>")

        checkout_branch(self.repo, "feature", create=True)
        (self.repo_dir / "conflict.txt").write_text("theirs\n")
        add_path(self.repo, "conflict.txt")
        commit(self.repo, "B", author="Alice <alice@example.com>")
        hash_b = rev_parse(self.repo, "HEAD")

        checkout_branch(self.repo, "main", create=False)
        (self.repo_dir / "conflict.txt").write_text("ours\n")
        add_path(self.repo, "conflict.txt")
        commit(self.repo, "M", author="Alice <alice@example.com>")
        hash_m = rev_parse(self.repo, "HEAD")

        with self.assertRaises(PygitError):
            cherry_pick(self.repo, hash_b)

        (self.repo_dir / "conflict.txt").write_text("resolved\n")
        add_path(self.repo, "conflict.txt")
        cherry_pick_continue(self.repo)

        head_after = rev_parse(self.repo, "HEAD")
        self.assertNotEqual(head_after, hash_m)
        self.assertEqual((self.repo_dir / "conflict.txt").read_text(), "resolved\n")

        pygit_dir = self.repo.git_dir / "pygit"
        self.assertFalse((pygit_dir / "CHERRY_PICK_HEAD").exists())

        reflog = read_reflog(self.repo, "HEAD")
        messages = [e[5] for e in reflog]
        self.assertTrue(any("cherry-pick" in m for m in messages))


class TestCherryPickAbort(unittest.TestCase):
    """Abort restores original state."""

    def setUp(self) -> None:
        d = tempfile.mkdtemp(prefix="pygit_cherry_abort_")
        self.repo_dir = Path(d)
        self.repo = Repository(str(self.repo_dir))
        self.repo.init()
        set_value(self.repo, "user.name", "Alice")
        set_value(self.repo, "user.email", "alice@example.com")

    def test_abort_restores_state(self) -> None:
        (self.repo_dir / "conflict.txt").write_text("base\n")
        add_path(self.repo, "conflict.txt")
        commit(self.repo, "A", author="Alice <alice@example.com>")

        checkout_branch(self.repo, "feature", create=True)
        (self.repo_dir / "conflict.txt").write_text("theirs\n")
        add_path(self.repo, "conflict.txt")
        commit(self.repo, "B", author="Alice <alice@example.com>")
        hash_b = rev_parse(self.repo, "HEAD")

        checkout_branch(self.repo, "main", create=False)
        (self.repo_dir / "conflict.txt").write_text("ours\n")
        add_path(self.repo, "conflict.txt")
        commit(self.repo, "M", author="Alice <alice@example.com>")
        hash_m = rev_parse(self.repo, "HEAD")

        with self.assertRaises(PygitError):
            cherry_pick(self.repo, hash_b)

        cherry_pick_abort(self.repo)

        self.assertEqual(rev_parse(self.repo, "HEAD"), hash_m)
        self.assertEqual((self.repo_dir / "conflict.txt").read_text(), "ours\n")

        pygit_dir = self.repo.git_dir / "pygit"
        self.assertFalse((pygit_dir / "CHERRY_PICK_HEAD").exists())

        reflog = read_reflog(self.repo, "HEAD")
        messages = [e[5] for e in reflog]
        self.assertTrue(any("cherry-pick: abort" in m for m in messages))
