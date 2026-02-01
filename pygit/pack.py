"""Packfile parsing, delta resolution, and writing (Phase 2: no deltas on write)."""

from __future__ import annotations

import struct
import zlib
from pathlib import Path
from typing import Callable, Dict, Iterator, List, Optional, Tuple

from .constants import OBJ_BLOB, OBJ_COMMIT, OBJ_TAG, OBJ_TREE
from .errors import PackError
from .util import sha1_hash

# Reverse map: type name -> pack type number
TYPE_TO_NUM = {OBJ_COMMIT: 1, OBJ_TREE: 2, OBJ_BLOB: 3, OBJ_TAG: 4}

# Pack object types (from git)
OBJ_OFS_DELTA = 6
OBJ_REF_DELTA = 7

PACK_SIGNATURE = b"PACK"
PACK_HEADER_LEN = 12  # PACK(4) + version(4) + num_objects(4)
PACK_TRAILER_LEN = 20  # pack sha1

TYPE_NAMES = {
    1: OBJ_COMMIT,
    2: OBJ_TREE,
    3: OBJ_BLOB,
    4: OBJ_TAG,
}


def _read_size_encoding(data: bytes, start: int) -> tuple[int, int]:
    """Decode size encoding from data starting at start. Returns (value, num_bytes_consumed)."""
    if start >= len(data):
        raise PackError("size encoding truncated")
    byte = data[start]
    value = byte & 0x7F
    n = 1
    shift = 4  # first byte contributed 4 bits (low nibble)
    while byte & 0x80:
        start += 1
        if start >= len(data):
            raise PackError("size encoding truncated")
        byte = data[start]
        value |= (byte & 0x7F) << shift
        shift += 7
        n += 1
    return (value, n)


def _decode_entry_header(data: bytes, offset: int) -> tuple[int, int, int, Optional[str], Optional[int]]:
    """Decode one pack entry header. Returns (type, size, header_len, base_sha_or_none, base_offset_or_none)."""
    if offset >= len(data):
        raise PackError("entry header truncated")
    first = data[offset]
    obj_type = (first >> 4) & 0x07
    size = first & 0x0F
    pos = offset + 1
    shift = 4
    while first & 0x80:
        if pos >= len(data):
            raise PackError("size encoding truncated")
        b = data[pos]
        size |= (b & 0x7F) << shift
        shift += 7
        pos += 1
        first = b
    header_len = pos - offset

    base_sha: Optional[str] = None
    base_offset_pack: Optional[int] = None

    if obj_type == OBJ_REF_DELTA:
        if pos + 20 > len(data):
            raise PackError("ref-delta base id truncated")
        base_sha = data[pos : pos + 20].hex()
        header_len += 20
    elif obj_type == OBJ_OFS_DELTA:
        ofs, n = _read_size_encoding(data, pos)
        # Git: offset is "negative relative to the type byte of the current object"
        # So base_offset = entry_start - ofs (ofs is positive "distance back")
        base_offset_pack = ofs  # positive; caller does entry_start - ofs
        header_len += n

    return (obj_type, size, header_len, base_sha, base_offset_pack)


def _apply_delta(base_content: bytes, delta: bytes) -> bytes:
    """Apply git delta instructions to base_content; return result bytes."""
    if len(delta) < 2:
        raise PackError("delta too short")
    pos = 0

    def read_varint() -> int:
        nonlocal pos
        value = delta[pos] & 0x7F
        n = 1
        shift = 7
        while delta[pos] & 0x80:
            pos += 1
            if pos >= len(delta):
                raise PackError("delta varint truncated")
            value |= (delta[pos] & 0x7F) << shift
            shift += 7
            n += 1
        pos += 1
        return value

    base_size = read_varint()
    result_size = read_varint()
    if base_size != len(base_content):
        raise PackError(f"delta base size mismatch: expected {base_size}, got {len(base_content)}")

    result = bytearray()
    while pos < len(delta):
        cmd = delta[pos]
        pos += 1
        if cmd & 0x80:
            # Copy from base
            offset = 0
            size = 0
            offset_len = cmd & 0x0F
            size_len = (cmd >> 4) & 0x07
            for i in range(offset_len):
                if pos >= len(delta):
                    raise PackError("delta copy offset truncated")
                offset |= delta[pos] << (8 * i)
                pos += 1
            for i in range(size_len):
                if pos >= len(delta):
                    raise PackError("delta copy size truncated")
                size |= delta[pos] << (8 * i)
                pos += 1
            if size == 0:
                size = 0x10000
            result.extend(base_content[offset : offset + size])
        else:
            # Insert
            if cmd == 0:
                raise PackError("delta insert size 0")
            if pos + cmd > len(delta):
                raise PackError("delta insert truncated")
            result.extend(delta[pos : pos + cmd])
            pos += cmd

    if len(result) != result_size:
        raise PackError(f"delta result size mismatch: expected {result_size}, got {len(result)}")
    return bytes(result)


