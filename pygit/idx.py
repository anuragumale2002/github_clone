"""Pack index v2 parsing and writing (Phase 2)."""

from __future__ import annotations

import struct
from pathlib import Path
from typing import Iterator, List, Optional, Tuple

from .constants import MIN_PREFIX_LEN, SHA1_HEX_LEN
from .errors import AmbiguousRefError, IdxError, ObjectNotFoundError
from .util import sha1_hash, write_bytes_atomic

IDX_SIGNATURE = b"\xfftOc"
IDX_VERSION_V2 = 2
FANOUT_COUNT = 256
FANOUT_ENTRIES = 256 * 4  # 1024 bytes
TRAILER_LEN = 20 + 20  # pack sha1 + idx sha1


class IdxV2:
    """Pack index v2: lookup by sha, iter_shas, resolve_prefix."""

    def __init__(self, path: Path) -> None:
        self.path = Path(path)
        self._data = self.path.read_bytes()
        self._parse()

    def _parse(self) -> None:
        if len(self._data) < 8 + FANOUT_ENTRIES:
            raise IdxError("idx file too short")
        if self._data[:4] != IDX_SIGNATURE:
            raise IdxError("invalid idx signature")
        version = struct.unpack(">I", self._data[4:8])[0]
        if version != IDX_VERSION_V2:
            raise IdxError(f"unsupported idx version {version}")

        # Fanout: 256 * 4 bytes big-endian
        self._fanout: List[int] = list(struct.unpack(">" + "I" * 256, self._data[8 : 8 + FANOUT_ENTRIES]))
        n = self._fanout[255]
        if n == 0:
            self._names: List[str] = []
            self._offsets: List[int] = []
            self._crc: List[int] = []
            self._pack_sha: Optional[str] = None
            self._idx_sha: Optional[str] = None
            return

        # Names: N * 20 bytes
        names_start = 8 + FANOUT_ENTRIES
        names_len = n * 20
        names_end = names_start + names_len
        if len(self._data) < names_end + n * 4 + n * 4:
            raise IdxError("idx truncated at names/crc/offsets")
        self._names = []
        for i in range(n):
            start = names_start + i * 20
            sha_bin = self._data[start : start + 20]
            self._names.append(sha_bin.hex())

        # CRC: N * 4 bytes
        crc_start = names_end
        self._crc = list(struct.unpack(">" + "I" * n, self._data[crc_start : crc_start + n * 4]))

        # Offsets: N * 4 bytes (network order)
        offset_start = crc_start + n * 4
        offset_end = offset_start + n * 4
        offsets_4 = struct.unpack(">" + "I" * n, self._data[offset_start:offset_end])
        self._offsets = list(offsets_4)

        # Large offset table: entries with MSB set get 8-byte offset from next table
        # Trailer is always last 40 bytes (Git may write optional extension data before it)
        if len(self._data) < TRAILER_LEN:
            raise IdxError("idx file too short for trailer")
        trailer_start = len(self._data) - TRAILER_LEN
        self._pack_sha = self._data[trailer_start : trailer_start + 20].hex()
        self._idx_sha = self._data[trailer_start + 20 : trailer_start + 40].hex()

        large_count = sum(1 for o in self._offsets if (o & 0x80000000) != 0)
        pos = offset_end
        if large_count > 0:
            if pos + large_count * 8 > trailer_start:
                raise IdxError("idx truncated at large offsets")
            large_table = []
            for _ in range(large_count):
                lo = struct.unpack(">Q", self._data[pos : pos + 8])[0]
                large_table.append(lo)
                pos += 8
            idx_large = 0
            for i in range(n):
                if (self._offsets[i] & 0x80000000) != 0:
                    self._offsets[i] = large_table[idx_large]
                    idx_large += 1

    def lookup(self, sha1_hex: str) -> Optional[int]:
        """Return pack file offset for object, or None if not in this index."""
        if len(sha1_hex) != SHA1_HEX_LEN:
            return None
        sha1_hex = sha1_hex.lower()
        sha_bin = bytes.fromhex(sha1_hex)
        first_byte = sha_bin[0]
        lo = self._fanout[first_byte - 1] if first_byte > 0 else 0
        hi = self._fanout[first_byte]
        if lo >= hi:
            return None
        # Binary search in [lo, hi)
        while lo < hi:
            mid = (lo + hi) // 2
            name = self._names[mid]
            if name < sha1_hex:
                lo = mid + 1
            elif name > sha1_hex:
                hi = mid
            else:
                return self._offsets[mid]
        return None

    def iter_shas(self, prefix: Optional[str] = None) -> Iterator[str]:
        """Yield object SHAs in index order. If prefix is set, only yield SHAs starting with prefix."""
        for name in self._names:
            if prefix is None or name.startswith(prefix.lower()):
                yield name

    def resolve_prefix(self, prefix: str, min_len: int = MIN_PREFIX_LEN) -> str:
        """Resolve prefix to full 40-char SHA. Raises ObjectNotFoundError or AmbiguousRefError."""
        prefix = prefix.lower()
        if len(prefix) < min_len:
            raise ObjectNotFoundError(f"prefix too short: {prefix}")
        if not all(c in "0123456789abcdef" for c in prefix):
            raise ObjectNotFoundError(f"invalid prefix: {prefix}")
        matches = [name for name in self._names if name.startswith(prefix)]
        if not matches:
            raise ObjectNotFoundError(f"object {prefix} not found in index")
        if len(matches) > 1:
            raise AmbiguousRefError(f"prefix '{prefix}' is ambiguous: {matches}")
        return matches[0]

    @property
    def pack_sha(self) -> Optional[str]:
        return self._pack_sha

    @property
    def object_count(self) -> int:
        return len(self._names)


