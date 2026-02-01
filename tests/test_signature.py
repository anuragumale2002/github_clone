"""Tests for PGP/signature preservation and verification stub (Phase F)."""

import unittest

from pygit.constants import OBJ_COMMIT, OBJ_TAG
from pygit.objects import Commit, Tag, verify_signature


class TestCommitGpgsig(unittest.TestCase):
    """Commit: preserve gpgsig header on parse/serialize."""

    def test_commit_with_gpgsig_preserves_content(self) -> None:
        raw = (
            b"tree abcdef0123456789abcdef0123456789abcdef\n"
            b"parent 0000000000000000000000000000000000000000\n"
            b"author A <a@b> 1700000000 +0000\n"
            b"committer A <a@b> 1700000000 +0000\n"
            b"gpgsig -----BEGIN PGP SIGNATURE-----\n"
            b" dummy\n"
            b" -----END PGP SIGNATURE-----\n"
            b"\n"
            b"msg\n"
        )
        commit = Commit.from_content(raw)
        self.assertEqual(commit.tree_hash, "abcdef0123456789abcdef0123456789abcdef")
        self.assertEqual(commit.message.strip(), "msg")
        self.assertIsNotNone(commit.gpgsig)
        self.assertIn("BEGIN PGP SIGNATURE", commit.gpgsig)
        self.assertEqual(commit.content, raw)

    def test_commit_roundtrip_with_gpgsig(self) -> None:
        c = Commit(
            "a" * 40,
            [],
            "A <a@b>",
            "A <a@b>",
            "hello",
            timestamp=1700000000,
            tz_offset="+0000",
            gpgsig="-----BEGIN PGP SIGNATURE-----\ndummy\n-----END PGP SIGNATURE-----",
        )
        # Serialized form: no trailing newline after message (join with \n)
        raw = b"tree " + ("a" * 40).encode() + b"\n"
        raw += b"author A <a@b> 1700000000 +0000\n"
        raw += b"committer A <a@b> 1700000000 +0000\n"
        raw += b"gpgsig -----BEGIN PGP SIGNATURE-----\n"
        raw += b" dummy\n"
        raw += b" -----END PGP SIGNATURE-----\n"
        raw += b"\n"
        raw += b"hello\n"
        self.assertEqual(c.content, raw)


class TestTagGpgSignature(unittest.TestCase):
    """Tag: preserve PGP block on parse/serialize."""

    def test_tag_with_pgp_block_preserves_content(self) -> None:
        raw = (
            b"object " + b"a" * 40 + b"\n"
            b"type commit\n"
            b"tag v1\n"
            b"tagger A <a@b> 1700000000 +0000\n"
            b"\n"
            b"msg\n"
            b"-----BEGIN PGP SIGNATURE-----\n"
            b"dummy\n"
            b"-----END PGP SIGNATURE-----\n"
        )
        tag = Tag.from_content(raw)
        self.assertEqual(tag.message, "msg")
        self.assertIsNotNone(tag.gpg_signature)
        self.assertIn(b"BEGIN PGP SIGNATURE", tag.gpg_signature)
        self.assertEqual(tag.content, raw)

    def test_tag_roundtrip_with_gpg_signature(self) -> None:
        sig = b"-----BEGIN PGP SIGNATURE-----\ndummy\n-----END PGP SIGNATURE-----\n"
        t = Tag(
            "a" * 40,
            "commit",
            "v1",
            "A <a@b>",
            "msg",
            timestamp=1700000000,
            tz_offset="+0000",
            gpg_signature=sig,
        )
        self.assertEqual(t.gpg_signature, sig)
        self.assertIn(b"BEGIN PGP SIGNATURE", t.content)


class TestVerifySignatureStub(unittest.TestCase):
    """verify_signature stub: unsigned -> (True, ''); signed -> (False, '...')."""

    def test_unsigned_commit_returns_valid(self) -> None:
        c = Commit("a" * 40, [], "A <a@b>", "A <a@b>", "msg", gpgsig=None)
        valid, msg = verify_signature(c)
        self.assertTrue(valid)
        self.assertEqual(msg, "")

    def test_signed_commit_returns_stub_message(self) -> None:
        c = Commit(
            "a" * 40,
            [],
            "A <a@b>",
            "A <a@b>",
            "msg",
            gpgsig="-----BEGIN PGP SIGNATURE-----\ndummy\n-----END PGP SIGNATURE-----",
        )
        valid, msg = verify_signature(c)
        self.assertFalse(valid)
        self.assertIn("not implemented", msg)

    def test_unsigned_tag_returns_valid(self) -> None:
        t = Tag("a" * 40, "commit", "v1", "A <a@b>", "msg", gpg_signature=None)
        valid, msg = verify_signature(t)
        self.assertTrue(valid)
        self.assertEqual(msg, "")

    def test_signed_tag_returns_stub_message(self) -> None:
        t = Tag(
            "a" * 40,
            "commit",
            "v1",
            "A <a@b>",
            "msg",
            gpg_signature=b"-----BEGIN PGP SIGNATURE-----\ndummy\n-----END PGP SIGNATURE-----",
        )
        valid, msg = verify_signature(t)
        self.assertFalse(valid)
        self.assertIn("not implemented", msg)
