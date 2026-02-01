"""Tests for show and restore."""

import tempfile
import unittest
from pathlib import Path

from pygit.objects import Blob, Commit, Tree
from pygit.porcelain import show_commit, restore
from pygit.repo import Repository


def make_temp_repo_with_commit() -> tuple[Path, Repository, str]:
    d = tempfile.mkdtemp(prefix="pygit_show_")
    p = Path(d)
    (p / ".git" / "objects").mkdir(parents=True)
    (p / ".git" / "refs" / "heads").mkdir(parents=True)
    (p / ".git" / "refs" / "tags").mkdir(parents=True)
    repo = Repository(str(p))
    blob = Blob(b"hello\n")
    bsha = repo.store_object(blob)
    tree = Tree([("100644", "f", bsha)])
    tsha = repo.store_object(tree)
    commit = Commit(
        tree_hash=tsha,
        parent_hashes=[],
        author="A <a@b.com>",
        committer="A <a@b.com>",
        message="First",
        timestamp=1700000000,
        tz_offset="+0000",
    )
    csha = repo.store_object(commit)
    (p / ".git" / "HEAD").write_text("ref: refs/heads/main\n")
    (p / ".git" / "refs" / "heads" / "main").write_text(csha + "\n")
    repo.save_index({"f": {"sha1": bsha, "mode": "100644", "size": 6, "mtime_ns": 0, "ctime_ns": 0}})
    (p / "f").write_text("hello\n")
    return p, repo, csha


class TestShow(unittest.TestCase):
    def setUp(self) -> None:
        self.repo_dir, self.repo, self.commit_sha = make_temp_repo_with_commit()

    def test_show_produces_diff_output(self) -> None:
        import io
        from contextlib import redirect_stdout
        out = io.StringIO()
        with redirect_stdout(out):
            show_commit(self.repo, "HEAD")
        text = out.getvalue()
        self.assertIn("commit", text)
        self.assertIn("Author:", text)
        self.assertIn("First", text)
        self.assertIn("diff", text.lower())


class TestRestore(unittest.TestCase):
    def setUp(self) -> None:
        self.repo_dir, self.repo, self.commit_sha = make_temp_repo_with_commit()

    def test_restore_staged_reverts_index(self) -> None:
        (self.repo_dir / "f").write_text("modified\n")
        blob2 = Blob(b"modified\n")
        b2 = self.repo.store_object(blob2)
        self.repo.save_index({"f": {"sha1": b2, "mode": "100644", "size": 9, "mtime_ns": 0, "ctime_ns": 0}})
        restore(self.repo, ["f"], staged=True)
        idx = self.repo.load_index()
        self.assertIn("f", idx)
        head_tree = self.repo.build_index_from_tree(
            Commit.from_content(self.repo.load_object(self.commit_sha).content).tree_hash
        )
        self.assertEqual(idx["f"]["sha1"], head_tree["f"])

    def test_restore_updates_working_file(self) -> None:
        (self.repo_dir / "f").write_text("changed\n")
        restore(self.repo, ["f"], staged=False)
        self.assertEqual((self.repo_dir / "f").read_text(), "hello\n")
