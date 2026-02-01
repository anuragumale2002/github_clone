"""Tests for gc / repack / prune (Phase 2)."""

import tempfile
import unittest
from pathlib import Path

from pygit.gc import gc, reachable_objects, repack
from pygit.plumbing import cat_file_type, rev_parse
from pygit.porcelain import add_path, commit
from pygit.repo import Repository


class TestGcRepack(unittest.TestCase):
    """gc packs reachable objects; objects load from pack."""

    def setUp(self) -> None:
        self.tmp = Path(tempfile.mkdtemp(prefix="pygit_gc_"))
        self.repo = Repository(str(self.tmp))
        self.repo.init()

    def test_gc_creates_pack(self) -> None:
        (self.tmp / "f").write_text("hello\n")
        add_path(self.repo, "f")
        commit(self.repo, "first", "A <a@b.c>")
        (self.tmp / "f").write_text("world\n")
        add_path(self.repo, "f")
        commit(self.repo, "second", "A <a@b.c>")

        pack_dir = self.tmp / ".git" / "objects" / "pack"
        self.assertFalse(pack_dir.exists() or any(pack_dir.glob("*.pack")))

        pack_sha = gc(self.repo, prune_loose=False)
        self.assertIsNotNone(pack_sha)
        self.assertTrue(pack_dir.is_dir())
        packs = list(pack_dir.glob("*.pack"))
        self.assertGreaterEqual(len(packs), 1)
        self.assertTrue((pack_dir / f"pack-{pack_sha}.pack").exists())
        self.assertTrue((pack_dir / f"pack-{pack_sha}.idx").exists())

    def test_objects_load_after_gc(self) -> None:
        (self.tmp / "f").write_text("hello\n")
        add_path(self.repo, "f")
        commit(self.repo, "first", "A <a@b.c>")

        head_before = rev_parse(self.repo, "HEAD")
        gc(self.repo, prune_loose=False)

        self.assertEqual(rev_parse(self.repo, "HEAD"), head_before)
        self.assertEqual(cat_file_type(self.repo, head_before), "commit")
        self.assertEqual(cat_file_type(self.repo, rev_parse(self.repo, "HEAD")), "commit")

    def test_reachable_objects_includes_commits_trees_blobs(self) -> None:
        (self.tmp / "a").write_text("a\n")
        add_path(self.repo, "a")
        commit(self.repo, "first", "A <a@b.c>")

        reachable = reachable_objects(self.repo)
        self.assertGreater(len(reachable), 0)
        head_sha = rev_parse(self.repo, "HEAD")
        self.assertIn(head_sha, reachable)

    def test_repack_deterministic(self) -> None:
        (self.tmp / "f").write_text("x\n")
        add_path(self.repo, "f")
        commit(self.repo, "first", "A <a@b.c>")

        object_ids = sorted(reachable_objects(self.repo))
        pack_sha = repack(self.repo, object_ids, prune_loose=False)
        self.assertIsNotNone(pack_sha)
        pack_dir = self.tmp / ".git" / "objects" / "pack"
        self.assertTrue((pack_dir / f"pack-{pack_sha}.pack").is_file())
        self.assertTrue((pack_dir / f"pack-{pack_sha}.idx").is_file())
        self.assertEqual(cat_file_type(self.repo, rev_parse(self.repo, "HEAD")), "commit")
