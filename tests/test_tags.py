"""Tests for tags: lightweight, annotated, delete, rev-parse peel, cat-file."""

import tempfile
import unittest
from pathlib import Path

from pygit.objects import Blob, Commit, Tag, Tree
from pygit.plumbing import cat_file_type, cat_file_pretty, rev_parse
from pygit.porcelain import tag_create_annotated, tag_create_lightweight, tag_delete, tag_list
from pygit.repo import Repository


def make_temp_repo_with_commit() -> tuple[Path, Repository, str]:
    d = tempfile.mkdtemp(prefix="pygit_tags_")
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
    return p, repo, csha


class TestLightweightTag(unittest.TestCase):
    def setUp(self) -> None:
        self.repo_dir, self.repo, self.commit_sha = make_temp_repo_with_commit()

    def test_lightweight_tag_creates_ref(self) -> None:
        tag_create_lightweight(self.repo, "v1", target="HEAD")
        ref_path = self.repo.git_dir / "refs" / "tags" / "v1"
        self.assertTrue(ref_path.exists())
        self.assertEqual(ref_path.read_text().strip(), self.commit_sha)

    def test_rev_parse_tag_equals_commit(self) -> None:
        tag_create_lightweight(self.repo, "v1", target="HEAD")
        self.assertEqual(rev_parse(self.repo, "v1"), self.commit_sha)

    def test_cat_file_t_lightweight_is_commit(self) -> None:
        tag_create_lightweight(self.repo, "v1", target="HEAD")
        self.assertEqual(cat_file_type(self.repo, "v1"), "commit")


class TestAnnotatedTag(unittest.TestCase):
    def setUp(self) -> None:
        self.repo_dir, self.repo, self.commit_sha = make_temp_repo_with_commit()

    def test_annotated_tag_ref_points_to_tag_object(self) -> None:
        tag_create_annotated(self.repo, "v2", target="HEAD", message="Release v2")
        ref_path = self.repo.git_dir / "refs" / "tags" / "v2"
        self.assertTrue(ref_path.exists())
        tag_hash = ref_path.read_text().strip()
        obj = self.repo.load_object(tag_hash)
        self.assertEqual(obj.type, "tag")

    def test_cat_file_t_annotated_is_tag(self) -> None:
        tag_create_annotated(self.repo, "v2", target="HEAD", message="Release v2")
        self.assertEqual(cat_file_type(self.repo, "v2"), "tag")

    def test_cat_file_p_annotated_contains_lines(self) -> None:
        tag_create_annotated(self.repo, "v2", target="HEAD", message="Release v2")
        import io
        from contextlib import redirect_stdout
        out = io.StringIO()
        with redirect_stdout(out):
            cat_file_pretty(self.repo, "v2")
        text = out.getvalue()
        self.assertIn("object ", text)
        self.assertIn("type commit", text)
        self.assertIn("tag v2", text)
        self.assertIn("Release v2", text)

    def test_rev_parse_peel_equals_commit(self) -> None:
        tag_create_annotated(self.repo, "v2", target="HEAD", message="Release v2")
        peeled = rev_parse(self.repo, "v2^{}")
        self.assertEqual(peeled, self.commit_sha)


class TestTagDelete(unittest.TestCase):
    def setUp(self) -> None:
        self.repo_dir, self.repo, self.commit_sha = make_temp_repo_with_commit()

    def test_delete_removes_ref(self) -> None:
        tag_create_lightweight(self.repo, "v1", target="HEAD")
        ref_path = self.repo.git_dir / "refs" / "tags" / "v1"
        self.assertTrue(ref_path.exists())
        tag_delete(self.repo, "v1")
        self.assertFalse(ref_path.exists())