# --- Idx v2 writing (Phase 2) ---


def write_idx(
    path: Path,
    pack_sha_hex: str,
    entries: List[Tuple[str, int]],
    crc_list: Optional[List[int]] = None,
) -> str:
    """Write idx v2 file. entries = [(sha_hex, offset), ...] sorted by sha.
    crc_list optional (N entries); use 0 if None. Returns idx file SHA1 (hex).
    Uses atomic write (temp then replace).
    """
    entries = sorted(entries, key=lambda e: e[0].lower())
    n = len(entries)
    pack_sha_bin = bytes.fromhex(pack_sha_hex.lower())

    # Fanout: fanout[i] = cumulative count of objects with first byte <= i
    fanout = [0] * 256
    for sha, _ in entries:
        fb = int(sha[:2], 16)
        fanout[fb] += 1
    for i in range(1, 256):
        fanout[i] += fanout[i - 1]

    body_parts: List[bytes] = [
        IDX_SIGNATURE,
        struct.pack(">I", IDX_VERSION_V2),
        struct.pack(">" + "I" * 256, *fanout),
    ]
    for sha, _ in entries:
        body_parts.append(bytes.fromhex(sha.lower()))
    names_crc_offsets = b"".join(body_parts[2:])  # after version: fanout + names
    # CRC: N * 4 bytes (0 if not provided)
    if crc_list is not None and len(crc_list) == n:
        body_parts.append(struct.pack(">" + "I" * n, *crc_list))
    else:
        body_parts.append(struct.pack(">" + "I" * n, *([0] * n)))

    # Offsets: 4 bytes each, or 0x80000000 | index for 8-byte table
    offsets_4: List[int] = []
    large_offsets: List[int] = []
    for _, off in entries:
        if off < 0x80000000:
            offsets_4.append(off)
        else:
            idx_large = len(large_offsets)
            large_offsets.append(off)
            offsets_4.append(0x80000000 | idx_large)
    body_parts.append(struct.pack(">" + "I" * n, *offsets_4))
    for lo in large_offsets:
        body_parts.append(struct.pack(">Q", lo))

    body = b"".join(body_parts)
    idx_sha = sha1_hash(body + pack_sha_bin)
    idx_bytes = body + pack_sha_bin + bytes.fromhex(idx_sha)

    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    write_bytes_atomic(path, idx_bytes)
    return idx_sha
