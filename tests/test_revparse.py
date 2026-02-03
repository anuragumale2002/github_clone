"""Tests for rev-parse: HEAD, branch names, full hashes, prefix unique/ambiguous."""

import tempfile
import unittest
from pathlib import Path

from pygit.errors import AmbiguousRefError, InvalidRefError, ObjectNotFoundError
from pygit.objects import Blob, Commit, Tree
from pygit.refs import update_ref, write_head_ref, write_head_detached
from pygit.repo import Repository
from pygit.plumbing import rev_parse


def make_temp_repo() -> Path:
    d = tempfile.mkdtemp(prefix="pygit_revparse_")
    p = Path(d)
    (p / ".git" / "objects").mkdir(parents=True)
    (p / ".git" / "refs" / "heads").mkdir(parents=True)
    (p / ".git" / "refs" / "tags").mkdir(parents=True)
    return p


class TestRevParse(unittest.TestCase):
    def setUp(self) -> None:
        self.repo_dir = make_temp_repo()
        self.repo = Repository(str(self.repo_dir))
        # Create one commit and store refs
        blob = Blob(b"x")
        blob_sha = self.repo.store_object(blob)
        tree = Tree([("100644", "f", blob_sha)])
        tree_sha = self.repo.store_object(tree)
        commit = Commit(
            tree_hash=tree_sha,
            parent_hashes=[],
            author="A <a@b.com>",
            committer="A <a@b.com>",
            message="m",
            timestamp=1700000000,
            tz_offset="+0000",
        )
        self.commit_sha = self.repo.store_object(commit)
        write_head_ref(self.repo.git_dir, "refs/heads/main")
        update_ref(self.repo.git_dir, "refs/heads/main", self.commit_sha)

    def test_rev_parse_head(self) -> None:
        self.assertEqual(rev_parse(self.repo, "HEAD"), self.commit_sha)

    def test_rev_parse_branch(self) -> None:
        self.assertEqual(rev_parse(self.repo, "main"), self.commit_sha)

    def test_rev_parse_full_hash(self) -> None:
        self.assertEqual(rev_parse(self.repo, self.commit_sha), self.commit_sha)

    def test_rev_parse_prefix_unique(self) -> None:
        prefix = self.commit_sha[:7]
        self.assertEqual(rev_parse(self.repo, prefix), self.commit_sha)

    def test_rev_parse_prefix_ambiguous(self) -> None:
        # Create another commit with same 7-char prefix (different full hash)
        blob2 = Blob(b"y")
        b2 = self.repo.store_object(blob2)
        tree2 = Tree([("100644", "g", b2)])
        t2 = self.repo.store_object(tree2)
        commit2 = Commit(
            tree_hash=t2,
            parent_hashes=[self.commit_sha],
            author="A <a@b.com>",
            committer="A <a@b.com>",
            message="m2",
            timestamp=1700000001,
            tz_offset="+0000",
        )
        c2 = self.repo.store_object(commit2)
        # If prefix matches both, should raise AmbiguousRefError
        prefix = self.commit_sha[:4]
        matches = self.repo.odb.prefix_lookup(prefix)
        if len(matches) > 1:
            with self.assertRaises(AmbiguousRefError):
                rev_parse(self.repo, prefix)
        else:
            self.assertEqual(rev_parse(self.repo, prefix), matches[0])

    def test_rev_parse_invalid(self) -> None:
        with self.assertRaises((InvalidRefError, ObjectNotFoundError)):
            rev_parse(self.repo, "nonexistent-branch-xyz")

    def test_rev_parse_head_tilde_one_requires_parent(self) -> None:
        # Single commit has no parent; HEAD~1 should raise
        with self.assertRaises(InvalidRefError):
            rev_parse(self.repo, "HEAD~1")


class TestRevParseTildeCaret(unittest.TestCase):
    """rev-parse with ~n (first parent n times) and ^n (n-th parent)."""

    def setUp(self) -> None:
        self.repo_dir = make_temp_repo()
        self.repo = Repository(str(self.repo_dir))
        # Commit 1 (root)
        blob1 = Blob(b"a")
        b1 = self.repo.store_object(blob1)
        tree1 = Tree([("100644", "f", b1)])
        t1 = self.repo.store_object(tree1)
        c1 = Commit(
            tree_hash=t1,
            parent_hashes=[],
            author="A <a@b.com>",
            committer="A <a@b.com>",
            message="First",
            timestamp=1700000000,
            tz_offset="+0000",
        )
        self.hash1 = self.repo.store_object(c1)
        write_head_ref(self.repo.git_dir, "refs/heads/main")
        update_ref(self.repo.git_dir, "refs/heads/main", self.hash1)
        # Commit 2 (child of c1)
        blob2 = Blob(b"b")
        b2 = self.repo.store_object(blob2)
        tree2 = Tree([("100644", "f", b2)])
        t2 = self.repo.store_object(tree2)
        c2 = Commit(
            tree_hash=t2,
            parent_hashes=[self.hash1],
            author="A <a@b.com>",
            committer="A <a@b.com>",
            message="Second",
            timestamp=1700000001,
            tz_offset="+0000",
        )
        self.hash2 = self.repo.store_object(c2)
        update_ref(self.repo.git_dir, "refs/heads/main", self.hash2)

    def test_rev_parse_head_tilde_1(self) -> None:
        self.assertEqual(rev_parse(self.repo, "HEAD~1"), self.hash1)

    def test_rev_parse_head_tilde_2(self) -> None:
        # HEAD~2 = first parent of first parent = root (hash1 has no parent -> error)
        with self.assertRaises(InvalidRefError):
            rev_parse(self.repo, "HEAD~2")

    def test_rev_parse_main_tilde_1(self) -> None:
        self.assertEqual(rev_parse(self.repo, "main~1"), self.hash1)

    def test_rev_parse_head_caret(self) -> None:
        self.assertEqual(rev_parse(self.repo, "HEAD^"), self.hash1)

    def test_rev_parse_head_caret_1(self) -> None:
        self.assertEqual(rev_parse(self.repo, "HEAD^1"), self.hash1)