def _resolve_ofs_delta_base_offset(entry_start: int, distance_back: int) -> int:
    """Convert OFS_DELTA distance-back to absolute pack offset. Git: offset is negative from type byte of current object."""
    return entry_start - distance_back


def load_pack_object(
    pack_path: Path,
    pack_data: Optional[bytes],
    entry_offset: int,
    obj_type: int,
    size: int,
    header_len: int,
    base_sha: Optional[str],
    base_offset_encoded: Optional[int],
    get_base_content: Callable[[str], bytes],
    get_base_content_by_offset: Callable[[int], bytes],
) -> tuple[str, bytes]:
    """Load one object from pack at entry_offset. Returns (sha1_hex, raw_object_bytes). Raw = type + ' ' + size + '\\0' + content."""
    if pack_data is None:
        with open(pack_path, "rb") as f:
            f.seek(entry_offset + header_len)
            decompressor = zlib.decompressobj()
            chunks = []
            while True:
                chunk = f.read(65536)
                if not chunk:
                    break
                out = decompressor.decompress(chunk)
                chunks.append(out)
                if decompressor.unused_data:
                    break
            data = b"".join(chunks)
    else:
        data_start = entry_offset + header_len
        decompressor = zlib.decompressobj()
        data = decompressor.decompress(pack_data[data_start:])
        if not decompressor.unused_data and len(pack_data) > data_start + len(pack_data) - data_start:
            pass  # consumed all we gave; assume one object

    if obj_type in TYPE_NAMES:
        # Non-delta: data is "type size\0content"
        type_str = TYPE_NAMES[obj_type]
        return (sha1_hash(data), data)
    if obj_type == OBJ_REF_DELTA:
        if not base_sha:
            raise PackError("ref-delta missing base")
        base_content = get_base_content(base_sha)
        # Base content is full object bytes (type size\0content); we need just content for delta base
        null = base_content.find(b"\0")
        if null == -1:
            raise PackError("invalid base object")
        base_raw = base_content[null + 1 :]
        result_content = _apply_delta(base_raw, data)
        type_str = base_content.split(b" ", 1)[0].decode()
        result_size = len(result_content)
        result_bytes = f"{type_str} {result_size}\0".encode() + result_content
        return (sha1_hash(result_bytes), result_bytes)
    if obj_type == OBJ_OFS_DELTA:
        if base_offset_encoded is None:
            raise PackError("ofs-delta missing offset")
        base_pack_offset = _resolve_ofs_delta_base_offset(entry_offset, base_offset_encoded)
        base_content = get_base_content_by_offset(base_pack_offset)
        null = base_content.find(b"\0")
        if null == -1:
            raise PackError("invalid base object")
        base_raw = base_content[null + 1 :]
        result_content = _apply_delta(base_raw, data)
        type_str = base_content.split(b" ", 1)[0].decode()
        result_size = len(result_content)
        result_bytes = f"{type_str} {result_size}\0".encode() + result_content
        return (sha1_hash(result_bytes), result_bytes)
    raise PackError(f"unsupported object type {obj_type}")


def read_pack_header(path: Path) -> tuple[int, int]:
    """Read pack header; return (version, num_objects). Raises PackError if invalid."""
    data = path.read_bytes()[:PACK_HEADER_LEN]
    if len(data) < PACK_HEADER_LEN:
        raise PackError("pack file too short")
    if data[:4] != PACK_SIGNATURE:
        raise PackError("invalid pack signature")
    version, num_objects = struct.unpack(">II", data[4:12])
    if version not in (2, 3):
        raise PackError(f"unsupported pack version {version}")
    return (version, num_objects)


