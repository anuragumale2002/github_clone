"""Tests for index: binary DIRC roundtrip, JSON migration, mtime/size caching, PYGIT_PARANOID, checksum (Phase B)."""

import hashlib
import json
import os
import struct
import tempfile
import unittest
from pathlib import Path

from pygit.errors import IndexChecksumError, IndexCorruptError
from pygit.index import (
    DIRC_SIGNATURE,
    INDEX_CHECKSUM_LEN,
    INDEX_VERSION_BINARY,
    index_entry_for_file,
    index_entries_unchanged,
    load_index,
    save_index,
)


def make_temp_repo() -> tuple[Path, Path]:
    """Return (repo_root, repo_git)."""
    d = tempfile.mkdtemp(prefix="pygit_index_")
    root = Path(d)
    git = root / ".git"
    git.mkdir()
    return root, git


class TestIndex(unittest.TestCase):
    def setUp(self) -> None:
        self.repo_root, self.repo_git = make_temp_repo()

    def test_binary_roundtrip(self) -> None:
        """Write binary -> read -> equals."""
        entries = {
            "a.txt": {"sha1": "a" * 40, "mode": "100644", "size": 5, "mtime_ns": 1700000000000000000},
        }
        save_index(self.repo_git, entries)
        raw = (self.repo_git / "index").read_bytes()
        self.assertEqual(raw[:4], DIRC_SIGNATURE)
        loaded = load_index(self.repo_git)
        self.assertEqual(loaded["a.txt"]["sha1"], "a" * 40)
        self.assertEqual(loaded["a.txt"]["mode"], "100644")
        self.assertEqual(loaded["a.txt"]["size"], 5)
        self.assertEqual(loaded["a.txt"]["mtime_ns"], 1700000000000000000)

    def test_migration_json_to_binary(self) -> None:
        """Create JSON index on disk -> load_index -> migrated to binary (file begins with DIRC)."""
        index_path = self.repo_git / "index"
        payload = {"version": 1, "entries": {"foo": {"sha1": "b" * 40, "mode": "100644", "size": 3, "mtime_ns": 0}}}
        index_path.write_text(json.dumps(payload))
        loaded = load_index(self.repo_git)
        self.assertIn("foo", loaded)
        self.assertEqual(loaded["foo"]["sha1"], "b" * 40)
        self.assertEqual(loaded["foo"]["mode"], "100644")
        raw = index_path.read_bytes()
        self.assertEqual(raw[:4], DIRC_SIGNATURE)

    def test_migration_legacy_then_binary(self) -> None:
        """Legacy {path: sha} then load -> migrated to binary."""
        index_path = self.repo_git / "index"
        index_path.write_text(json.dumps({"bar": "c" * 14 + "dd"}))
        loaded = load_index(self.repo_git)
        self.assertIn("bar", loaded)
        self.assertEqual(loaded["bar"]["sha1"], "c" * 14 + "dd")
        self.assertEqual(loaded["bar"].get("mode"), "100644")
        raw = index_path.read_bytes()
        self.assertEqual(raw[:4], DIRC_SIGNATURE)

    def test_index_entries_unchanged(self) -> None:
        """If mtime and size unchanged, unchanged returns True."""
        f = self.repo_root / "somefile"
        f.write_text("hi")
        try:
            st = f.stat()
            mtime_ns = getattr(st, "st_mtime_ns", int(st.st_mtime * 1_000_000_000))
            entry = {"sha1": "x", "size": st.st_size, "mtime_ns": mtime_ns}
            self.assertTrue(index_entries_unchanged(self.repo_root, "somefile", entry))
            entry["size"] = 999
            self.assertFalse(index_entries_unchanged(self.repo_root, "somefile", entry))
        finally:
            if f.exists():
                f.unlink()

    def test_index_entries_unchanged_paranoid(self) -> None:
        """PYGIT_PARANOID=1 -> always rehash (unchanged returns False)."""
        f = self.repo_root / "paranoid_file"
        f.write_text("x")
        try:
            st = f.stat()
            mtime_ns = getattr(st, "st_mtime_ns", int(st.st_mtime * 1_000_000_000))
            entry = {"sha1": "y", "size": st.st_size, "mtime_ns": mtime_ns}
            prev = os.environ.pop("PYGIT_PARANOID", None)
            try:
                os.environ["PYGIT_PARANOID"] = "1"
                self.assertFalse(index_entries_unchanged(self.repo_root, "paranoid_file", entry))
            finally:
                if prev is not None:
                    os.environ["PYGIT_PARANOID"] = prev
                else:
                    os.environ.pop("PYGIT_PARANOID", None)
        finally:
            if f.exists():
                f.unlink()

    def test_index_checksum_roundtrip(self) -> None:
        """After save_index, file ends with SHA-1 of preceding content; load_index succeeds."""
        entries = {
            "a.txt": {"sha1": "a" * 40, "mode": "100644", "size": 5, "mtime_ns": 0, "ctime_ns": 0},
        }
        save_index(self.repo_git, entries)
        raw = (self.repo_git / "index").read_bytes()
        self.assertGreaterEqual(len(raw), 32)
        body = raw[:-INDEX_CHECKSUM_LEN]
        stored = raw[-INDEX_CHECKSUM_LEN:]
        self.assertEqual(hashlib.sha1(body).digest(), stored)
        loaded = load_index(self.repo_git)
        self.assertEqual(loaded["a.txt"]["sha1"], "a" * 40)

    def test_index_checksum_mismatch_raises(self) -> None:
        """Corrupting one byte in index causes load_index to raise IndexChecksumError."""
        entries = {
            "f": {"sha1": "b" * 40, "mode": "100644", "size": 1, "mtime_ns": 0, "ctime_ns": 0},
        }
        save_index(self.repo_git, entries)
        index_path = self.repo_git / "index"
        raw = index_path.read_bytes()
        # Tamper one byte in the middle (not the checksum)
        tampered = bytearray(raw)
        tampered[20] = tampered[20] ^ 0xFF
        index_path.write_bytes(bytes(tampered))
        with self.assertRaises(IndexChecksumError):
            load_index(self.repo_git)

    def test_index_unsorted_entries_raises(self) -> None:
        """Index with entries not sorted by path raises IndexCorruptError on load."""
        # Write valid index with sorted entries a, b
        entries = {
            "a": {"sha1": "a" * 40, "mode": "100644", "size": 0, "mtime_ns": 0, "ctime_ns": 0},
            "b": {"sha1": "b" * 40, "mode": "100644", "size": 0, "mtime_ns": 0, "ctime_ns": 0},
        }
        save_index(self.repo_git, entries)
        raw = (self.repo_git / "index").read_bytes()
        body = raw[:-INDEX_CHECKSUM_LEN]
        header = body[:12]
        rest = body[12:]
        # Each entry is 8-byte aligned; find boundary by parsing first entry length
        # Entry: 62 fixed + path+null + pad. Min path "a" = 1+1 = 2, so 62+2=64, pad to 64.
        # So first entry (a) is 64 bytes, second (b) is 64 bytes.
        entry_a_blob = rest[:64]
        entry_b_blob = rest[64:128]
        # Swap so body has b then a (unsorted)
        unsorted_body = header + entry_b_blob + entry_a_blob
        path = self.repo_git / "index"
        path.write_bytes(unsorted_body + hashlib.sha1(unsorted_body).digest())
        with self.assertRaises(IndexCorruptError):
            load_index(self.repo_git)
