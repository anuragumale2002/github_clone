"""Git pkt-line format: 4 hex length + payload; 0000 = flush (Phase E)."""

from __future__ import annotations

import struct
from typing import Iterator, List, Optional

# Max payload 65520; total line max 65524
PKT_MAX_PAYLOAD = 65520
PKT_FLUSH = b"0000"


def pkt_encode(data: bytes) -> bytes:
    """Encode one pkt-line. data should not include trailing LF unless desired. Returns length(4 hex) + data."""
    n = 4 + len(data)
    if n > 65524:
        raise ValueError("pkt-line too long")
    return f"{n:04x}".encode() + data


def pkt_encode_line(line: str) -> bytes:
    """Encode a text line (adds LF)."""
    return pkt_encode(line.encode("utf-8") + b"\n")


def pkt_flush() -> bytes:
    """Return flush packet (0000)."""
    return PKT_FLUSH


def pkt_read(stream: "bytes | list[bytes]", pos: int = 0) -> tuple[Optional[bytes], int]:
    """Read one pkt-line from stream (bytes or list of chunks). Returns (payload or None for flush, new_pos)."""
    if isinstance(stream, bytes):
        data = stream
        start = pos
        if start + 4 > len(data):
            return (None, pos)
        length_hex = data[start : start + 4].decode("ascii")
        try:
            length = int(length_hex, 16)
        except ValueError:
            return (None, pos)
        if length == 0:
            return (None, start + 4)
        if start + length > len(data):
            return (None, pos)
        payload = data[start + 4 : start + length]
        return (payload, start + length)
    # list of chunks
    chunks = stream
    if pos >= sum(len(c) for c in chunks):
        return (None, pos)
    offset = 0
    for c in chunks:
        if offset + len(c) > pos:
            break
        offset += len(c)
    rest = b"".join(chunks)[pos:]
    if len(rest) < 4:
        return (None, pos)
    length_hex = rest[:4].decode("ascii")
    try:
        length = int(length_hex, 16)
    except ValueError:
        return (None, pos)
    if length == 0:
        return (None, pos + 4)
    if len(rest) < length:
        return (None, pos)
    return (rest[4:length], pos + length)


def pkt_iter(stream: bytes) -> Iterator[Optional[bytes]]:
    """Yield pkt-line payloads from stream; None for flush."""
    pos = 0
    while pos < len(stream):
        payload, next_pos = pkt_read(stream, pos)
        if next_pos == pos:
            break
        pos = next_pos
        yield payload


def pkt_parse_refs(data: bytes) -> List[tuple[str, str]]:
    """Parse ref advertisement: lines like 'sha refname\\0capabilities' or 'sha refname'. Return [(refname, sha), ...]."""
    result: List[tuple[str, str]] = []
    for payload in pkt_iter(data):
        if payload is None:
            continue
        line = payload.decode("utf-8", errors="replace").strip()
        if not line or line.startswith("#"):
            continue
        parts = line.split(None, 1)
        if len(parts) < 2:
            continue
        sha, ref_part = parts[0], parts[1]
        if "\0" in ref_part:
            refname = ref_part.split("\0")[0]
        else:
            refname = ref_part
        if len(sha) == 40 and refname:
            result.append((refname, sha.lower()))
    return result
