"""Tests for remote add/list/remove and refspec (Phase 3)."""

import tempfile
import unittest
from pathlib import Path

from pygit.remote import (
    get_remote_fetch_refspecs,
    get_remote_url,
    parse_refspec,
    refspec_expand,
    refspec_expand_src_list,
    remote_add,
    remote_list,
    remote_remove,
)
from pygit.repo import Repository


class TestRemoteConfig(unittest.TestCase):
    """remote add / list / remove."""

    def setUp(self) -> None:
        self.tmp = Path(tempfile.mkdtemp(prefix="pygit_remote_"))
        self.repo = Repository(str(self.tmp))
        self.repo.init()

    def test_remote_add_and_list(self) -> None:
        remote_add(self.repo, "origin", "/path/to/repo")
        remotes = remote_list(self.repo)
        self.assertEqual(len(remotes), 1)
        self.assertEqual(remotes[0][0], "origin")
        self.assertEqual(remotes[0][1], "/path/to/repo")

    def test_remote_add_creates_refs_remotes_dir(self) -> None:
        remote_add(self.repo, "origin", "file:///tmp/other")
        remotes_dir = self.tmp / ".git" / "refs" / "remotes" / "origin"
        self.assertTrue(remotes_dir.is_dir())

    def test_remote_remove(self) -> None:
        remote_add(self.repo, "origin", "/path/to/repo")
        remote_remove(self.repo, "origin")
        remotes = remote_list(self.repo)
        self.assertEqual(len(remotes), 0)

    def test_remote_list_verbose(self) -> None:
        remote_add(self.repo, "origin", "https://example.com/repo.git")
        remotes = remote_list(self.repo)
        self.assertEqual(remotes[0], ("origin", "https://example.com/repo.git", "https://example.com/repo.git"))

    def test_get_remote_url(self) -> None:
        remote_add(self.repo, "origin", "/path/to/repo")
        self.assertEqual(get_remote_url(self.repo, "origin"), "/path/to/repo")
        self.assertIsNone(get_remote_url(self.repo, "nonexistent"))

    def test_default_fetch_refspec(self) -> None:
        remote_add(self.repo, "origin", "/path/to/repo")
        refspecs = get_remote_fetch_refspecs(self.repo, "origin")
        self.assertEqual(len(refspecs), 1)
        self.assertIn("refs/heads/*", refspecs[0])
        self.assertIn("refs/remotes/origin/*", refspecs[0])


class TestRefspec(unittest.TestCase):
    """Refspec parsing and expansion."""

    def test_parse_simple(self) -> None:
        r = parse_refspec("refs/heads/main:refs/remotes/origin/main")
        self.assertFalse(r.force)
        self.assertEqual(r.src, "refs/heads/main")
        self.assertEqual(r.dst, "refs/remotes/origin/main")
        self.assertFalse(r.wildcard)

    def test_parse_force(self) -> None:
        r = parse_refspec("+refs/heads/main:refs/remotes/origin/main")
        self.assertTrue(r.force)
        self.assertEqual(r.src, "refs/heads/main")

    def test_parse_wildcard(self) -> None:
        r = parse_refspec("+refs/heads/*:refs/remotes/origin/*")
        self.assertTrue(r.wildcard)
        self.assertEqual(r.src, "refs/heads/*")
        self.assertEqual(r.dst, "refs/remotes/origin/*")

    def test_refspec_expand_wildcard(self) -> None:
        r = parse_refspec("refs/heads/*:refs/remotes/origin/*")
        self.assertEqual(refspec_expand(r, "refs/heads/main"), "refs/remotes/origin/main")
        self.assertEqual(refspec_expand(r, "refs/heads/feature/x"), "refs/remotes/origin/feature/x")
        self.assertIsNone(refspec_expand(r, "refs/tags/v1"))

    def test_refspec_expand_src_list(self) -> None:
        r = parse_refspec("refs/heads/*:refs/remotes/origin/*")
        src_list = ["refs/heads/main", "refs/heads/feature", "refs/tags/v1"]
        result = refspec_expand_src_list(r, src_list)
        self.assertEqual(len(result), 2)
        self.assertEqual(result[0], ("refs/heads/main", "refs/remotes/origin/main"))
        self.assertEqual(result[1], ("refs/heads/feature", "refs/remotes/origin/feature"))
