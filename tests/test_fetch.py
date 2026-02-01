"""Tests for fetch (Phase 4, local transport)."""

import tempfile
import unittest
from pathlib import Path

from pygit.fetch import fetch
from pygit.plumbing import rev_parse
from pygit.porcelain import add_path, commit
from pygit.refs import resolve_ref
from pygit.remote import remote_add
from pygit.repo import Repository


class TestFetchLocal(unittest.TestCase):
    """Fetch from local path: two repos A and B, commit in B, fetch into A."""

    def setUp(self) -> None:
        self.tmp = Path(tempfile.mkdtemp(prefix="pygit_fetch_"))
        (self.tmp / "A").mkdir()
        (self.tmp / "B").mkdir()
        self.repo_a = Repository(str(self.tmp / "A"))
        self.repo_a.init()
        self.repo_b = Repository(str(self.tmp / "B"))
        self.repo_b.init()

    def test_fetch_updates_remote_tracking_refs(self) -> None:
        (self.tmp / "B" / "f").write_text("hello\n")
        add_path(self.repo_b, "f")
        commit(self.repo_b, "first", "B <b@b.c>")
        head_b = rev_parse(self.repo_b, "HEAD")

        remote_add(self.repo_a, "origin", str(self.tmp / "B"))
        fetch(self.repo_a, "origin")

        remote_ref = resolve_ref(self.repo_a.git_dir, "refs/remotes/origin/main")
        self.assertIsNotNone(remote_ref)
        self.assertEqual(remote_ref, head_b)

    def test_fetch_copies_objects(self) -> None:
        (self.tmp / "B" / "f").write_text("hello\n")
        add_path(self.repo_b, "f")
        commit(self.repo_b, "first", "B <b@b.c>")
        head_b = rev_parse(self.repo_b, "HEAD")

        remote_add(self.repo_a, "origin", str(self.tmp / "B"))
        fetch(self.repo_a, "origin")

        self.assertTrue(self.repo_a.odb.exists(head_b))
        obj = self.repo_a.load_object(head_b)
        self.assertEqual(obj.type, "commit")
