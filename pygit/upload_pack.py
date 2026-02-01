"""Minimal smart protocol: upload-pack client (pkt-line + want/have + receive pack). Phase E."""

from __future__ import annotations

import socket
from pathlib import Path
from typing import TYPE_CHECKING, List, Optional, Set, Tuple

from .constants import SHA1_HEX_LEN
from .errors import PygitError
from .idx import write_idx
from .pack import PACK_SIGNATURE, get_pack_sha_offsets
from .pkt_line import pkt_encode_line, pkt_flush, pkt_parse_refs
from .util import sha1_hash, write_bytes

if TYPE_CHECKING:
    from .repo import Repository


def _pkt_read_from_sock(sock: socket.socket, timeout: float = 30.0) -> bytes:
    """Read pkt-line stream from socket until flush; return all bytes (including flush)."""
    sock.settimeout(timeout)
    chunks: List[bytes] = []
    while True:
        try:
            head = sock.recv(4)
        except (socket.timeout, OSError) as e:
            raise PygitError(f"upload-pack read: {e}") from e
        if len(head) < 4:
            break
        try:
            length = int(head.decode("ascii"), 16)
        except ValueError:
            break
        if length == 0:
            chunks.append(head)
            break
        rest = length - 4
        if rest > 0:
            got = b""
            while len(got) < rest:
                part = sock.recv(min(65536, rest - len(got)))
                if not part:
                    break
                got += part
            chunks.append(head + got)
        else:
            chunks.append(head)
    return b"".join(chunks)


def _send_pkt(sock: socket.socket, data: bytes) -> None:
    sock.sendall(data)


def upload_pack_advertise(sock: socket.socket, path: str = "/", timeout: float = 30.0) -> List[Tuple[str, str]]:
    """Send upload-pack advertise request; read ref advertisement. Returns [(refname, sha), ...]."""
    line = f"git-upload-pack {path}\0"
    if len(line) + 4 > 65524:
        raise PygitError("path too long")
    pkt = f"{4 + len(line):04x}".encode() + line.encode("utf-8")
    _send_pkt(sock, pkt + pkt_flush())
    data = _pkt_read_from_sock(sock, timeout=timeout)
    return pkt_parse_refs(data)


def upload_pack_fetch(
    sock: socket.socket,
    want: List[str],
    have: Optional[Set[str]] = None,
    timeout: float = 30.0,
) -> bytes:
    """Send want/have/done; read pack data from socket. Returns raw pack bytes (with trailer)."""
    have = have or set()
    for sha in want:
        if len(sha) != SHA1_HEX_LEN:
            raise PygitError(f"invalid want sha: {sha}")
        _send_pkt(sock, pkt_encode_line(f"want {sha}"))
    for sha in have:
        if len(sha) != SHA1_HEX_LEN:
            continue
        _send_pkt(sock, pkt_encode_line(f"have {sha}"))
    _send_pkt(sock, pkt_encode_line("done"))
    _send_pkt(sock, pkt_flush())
    sock.settimeout(timeout)
    buf = b""
    try:
        while True:
            chunk = sock.recv(65536)
            if not chunk:
                break
            buf += chunk
    except socket.timeout:
        pass
    pack_start = buf.find(PACK_SIGNATURE)
    if pack_start == -1:
        raise PygitError("upload-pack: no pack data received")
    pack_bytes = buf[pack_start:]
    if len(pack_bytes) < 12 + 20:
        raise PygitError("upload-pack: pack too short")
    return pack_bytes


def fetch_via_upload_pack_tcp(
    repo: "Repository",
    host: str,
    port: int,
    path: str = "/",
    want_refs: Optional[List[str]] = None,
    timeout: float = 30.0,
) -> None:
    """Fetch from upload-pack over TCP: advertise refs, want/have/done, receive pack, write pack+idx."""
    repo.require_repo()
    want_refs = want_refs or ["refs/heads/main"]
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    try:
        sock.connect((host, port))
    except OSError as e:
        raise PygitError(f"upload-pack connect: {e}") from e
    try:
        refs = upload_pack_advertise(sock, path=path, timeout=timeout)
        want_shas = []
        for ref in want_refs:
            sha = next((s for r, s in refs if r == ref), None)
            if sha:
                want_shas.append(sha)
        if not want_shas:
            return
        have_shas: Set[str] = set()
        from .refs import resolve_ref
        for name in ["refs/heads/main", "HEAD"]:
            sha = resolve_ref(repo.git_dir, name)
            if sha:
                have_shas.add(sha)
        pack_bytes = upload_pack_fetch(sock, want=want_shas, have=have_shas, timeout=timeout)
    finally:
        sock.close()
    objects_dir = repo.git_dir / "objects"
    pack_dir = objects_dir / "pack"
    pack_dir.mkdir(parents=True, exist_ok=True)
    pack_sha = pack_bytes[-20:].hex()
    pack_path = pack_dir / f"pack-{pack_sha}.pack"
    write_bytes(pack_path, pack_bytes)

    def get_base(s: str) -> bytes:
        return repo.odb._raw_load(s)

    try:
        entries = get_pack_sha_offsets(pack_path, get_base)
    except Exception as e:
        pack_path.unlink(missing_ok=True)
        raise PygitError(f"upload-pack: invalid pack: {e}") from e
    write_idx(pack_path.with_suffix(".idx"), pack_sha, entries)
    repo.odb.rescan_packs()
