"""Tests for objects: blob/tree/commit serialize/deserialize and hash correctness."""

import unittest
import zlib

from pygit.objects import Blob, Commit, GitObject, Tree
from pygit.util import sha1_hash


class TestBlob(unittest.TestCase):
    def test_blob_roundtrip(self) -> None:
        content = b"hello world"
        blob = Blob(content)
        h = blob.hash_id()
        self.assertEqual(len(h), 40)
        self.assertTrue(all(c in "0123456789abcdef" for c in h))
        raw = blob.serialize()
        decompressed = zlib.decompress(raw)
        self.assertTrue(b"\0" in decompressed)
        header, body = decompressed.split(b"\0", 1)
        self.assertEqual(body, content)
        self.assertEqual(header.decode(), f"blob {len(content)}")
        # deserialize roundtrip
        blob2 = GitObject.deserialize(blob.serialize())
        self.assertIsInstance(blob2, Blob)
        self.assertEqual(blob2.content, content)
        self.assertEqual(blob2.hash_id(), h)

    def test_blob_hash_format(self) -> None:
        blob = Blob(b"x")
        header = b"blob 1\0"
        expected = sha1_hash(header + b"x")
        self.assertEqual(blob.hash_id(), expected)


class TestTree(unittest.TestCase):
    def test_tree_roundtrip(self) -> None:
        entries = [("100644", "a.txt", "a" * 40), ("040000", "dir", "b" * 40)]
        tree = Tree(entries)
        h = tree.hash_id()
        self.assertEqual(len(h), 40)
        raw = tree.serialize()
        tree2 = GitObject.deserialize(raw)
        self.assertIsInstance(tree2, Tree)
        self.assertEqual(len(tree2.entries), 2)
        self.assertEqual(tree2.hash_id(), h)

    def test_tree_from_content(self) -> None:
        # one entry: 100644 name\0 + 20-byte sha
        name = "f"
        mode = "100644"
        sha_hex = "a" * 40
        content = f"{mode} {name}\0".encode() + bytes.fromhex(sha_hex)
        tree = Tree.from_content(content)
        self.assertEqual(len(tree.entries), 1)
        self.assertEqual(tree.entries[0], (mode, name, sha_hex))
        self.assertEqual(tree.content, content)
        self.assertEqual(tree.hash_id(), sha1_hash(b"tree " + str(len(content)).encode() + b"\0" + content))


class TestCommit(unittest.TestCase):
    def test_commit_roundtrip(self) -> None:
        tree_hash = "c" * 40
        parent = "d" * 40
        author = "A <a@x.com>"
        message = "msg"
        commit = Commit(
            tree_hash=tree_hash,
            parent_hashes=[parent],
            author=author,
            committer=author,
            message=message,
            timestamp=1700000000,
            tz_offset="+0000",
        )
        h = commit.hash_id()
        self.assertEqual(len(h), 40)
        raw = commit.serialize()
        commit2 = GitObject.deserialize(raw)
        self.assertIsInstance(commit2, Commit)
        self.assertEqual(commit2.tree_hash, tree_hash)
        self.assertEqual(commit2.parent_hashes, [parent])
        self.assertEqual(commit2.message, message)
        self.assertEqual(commit2.hash_id(), h)

    def test_commit_from_content_preserves_hash(self) -> None:
        content = (
            b"tree " + b"e" * 40 + b"\n"
            b"parent " + b"f" * 40 + b"\n"
            b"author Author <a@b.com> 1700000000 +0530\n"
            b"committer Author <a@b.com> 1700000000 +0530\n"
            b"\n"
            b"message body\n"
        )
        commit = Commit.from_content(content)
        self.assertEqual(commit.content, content)
        header = b"commit " + str(len(content)).encode() + b"\0"
        expected_hash = sha1_hash(header + content)
        self.assertEqual(commit.hash_id(), expected_hash)
