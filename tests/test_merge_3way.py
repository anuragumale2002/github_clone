"""Tests for 3-way merge: clean merge commit, text conflict, delete/modify, binary conflict."""

import io
import sys
import tempfile
import unittest
from pathlib import Path

from pygit.constants import REF_HEADS_PREFIX
from pygit.errors import PygitError
from pygit.graph import get_commit_parents
from pygit.refs import resolve_ref, update_ref
from pygit.repo import Repository
from pygit.porcelain import (
    add_path,
    branch_create,
    checkout_branch,
    commit,
    merge,
    status,
    log,
)


class TestMerge3WayClean(unittest.TestCase):
    """Clean 3-way merge produces merge commit with 2 parents."""

    def setUp(self) -> None:
        d = tempfile.mkdtemp(prefix="pygit_merge_3way_")
        self.repo_dir = Path(d)
        self.repo = Repository(str(self.repo_dir))
        self.repo.init()
        (self.repo_dir / "a.txt").write_text("base\n")
        add_path(self.repo, "a.txt")
        self.hash_a = commit(self.repo, "Commit A", author="PyGit <p@x.com>") or ""
        branch_create(self.repo, "feature")
        (self.repo_dir / "a.txt").write_text("main change\n")
        add_path(self.repo, "a.txt")
        self.hash_b = commit(self.repo, "Commit B", author="PyGit <p@x.com>") or ""
        checkout_branch(self.repo, "feature", create=False)
        (self.repo_dir / "b.txt").write_text("feature file\n")
        add_path(self.repo, "b.txt")
        self.hash_c = commit(self.repo, "Commit C", author="PyGit <p@x.com>") or ""
        checkout_branch(self.repo, "main", create=False)
        (self.repo_dir / "b.txt").unlink(missing_ok=True)

    def test_merge_creates_merge_commit_with_two_parents(self) -> None:
        merge(self.repo, "feature")
        main_ref = resolve_ref(self.repo.git_dir, REF_HEADS_PREFIX + "main")
        self.assertIsNotNone(main_ref)
        parents = get_commit_parents(self.repo, main_ref)
        self.assertEqual(len(parents), 2)
        self.assertEqual(parents[0], self.hash_b)
        self.assertEqual(parents[1], self.hash_c)

    def test_merge_main_ref_points_to_new_commit(self) -> None:
        merge(self.repo, "feature")
        main_ref = resolve_ref(self.repo.git_dir, REF_HEADS_PREFIX + "main")
        self.assertNotEqual(main_ref, self.hash_b)
        self.assertNotEqual(main_ref, self.hash_c)

    def test_merge_working_tree_has_both_files(self) -> None:
        merge(self.repo, "feature")
        self.assertEqual((self.repo_dir / "a.txt").read_text(), "main change\n")
        self.assertEqual((self.repo_dir / "b.txt").read_text(), "feature file\n")

    def test_merge_status_clean_after(self) -> None:
        merge(self.repo, "feature")
        out = io.StringIO()
        old_stdout = sys.stdout
        sys.stdout = out
        try:
            status(self.repo)
        finally:
            sys.stdout = old_stdout
        self.assertIn("nothing to commit, working tree clean", out.getvalue())

    def test_merge_log_shows_merge_message(self) -> None:
        merge(self.repo, "feature")
        out = io.StringIO()
        old_stdout = sys.stdout
        sys.stdout = out
        try:
            log(self.repo, rev="HEAD", max_count=1, oneline=True)
        finally:
            sys.stdout = old_stdout
        self.assertIn("Merge", out.getvalue())