def iter_pack_entries(path: Path, pack_data: Optional[bytes] = None) -> Iterator[tuple[int, int, int, int, Optional[str], Optional[int]]]:
    """Yield (entry_offset, obj_type, size, header_len, base_sha, base_offset_encoded) for each entry.
    If pack_data is None, read from path. Otherwise use pack_data (and path is used for get_base_content_by_offset reads).
    """
    if pack_data is None:
        pack_data = path.read_bytes()
    if len(pack_data) < PACK_HEADER_LEN + PACK_TRAILER_LEN:
        raise PackError("pack file too short")
    version, num_objects = struct.unpack(">II", pack_data[4:12])
    if version not in (2, 3):
        raise PackError(f"unsupported pack version {version}")

    offset = PACK_HEADER_LEN
    end = len(pack_data) - PACK_TRAILER_LEN

    for _ in range(num_objects):
        if offset >= end:
            raise PackError("pack truncated")
        obj_type, size, header_len, base_sha, base_offset_enc = _decode_entry_header(pack_data, offset)
        entry_start = offset
        data_start = offset + header_len

        decompressor = zlib.decompressobj()
        decompressor.decompress(pack_data[data_start:])
        # Consumed bytes: we don't know exactly without tracking; use full remaining or chunk
        # Actually we need compressed size. Decompress until unused_data.
        chunk_start = data_start
        out_len = 0
        while chunk_start < len(pack_data):
            chunk = pack_data[chunk_start : chunk_start + 65536]
            if not chunk:
                break
            out = decompressor.decompress(chunk)
            out_len += len(out)
            consumed = len(chunk) - len(decompressor.unused_data)
            chunk_start += consumed
            if decompressor.unused_data:
                break
        compressed_len = chunk_start - data_start
        offset = data_start + compressed_len
        yield (entry_start, obj_type, size, header_len, base_sha, base_offset_enc)
    if offset != end:
        pass  # allow slack for zlib boundary; idx gives exact lookup
    return


def read_pack_entries_with_bases(
    path: Path,
    get_base_content: Callable[[str], bytes],
) -> dict[str, bytes]:
    """Read entire pack and resolve all objects (including deltas). Returns dict sha_hex -> raw_object_bytes."""
    pack_data = path.read_bytes()
    if len(pack_data) < PACK_HEADER_LEN + PACK_TRAILER_LEN:
        raise PackError("pack file too short")
    version, num_objects = struct.unpack(">II", pack_data[4:12])
    if version not in (2, 3):
        raise PackError(f"unsupported pack version {version}")

    # First pass: collect entry offsets and header info (and decompress to skip to next entry)
    entries: list[tuple[int, int, int, int, Optional[str], Optional[int], int]] = []
    offset = PACK_HEADER_LEN
    end = len(pack_data) - PACK_TRAILER_LEN

    for _ in range(num_objects):
        if offset >= end:
            raise PackError("pack truncated")
        obj_type, size, header_len, base_sha, base_offset_enc = _decode_entry_header(pack_data, offset)
        entry_start = offset
        data_start = offset + header_len

        decompressor = zlib.decompressobj()
        rest = pack_data[data_start:]
        decompressor.decompress(rest)
        consumed = len(rest) - len(decompressor.unused_data)
        compressed_len = consumed
        next_offset = data_start + compressed_len
        entries.append((entry_start, obj_type, size, header_len, base_sha, base_offset_enc, next_offset))
        offset = next_offset

    # Map pack file offset (of entry start) -> (entry_start, obj_type, size, header_len, base_sha, base_offset_enc, next_offset)
    offset_to_entry: dict[int, tuple[int, int, int, int, Optional[str], Optional[int], int]] = {}
    for tup in entries:
        entry_start = tup[0]
        offset_to_entry[entry_start] = tup

    resolved: dict[str, bytes] = {}
    resolved_by_offset: dict[int, bytes] = {}

    def get_base(sha: str) -> bytes:
        if sha in resolved:
            return resolved[sha]
        return get_base_content(sha)

    def get_base_by_offset(pack_off: int) -> bytes:
        if pack_off in resolved_by_offset:
            return resolved_by_offset[pack_off]
        raw = _resolve_one(pack_off)
        resolved_by_offset[pack_off] = raw
        return raw

    def _resolve_one(entry_start: int) -> bytes:
        tup = offset_to_entry.get(entry_start)
        if not tup:
            raise PackError(f"entry at {entry_start} not found")
        entry_off, obj_type, size, header_len, base_sha, base_offset_enc, next_off = tup
        data_start = entry_off + header_len
        compressed_len = next_off - data_start
        decompressor = zlib.decompressobj()
        data = decompressor.decompress(pack_data[data_start : data_start + compressed_len])

        if obj_type in TYPE_NAMES:
            sha = sha1_hash(data)
            resolved[sha] = data
            resolved_by_offset[entry_start] = data
            return data
        if obj_type == OBJ_REF_DELTA:
            base_content = get_base(base_sha)  # type: ignore[arg-type]
            null = base_content.find(b"\0")
            if null == -1:
                raise PackError("invalid base object")
            base_raw = base_content[null + 1 :]
            result_content = _apply_delta(base_raw, data)
            type_str = base_content.split(b" ", 1)[0].decode()
            result_bytes = f"{type_str} {len(result_content)}\0".encode() + result_content
            sha = sha1_hash(result_bytes)
            resolved[sha] = result_bytes
            resolved_by_offset[entry_start] = result_bytes
            return result_bytes
        if obj_type == OBJ_OFS_DELTA:
            base_pack_offset = _resolve_ofs_delta_base_offset(entry_off, base_offset_enc)  # type: ignore[arg-type]
            base_content = get_base_by_offset(base_pack_offset)
            null = base_content.find(b"\0")
            if null == -1:
                raise PackError("invalid base object")
            base_raw = base_content[null + 1 :]
            result_content = _apply_delta(base_raw, data)
            type_str = base_content.split(b" ", 1)[0].decode()
            result_bytes = f"{type_str} {len(result_content)}\0".encode() + result_content
            sha = sha1_hash(result_bytes)
            resolved[sha] = result_bytes
            resolved_by_offset[entry_start] = result_bytes
            return result_bytes
        raise PackError(f"unsupported type {obj_type}")

    for tup in sorted(entries, key=lambda t: t[0]):
        entry_start = tup[0]
        if entry_start not in resolved_by_offset:
            _resolve_one(entry_start)

    return resolved


