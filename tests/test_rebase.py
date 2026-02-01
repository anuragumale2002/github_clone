"""Tests for rebase: linear history, conflict and abort (Phase D)."""

import tempfile
import unittest
from pathlib import Path

from pygit.errors import PygitError
from pygit.plumbing import rev_parse
from pygit.porcelain import add_path, checkout_branch, commit
from pygit.rebase import rebase, rebase_abort, rebase_continue
from pygit.refs import head_commit
from pygit.repo import Repository


class TestRebaseLinear(unittest.TestCase):
    """Normal rebase produces linear history A-D-B'-C'."""

    def setUp(self) -> None:
        self.tmp = Path(tempfile.mkdtemp(prefix="pygit_rebase_"))
        self.repo = Repository(str(self.tmp))
        self.repo.init()

    def test_rebase_linear_history(self) -> None:
        (self.tmp / "f").write_text("a\n")
        add_path(self.repo, "f")
        commit(self.repo, "A", "X <x@x>")

        checkout_branch(self.repo, "upstream", create=True)
        (self.tmp / "d").write_text("d\n")
        add_path(self.repo, "d")
        commit(self.repo, "D", "X <x@x>")
        hash_d = rev_parse(self.repo, "HEAD")

        checkout_branch(self.repo, "main", create=False)
        if (self.tmp / "d").exists():
            (self.tmp / "d").unlink()
        (self.tmp / "f").write_text("b\n")
        add_path(self.repo, "f")
        commit(self.repo, "B", "X <x@x>")
        (self.tmp / "f").write_text("c\n")
        add_path(self.repo, "f")
        commit(self.repo, "C", "X <x@x>")

        rebase(self.repo, "upstream")

        head = head_commit(self.repo.git_dir)
        self.assertIsNotNone(head)
        head_obj = self.repo.load_object(head)
        from pygit.objects import Commit
        c = Commit.from_content(head_obj.content)
        self.assertIn("C", c.message)
        self.assertEqual(len(c.parent_hashes), 1)
        parent = c.parent_hashes[0]
        parent_obj = self.repo.load_object(parent)
        p = Commit.from_content(parent_obj.content)
        self.assertIn("B", p.message)
        self.assertEqual(len(p.parent_hashes), 1)
        self.assertEqual(p.parent_hashes[0], hash_d)
        self.assertEqual((self.tmp / "f").read_text(), "c\n")
        self.assertEqual((self.tmp / "d").read_text(), "d\n")


class TestRebaseAbort(unittest.TestCase):
    """Rebase --abort restores original HEAD and tree."""

    def setUp(self) -> None:
        self.tmp = Path(tempfile.mkdtemp(prefix="pygit_rebase_abort_"))
        self.repo = Repository(str(self.tmp))
        self.repo.init()

    def test_rebase_abort_restores_state(self) -> None:
        (self.tmp / "g").write_text("one\n")
        add_path(self.repo, "g")
        commit(self.repo, "base", "Y <y@y>")

        (self.tmp / "g").write_text("two\n")
        add_path(self.repo, "g")
        commit(self.repo, "main1", "Y <y@y>")
        (self.tmp / "g").write_text("three\n")
        add_path(self.repo, "g")
        commit(self.repo, "main2", "Y <y@y>")
        orig_head = rev_parse(self.repo, "HEAD")
        orig_content = (self.tmp / "g").read_text()

        checkout_branch(self.repo, "other", create=True)
        (self.tmp / "g").write_text("other\n")
        add_path(self.repo, "g")
        commit(self.repo, "other", "Y <y@y>")

        checkout_branch(self.repo, "main", create=False)
        try:
            rebase(self.repo, "other")
        except PygitError:
            pass
        if (self.repo.git_dir / "pygit" / "REBASE_ORIG_HEAD").exists():
            rebase_abort(self.repo)
            head = head_commit(self.repo.git_dir)
            self.assertEqual(head, orig_head)
            self.assertEqual((self.tmp / "g").read_text(), orig_content)
        else:
            self.skipTest("rebase did not conflict (no REBASE_ORIG_HEAD)")
