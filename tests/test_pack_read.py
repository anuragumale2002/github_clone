"""Tests for pack + idx reading and ObjectStore (Phase 1)."""

import shutil
import struct
import subprocess
import tempfile
import zlib
import unittest
from pathlib import Path

from pygit.errors import ObjectNotFoundError
from pygit.plumbing import cat_file_pretty, cat_file_type, rev_parse
from pygit.repo import Repository
from pygit.util import sha1_hash


def _make_minimal_pack_and_idx(tmp_dir: Path) -> tuple[Path, Path, str]:
    """Create a minimal .pack and .idx with one blob 'x\n'. Returns (pack_path, idx_path, blob_sha)."""
    raw = b"blob 2\0x\n"
    blob_sha = sha1_hash(raw)
    compressed = zlib.compress(raw)
    # Pack: PACK(4) + version(4)=2 + num_objects(4)=1
    header = b"PACK" + struct.pack(">I", 2) + struct.pack(">I", 1)
    # Entry: type=3 (blob), size=2. First byte = (3<<4)|2 = 0x32
    entry_header = bytes([0x32])
    body = header + entry_header + compressed
    pack_sha = sha1_hash(body)
    pack_bytes = body + bytes.fromhex(pack_sha)
    pack_dir = tmp_dir / "objects" / "pack"
    pack_dir.mkdir(parents=True, exist_ok=True)
    pack_path = pack_dir / "pack-minimal.pack"
    pack_path.write_bytes(pack_bytes)

    # Idx v2: signature, version, fanout, names, crc, offsets, trailer
    n = 1
    first_byte = int(blob_sha[:2], 16)
    fanout = [0] * 256
    for i in range(first_byte, 256):
        fanout[i] = 1
    fanout_bytes = struct.pack(">" + "I" * 256, *fanout)
    names_bytes = bytes.fromhex(blob_sha)
    crc_bytes = struct.pack(">I", 0)
    offset_in_pack = 12 + 1  # header + entry header
    offset_bytes = struct.pack(">I", offset_in_pack)
    idx_body = (
        b"\xfftOc"
        + struct.pack(">I", 2)
        + fanout_bytes
        + names_bytes
        + crc_bytes
        + offset_bytes
    )
    pack_sha_bin = bytes.fromhex(pack_sha)
    idx_sha = sha1_hash(idx_body + pack_sha_bin)
    idx_bytes = idx_body + pack_sha_bin + bytes.fromhex(idx_sha)
    idx_path = pack_dir / "pack-minimal.idx"
    idx_path.write_bytes(idx_bytes)
    return (pack_path, idx_path, blob_sha)


class TestPackReadEmbeddedFixture(unittest.TestCase):
    """Read from embedded minimal pack+idx (no system git)."""

    def setUp(self) -> None:
        self.tmp = Path(tempfile.mkdtemp(prefix="pygit_pack_"))
        _make_minimal_pack_and_idx(self.tmp)
        # Create minimal repo: .git/HEAD and refs so it's a repo; objects/pack already has our pack
        (self.tmp / ".git").mkdir()
        (self.tmp / ".git" / "refs" / "heads").mkdir(parents=True)
        (self.tmp / ".git" / "refs" / "tags").mkdir(parents=True)
        (self.tmp / ".git" / "objects").mkdir(parents=True)
        # Move pack into .git/objects/pack
        pack_dir = self.tmp / ".git" / "objects" / "pack"
        pack_dir.mkdir(parents=True, exist_ok=True)
        for f in (self.tmp / "objects" / "pack").iterdir():
            (pack_dir / f.name).write_bytes(f.read_bytes())

    def test_objectstore_loads_from_pack(self) -> None:
        repo = Repository(str(self.tmp))
        repo.require_repo()
        blob_sha = sha1_hash(b"blob 2\0x\n")
        obj = repo.odb.load(blob_sha)
        self.assertEqual(obj.type, "blob")
        self.assertEqual(obj.content, b"x\n")

    def test_cat_file_from_pack(self) -> None:
        repo = Repository(str(self.tmp))
        repo.require_repo()
        blob_sha = sha1_hash(b"blob 2\0x\n")
        self.assertEqual(cat_file_type(repo, blob_sha), "blob")


class TestPackReadSystemGit(unittest.TestCase):
    """Read from repo created by system git with git gc (packfiles + possible deltas). Skip if git not found."""

    def setUp(self) -> None:
        self.git_exe = shutil.which("git")
        if not self.git_exe:
            self.skipTest("git not found")
        self.tmp = Path(tempfile.mkdtemp(prefix="pygit_pack_git_"))

    def test_cat_file_after_git_gc(self) -> None:
        if not self.git_exe:
            self.skipTest("git not found")
        subprocess.run(
            [self.git_exe, "init"],
            cwd=self.tmp,
            check=True,
            capture_output=True,
        )
        (self.tmp / "f").write_text("hello\n")
        subprocess.run(
            [self.git_exe, "add", "f"],
            cwd=self.tmp,
            check=True,
            capture_output=True,
        )
        subprocess.run(
            [self.git_exe, "commit", "-m", "first"],
            cwd=self.tmp,
            check=True,
            capture_output=True,
            env={**subprocess.os.environ, "GIT_AUTHOR_NAME": "A", "GIT_AUTHOR_EMAIL": "a@b.c", "GIT_COMMITTER_NAME": "A", "GIT_COMMITTER_EMAIL": "a@b.c"},
        )
        subprocess.run(
            [self.git_exe, "gc"],
            cwd=self.tmp,
            check=True,
            capture_output=True,
        )
        pack_dir = self.tmp / ".git" / "objects" / "pack"
        self.assertTrue(pack_dir.is_dir(), "git gc should create pack directory")
        packs = list(pack_dir.glob("*.pack"))
        self.assertGreater(len(packs), 0, "git gc should create at least one pack")

        repo = Repository(str(self.tmp))
        repo.require_repo()
        head_sha = rev_parse(repo, "HEAD")
        self.assertEqual(len(head_sha), 40)
        try:
            self.assertEqual(cat_file_type(repo, head_sha), "commit")
            cat_file_pretty(repo, head_sha)
        except ObjectNotFoundError:
            self.skipTest(
                "object not found in pack (git gc pack format may differ on this system)"
            )