class TestMerge3WayTextConflict(unittest.TestCase):
    """Text conflict creates markers and does not commit."""

    def setUp(self) -> None:
        d = tempfile.mkdtemp(prefix="pygit_merge_conflict_")
        self.repo_dir = Path(d)
        self.repo = Repository(str(self.repo_dir))
        self.repo.init()
        (self.repo_dir / "conflict.txt").write_text("base\n")
        add_path(self.repo, "conflict.txt")
        self.hash_a = commit(self.repo, "Commit A", author="PyGit <p@x.com>") or ""
        branch_create(self.repo, "feature")
        (self.repo_dir / "conflict.txt").write_text("ours\n")
        add_path(self.repo, "conflict.txt")
        self.hash_b = commit(self.repo, "Commit B", author="PyGit <p@x.com>") or ""
        checkout_branch(self.repo, "feature", create=False)
        (self.repo_dir / "conflict.txt").write_text("theirs\n")
        add_path(self.repo, "conflict.txt")
        self.hash_c = commit(self.repo, "Commit C", author="PyGit <p@x.com>") or ""
        checkout_branch(self.repo, "main", create=False)

    def test_merge_raises_on_conflict(self) -> None:
        with self.assertRaises(PygitError):
            merge(self.repo, "feature")

    def test_merge_no_commit_main_ref_unchanged(self) -> None:
        try:
            merge(self.repo, "feature")
        except PygitError:
            pass
        main_ref = resolve_ref(self.repo.git_dir, REF_HEADS_PREFIX + "main")
        self.assertEqual(main_ref, self.hash_b)

    def test_merge_file_has_conflict_markers(self) -> None:
        try:
            merge(self.repo, "feature")
        except PygitError:
            pass
        content = (self.repo_dir / "conflict.txt").read_text()
        self.assertIn("<<<<<<< HEAD", content)
        self.assertIn("=======", content)
        self.assertIn(">>>>>>> feature", content)
        self.assertIn("ours", content)
        self.assertIn("theirs", content)

    def test_merge_prints_conflict_message(self) -> None:
        out = io.StringIO()
        old_stdout = sys.stdout
        sys.stdout = out
        try:
            merge(self.repo, "feature")
        except PygitError:
            pass
        finally:
            sys.stdout = old_stdout
        self.assertIn("Automatic merge failed", out.getvalue())
        self.assertIn("conflict.txt", out.getvalue())


class TestMergeDeleteModifyConflict(unittest.TestCase):
    """Delete/modify conflict: base has file, ours deletes, theirs modifies -> conflict."""

    def setUp(self) -> None:
        d = tempfile.mkdtemp(prefix="pygit_merge_delmod_")
        self.repo_dir = Path(d)
        self.repo = Repository(str(self.repo_dir))
        self.repo.init()
        (self.repo_dir / "file.txt").write_text("base\n")
        add_path(self.repo, "file.txt")
        self.hash_a = commit(self.repo, "Commit A", author="PyGit <p@x.com>") or ""
        branch_create(self.repo, "feature")
        from pygit.porcelain import rm_paths
        from pygit.plumbing import commit_tree as plumbing_commit_tree
        rm_paths(self.repo, ["file.txt"], cached=False)
        empty_tree = self.repo.create_tree_from_index()
        self.hash_b = plumbing_commit_tree(
            self.repo, empty_tree, [self.hash_a], "Commit B delete"
        )
        update_ref(self.repo.git_dir, REF_HEADS_PREFIX + "main", self.hash_b)
        checkout_branch(self.repo, "feature", create=False)
        (self.repo_dir / "file.txt").write_text("theirs change\n")
        add_path(self.repo, "file.txt")
        self.hash_c = commit(self.repo, "Commit C modify", author="PyGit <p@x.com>") or ""
        checkout_branch(self.repo, "main", create=False)

    def test_merge_delete_modify_raises(self) -> None:
        with self.assertRaises(PygitError):
            merge(self.repo, "feature")


class TestMergeBinaryConflict(unittest.TestCase):
    """Binary conflict: file with NUL bytes, differing changes -> conflict, no commit."""

    def setUp(self) -> None:
        d = tempfile.mkdtemp(prefix="pygit_merge_bin_")
        self.repo_dir = Path(d)
        self.repo = Repository(str(self.repo_dir))
        self.repo.init()
        (self.repo_dir / "bin.txt").write_bytes(b"base\x00\n")
        add_path(self.repo, "bin.txt")
        self.hash_a = commit(self.repo, "Commit A", author="PyGit <p@x.com>") or ""
        branch_create(self.repo, "feature")
        (self.repo_dir / "bin.txt").write_bytes(b"ours\x00\n")
        add_path(self.repo, "bin.txt")
        self.hash_b = commit(self.repo, "Commit B", author="PyGit <p@x.com>") or ""
        checkout_branch(self.repo, "feature", create=False)
        (self.repo_dir / "bin.txt").write_bytes(b"theirs\x00\n")
        add_path(self.repo, "bin.txt")
        self.hash_c = commit(self.repo, "Commit C", author="PyGit <p@x.com>") or ""
        checkout_branch(self.repo, "main", create=False)

    def test_merge_binary_conflict_raises(self) -> None:
        with self.assertRaises(PygitError):
            merge(self.repo, "feature")

    def test_merge_binary_conflict_prints_binary_message(self) -> None:
        out = io.StringIO()
        old_stdout = sys.stdout
        sys.stdout = out
        try:
            merge(self.repo, "feature")
        except PygitError:
            pass
        finally:
            sys.stdout = old_stdout
        self.assertIn("Binary file conflict", out.getvalue())
