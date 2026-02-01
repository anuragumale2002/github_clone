"""Tests for smart protocol upload-pack client (Phase E)."""

import socket
import tempfile
import threading
import unittest
from pathlib import Path

from pygit.pack import PACK_SIGNATURE, get_pack_sha_offsets, write_pack
from pygit.pkt_line import pkt_encode, pkt_flush
from pygit.repo import Repository
from pygit.upload_pack import fetch_via_upload_pack_tcp
from pygit.util import sha1_hash


def _make_minimal_pack_with_commit() -> tuple[bytes, str]:
    """Build a minimal pack containing one commit, one tree, one blob. Returns (pack_bytes, commit_sha)."""
    raw_blob = b"blob 2\0x\n"
    blob_sha = sha1_hash(raw_blob)
    tree_content = b"100644 f\0" + bytes.fromhex(blob_sha)
    raw_tree = b"tree %d\0" % len(tree_content) + tree_content
    tree_sha = sha1_hash(raw_tree)
    commit_content = (
        b"tree " + tree_sha.encode() + b"\n"
        b"author A <a@b> 0 +0000\n"
        b"committer A <a@b> 0 +0000\n"
        b"\nfirst\n"
    )
    raw_commit = b"commit %d\0" % len(commit_content) + commit_content
    commit_sha = sha1_hash(raw_commit)

    objects = sorted([blob_sha, tree_sha, commit_sha])

    def get_raw(sha: str) -> bytes:
        if sha == blob_sha:
            return raw_blob
        if sha == tree_sha:
            return raw_tree
        if sha == commit_sha:
            return raw_commit
        raise KeyError(sha)

    pack_bytes, _ = write_pack(Path("."), objects, get_raw)
    return (pack_bytes, commit_sha)


def _read_pkt_line_from_sock(sock: socket.socket, buf: bytearray) -> bytes | None:
    """Read one pkt-line from socket; append to buf. Return payload or None for flush."""
    while len(buf) < 4:
        chunk = sock.recv(4096)
        if not chunk:
            return None
        buf.extend(chunk)
    length_hex = buf[:4].decode("ascii")
    try:
        length = int(length_hex, 16)
    except ValueError:
        return None
    while len(buf) < length:
        chunk = sock.recv(4096)
        if not chunk:
            return None
        buf.extend(chunk)
    payload = buf[4:length]
    del buf[:length]
    if length == 0:
        return None
    return payload


def _run_upload_pack_stub_once(
    listen_sock: socket.socket,
    pack_bytes: bytes,
    ref_line: bytes,
) -> None:
    """Accept one connection, speak minimal upload-pack, send refs then pack."""
    conn, _ = listen_sock.accept()
    try:
        buf = bytearray()
        # Read advertise request until flush
        while True:
            p = _read_pkt_line_from_sock(conn, buf)
            if p is None:
                break
        # Send ref advertisement
        conn.sendall(pkt_encode(ref_line) + pkt_flush())
        # Read want/have/done until flush
        buf.clear()
        while True:
            p = _read_pkt_line_from_sock(conn, buf)
            if p is None:
                break
        # Send raw pack
        conn.sendall(pack_bytes)
    finally:
        conn.close()


class TestUploadPackTcp(unittest.TestCase):
    """Fetch via upload-pack TCP against a minimal in-process server stub."""

    def setUp(self) -> None:
        self.tmp = Path(tempfile.mkdtemp(prefix="pygit_upload_pack_"))
        self.repo = Repository(str(self.tmp))
        self.repo.init()
        self.pack_bytes, self.commit_sha = _make_minimal_pack_with_commit()
        # Ref line: "sha refs/heads/main\0\n" so client can parse (refname, sha)
        self.ref_line = self.commit_sha.encode() + b" refs/heads/main\0\n"

    def test_minimal_pack_is_valid(self) -> None:
        """The minimal pack we build can be parsed by get_pack_sha_offsets."""
        pack_path = self.tmp / "test.pack"
        pack_path.write_bytes(self.pack_bytes)
        def get_base(s: str):
            raise KeyError(s)
        entries = get_pack_sha_offsets(pack_path, get_base)
        self.assertEqual(len(entries), 3)
        shas = {e[0] for e in entries}
        self.assertIn(self.commit_sha, shas)

    def test_fetch_via_upload_pack_tcp_receives_pack_and_objects(self) -> None:
        listen_sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        listen_sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        listen_sock.bind(("127.0.0.1", 0))
        port = listen_sock.getsockname()[1]
        listen_sock.listen(1)
        done = threading.Event()
        err: list[Exception] = []

        def server_thread() -> None:
            try:
                _run_upload_pack_stub_once(listen_sock, self.pack_bytes, self.ref_line)
            except Exception as e:
                err.append(e)
            finally:
                done.set()

        t = threading.Thread(target=server_thread)
        t.start()
        try:
            fetch_via_upload_pack_tcp(
                self.repo,
                "127.0.0.1",
                port,
                path="/",
                want_refs=["refs/heads/main"],
                timeout=5.0,
            )
        finally:
            listen_sock.close()
            t.join(timeout=2.0)
        if err:
            raise err[0]

        self.assertTrue(
            self.repo.odb.exists(self.commit_sha),
            f"commit {self.commit_sha} should exist in odb after fetch",
        )
        obj = self.repo.load_object(self.commit_sha)
        self.assertEqual(obj.type, "commit")