def get_pack_sha_offsets(
    path: Path,
    get_base_content: Callable[[str], bytes],
) -> List[Tuple[str, int]]:
    """Read pack and return [(sha_hex, entry_offset), ...] for building idx. Resolves deltas."""
    pack_data = path.read_bytes()
    if len(pack_data) < PACK_HEADER_LEN + PACK_TRAILER_LEN:
        raise PackError("pack file too short")
    version, num_objects = struct.unpack(">II", pack_data[4:12])
    if version not in (2, 3):
        raise PackError(f"unsupported pack version {version}")
    entries = []
    offset = PACK_HEADER_LEN
    end = len(pack_data) - PACK_TRAILER_LEN
    for _ in range(num_objects):
        if offset >= end:
            raise PackError("pack truncated")
        obj_type, size, header_len, base_sha, base_offset_enc = _decode_entry_header(pack_data, offset)
        entry_start = offset
        data_start = offset + header_len
        decompressor = zlib.decompressobj()
        rest = pack_data[data_start:]
        decompressor.decompress(rest)
        consumed = len(rest) - len(decompressor.unused_data)
        next_offset = data_start + consumed
        entries.append((entry_start, obj_type, size, header_len, base_sha, base_offset_enc, next_offset))
        offset = next_offset
    offset_to_entry = {t[0]: t for t in entries}
    resolved_by_offset: Dict[int, bytes] = {}
    resolved: Dict[str, bytes] = {}

    def get_base(s: str) -> bytes:
        if s in resolved:
            return resolved[s]
        return get_base_content(s)

    def get_base_by_offset(pack_off: int) -> bytes:
        if pack_off in resolved_by_offset:
            return resolved_by_offset[pack_off]
        raw = _resolve_one(pack_off)
        resolved_by_offset[pack_off] = raw
        return raw

    def _resolve_one(entry_start: int) -> bytes:
        tup = offset_to_entry.get(entry_start)
        if not tup:
            raise PackError(f"entry at {entry_start} not found")
        entry_off, obj_type, size, header_len, base_sha, base_offset_enc, next_off = tup
        data_start = entry_off + header_len
        compressed_len = next_off - data_start
        decompressor = zlib.decompressobj()
        data = decompressor.decompress(pack_data[data_start : data_start + compressed_len])
        if obj_type in TYPE_NAMES:
            sha = sha1_hash(data)
            resolved[sha] = data
            resolved_by_offset[entry_start] = data
            return data
        if obj_type == OBJ_REF_DELTA:
            base_content = get_base(base_sha)  # type: ignore[arg-type]
            null = base_content.find(b"\0")
            if null == -1:
                raise PackError("invalid base object")
            base_raw = base_content[null + 1 :]
            result_content = _apply_delta(base_raw, data)
            type_str = base_content.split(b" ", 1)[0].decode()
            result_bytes = f"{type_str} {len(result_content)}\0".encode() + result_content
            sha = sha1_hash(result_bytes)
            resolved[sha] = result_bytes
            resolved_by_offset[entry_start] = result_bytes
            return result_bytes
        if obj_type == OBJ_OFS_DELTA:
            base_pack_offset = _resolve_ofs_delta_base_offset(entry_off, base_offset_enc)  # type: ignore[arg-type]
            base_content = get_base_by_offset(base_pack_offset)
            null = base_content.find(b"\0")
            if null == -1:
                raise PackError("invalid base object")
            base_raw = base_content[null + 1 :]
            result_content = _apply_delta(base_raw, data)
            type_str = base_content.split(b" ", 1)[0].decode()
            result_bytes = f"{type_str} {len(result_content)}\0".encode() + result_content
            sha = sha1_hash(result_bytes)
            resolved[sha] = result_bytes
            resolved_by_offset[entry_start] = result_bytes
            return result_bytes
        raise PackError(f"unsupported type {obj_type}")

    for tup in sorted(entries, key=lambda t: t[0]):
        if tup[0] not in resolved_by_offset:
            _resolve_one(tup[0])
    return [(sha1_hash(resolved_by_offset[es]), es) for es in sorted(offset_to_entry.keys())]


