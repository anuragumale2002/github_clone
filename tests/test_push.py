"""Tests for push (Phase 5, local transport)."""

import tempfile
import unittest
from pathlib import Path

from pygit.plumbing import rev_parse
from pygit.porcelain import add_path, commit, log
from pygit.push import push
from pygit.remote import remote_add
from pygit.repo import Repository


class TestPushLocal(unittest.TestCase):
    """Push from A to B; verify B branch updated."""

    def setUp(self) -> None:
        self.tmp = Path(tempfile.mkdtemp(prefix="pygit_push_"))
        (self.tmp / "A").mkdir()
        (self.tmp / "B").mkdir()
        self.repo_a = Repository(str(self.tmp / "A"))
        self.repo_a.init()
        self.repo_b = Repository(str(self.tmp / "B"))
        self.repo_b.init()

    def test_push_updates_remote_ref(self) -> None:
        (self.tmp / "A" / "f").write_text("hello\n")
        add_path(self.repo_a, "f")
        commit(self.repo_a, "first", "A <a@b.c>")
        head_a = rev_parse(self.repo_a, "HEAD")

        remote_add(self.repo_a, "origin", str(self.tmp / "B"))
        push(self.repo_a, "origin", "HEAD", "refs/heads/main")

        head_b = rev_parse(self.repo_b, "HEAD")
        self.assertEqual(head_b, head_a)

    def test_push_non_ff_refused_without_force(self) -> None:
        (self.tmp / "A" / "f").write_text("a\n")
        add_path(self.repo_a, "f")
        commit(self.repo_a, "first", "A <a@b.c>")
        remote_add(self.repo_a, "origin", str(self.tmp / "B"))
        push(self.repo_a, "origin", "HEAD", "refs/heads/main")

        (self.tmp / "B" / "g").write_text("b\n")
        add_path(self.repo_b, "g")
        commit(self.repo_b, "second", "B <b@b.c>")

        (self.tmp / "A" / "f").write_text("a2\n")
        add_path(self.repo_a, "f")
        commit(self.repo_a, "second", "A <a@b.c>")

        from pygit.errors import PygitError

        with self.assertRaises(PygitError) as ctx:
            push(self.repo_a, "origin", "HEAD", "refs/heads/main", force=False)
        self.assertIn("non-fast-forward", str(ctx.exception))
