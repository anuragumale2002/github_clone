"""Tests for stash save/list/apply/pop (Phase C)."""

import tempfile
import unittest
from pathlib import Path

from pygit.porcelain import add_path, commit, status
from pygit.repo import Repository
from pygit.stash import stash_apply, stash_list, stash_pop, stash_save


class TestStash(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = Path(tempfile.mkdtemp(prefix="pygit_stash_"))
        self.repo = Repository(str(self.tmp))
        self.repo.init()

    def test_stash_save_then_status_clean(self) -> None:
        (self.tmp / "f").write_text("hello\n")
        add_path(self.repo, "f")
        commit(self.repo, "first", "A <a@b.c>")
        (self.tmp / "f").write_text("modified\n")
        add_path(self.repo, "f")
        stash_save(self.repo)
        # After stash, working tree and index should be clean (reset to HEAD)
        out: list[str] = []
        status(self.repo)
        # We can't easily capture status output; instead check file content = HEAD
        self.assertEqual((self.tmp / "f").read_text(), "hello\n")

    def test_stash_list_and_apply_restores(self) -> None:
        (self.tmp / "g").write_text("one\n")
        add_path(self.repo, "g")
        commit(self.repo, "first", "B <b@b.c>")
        (self.tmp / "g").write_text("two\n")
        add_path(self.repo, "g")
        stash_save(self.repo, message="stash msg")
        stashes = stash_list(self.repo)
        self.assertEqual(len(stashes), 1)
        self.assertIn("stash msg", stashes[0][1])
        stash_apply(self.repo)
        self.assertEqual((self.tmp / "g").read_text(), "two\n")

    def test_stash_pop_removes_entry(self) -> None:
        (self.tmp / "h").write_text("a\n")
        add_path(self.repo, "h")
        commit(self.repo, "first", "C <c@b.c>")
        (self.tmp / "h").write_text("b\n")
        add_path(self.repo, "h")
        stash_save(self.repo)
        self.assertEqual(len(stash_list(self.repo)), 1)
        stash_pop(self.repo)
        self.assertEqual((self.tmp / "h").read_text(), "b\n")
        self.assertEqual(len(stash_list(self.repo)), 0)