# --- Pack writing (Phase 2, no deltas) ---


def _encode_type_size(type_num: int, size: int) -> bytes:
    """Encode object type and size as pack entry header (varint). type_num 1-4 only."""
    buf = bytearray()
    first = (type_num << 4) | (size & 0x0F)
    size >>= 4
    if size:
        first |= 0x80  # MSB set so reader continues to next byte
    while size:
        buf.append(size & 0x7F)
        size >>= 7
    # MSB set on all continuation bytes except the last (Git pack format)
    for i in range(len(buf) - 1):
        buf[i] |= 0x80
    return bytes([first]) + bytes(buf)


def write_pack(
    path: Path,
    object_ids: List[str],
    get_raw: Callable[[str], bytes],
) -> Tuple[bytes, List[Tuple[str, int]]]:
    """Write a pack file (no deltas). get_raw(sha) returns raw object bytes (type size\\0content).
    object_ids must be sorted deterministically (e.g. sorted by sha).
    Returns (pack_bytes, list of (sha, offset) for each object entry start).
    Caller computes pack_sha = sha1_hash(pack_bytes) and appends it to form final pack file.
    """
    object_ids = sorted(object_ids)
    header = PACK_SIGNATURE + struct.pack(">II", 2, len(object_ids))
    body_parts: List[bytes] = [header]
    offsets: List[Tuple[str, int]] = []
    pos = len(header)

    for sha in object_ids:
        raw = get_raw(sha)
        null = raw.find(b"\0")
        if null == -1:
            raise PackError(f"invalid raw object for {sha}")
        header = raw[:null].decode()
        parts = header.split(" ", 1)
        type_str = parts[0]
        type_num = TYPE_TO_NUM.get(type_str)
        if type_num is None:
            raise PackError(f"unsupported type for pack write: {type_str}")
        size = int(parts[1])
        entry_header = _encode_type_size(type_num, size)
        compressed = zlib.compress(raw, level=zlib.Z_BEST_SPEED)
        entry = entry_header + compressed
        body_parts.append(entry)
        offsets.append((sha, pos))
        pos += len(entry)

    body = b"".join(body_parts)
    pack_sha = sha1_hash(body)
    return (body + bytes.fromhex(pack_sha), offsets)
