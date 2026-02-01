"""Unified object store: loose + packed objects. Phase 1: read-only pack support."""

from __future__ import annotations

import zlib
from pathlib import Path
from typing import Dict, List, Optional, Tuple

from .constants import MIN_PREFIX_LEN, SHA1_HEX_LEN
from .errors import AmbiguousRefError, IdxError, ObjectNotFoundError, PackError
from .idx import IdxV2
from .objects import GitObject
from .odb import ObjectDB
from .pack import read_pack_entries_with_bases
from .util import write_bytes


class ObjectStore:
    """Unified object database: loose objects + pack files (read)."""

    def __init__(self, objects_dir: Path) -> None:
        self.objects_dir = Path(objects_dir)
        self._loose = ObjectDB(self.objects_dir)
        self._packs: List[Tuple[Path, IdxV2]] = []
        self._pack_caches: Dict[Path, Dict[str, bytes]] = {}
        self._scan_packs()

    def _scan_packs(self) -> None:
        """Scan .git/objects/pack/*.idx and register each with its .pack file."""
        pack_dir = self.objects_dir / "pack"
        if not pack_dir.is_dir():
            return
        for idx_path in pack_dir.glob("*.idx"):
            pack_path = idx_path.with_suffix(".pack")
            if not pack_path.is_file():
                continue
            try:
                idx = IdxV2(idx_path)
                self._packs.append((pack_path, idx))
            except (IdxError, PackError):
                continue

    def rescan_packs(self) -> None:
        """Rescan pack directory (e.g. after gc/repack). Clears pack caches and reloads idx list."""
        self._packs.clear()
        self._pack_caches.clear()
        self._scan_packs()

    def _raw_load(self, sha: str) -> bytes:
        """Load raw object bytes (type size\\0content). From loose or pack. Raises ObjectNotFoundError."""
        sha = sha.lower()
        # 1) Loose
        path = self._loose._object_path(sha)
        if path.exists():
            raw = path.read_bytes()
            return zlib.decompress(raw)

        # 2) Pack caches (already loaded)
        for pack_path, _ in self._packs:
            cache = self._pack_caches.get(pack_path)
            if cache and sha in cache:
                return cache[sha]

        # 3) Lookup in pack indices and load pack if found
        for pack_path, idx in self._packs:
            offset = idx.lookup(sha)
            if offset is not None:
                if pack_path not in self._pack_caches:
                    try:
                        resolved = read_pack_entries_with_bases(pack_path, get_base_content=self._raw_load)
                        self._pack_caches[pack_path] = resolved
                    except PackError:
                        continue
                if sha in self._pack_caches[pack_path]:
                    return self._pack_caches[pack_path][sha]
                break

        raise ObjectNotFoundError(f"object {sha} not found")

    def _raw_to_object(self, raw: bytes) -> GitObject:
        """Convert raw object bytes (type size\\0content) to GitObject."""
        return GitObject.deserialize(zlib.compress(raw))

    def exists(self, sha: str) -> bool:
        """Return True if object exists (loose or packed)."""
        if len(sha) != SHA1_HEX_LEN or not all(c in "0123456789abcdef" for c in sha.lower()):
            return False
        sha = sha.lower()
        if self._loose.exists(sha):
            return True
        for _pack_path, idx in self._packs:
            if idx.lookup(sha) is not None:
                return True
        for _pack_path, cache in self._pack_caches.items():
            if sha in cache:
                return True
        return False

    def store(self, obj: GitObject) -> str:
        """Write object to loose ODB; return full 40-char hash. (Pack writing is Phase 2.)"""
        return self._loose.store(obj)

    def load(self, sha: str) -> GitObject:
        """Load object by full 40-char hash. From loose or pack. Raises ObjectNotFoundError."""
        raw = self._raw_load(sha)
        return self._raw_to_object(raw)

    def get_raw(self, sha: str) -> bytes:
        """Load raw object bytes (type size\\0content). For pack writing. Raises ObjectNotFoundError."""
        return self._raw_load(sha)

    def is_in_any_pack(self, sha: str) -> bool:
        """Return True if object exists in any pack index (for prune)."""
        sha = sha.lower()
        if len(sha) != SHA1_HEX_LEN:
            return False
        for _pack_path, idx in self._packs:
            if idx.lookup(sha) is not None:
                return True
        return False

    def prefix_lookup(self, prefix: str) -> List[str]:
        """Return list of full 40-char hashes that start with prefix (loose + packed)."""
        if len(prefix) < MIN_PREFIX_LEN:
            return []
        prefix = prefix.lower()
        if not all(c in "0123456789abcdef" for c in prefix):
            return []
        matches: List[str] = []
        matches.extend(self._loose.prefix_lookup(prefix))
        for pack_path, idx in self._packs:
            for name in idx.iter_shas(prefix):
                if name not in matches:
                    matches.append(name)
        for cache in self._pack_caches.values():
            for name in cache:
                if name.startswith(prefix) and name not in matches:
                    matches.append(name)
        return sorted(set(matches))

    def resolve_prefix(self, prefix: str) -> str:
        """Resolve prefix to full hash. Raises ObjectNotFoundError or AmbiguousRefError."""
        if len(prefix) == SHA1_HEX_LEN and all(c in "0123456789abcdef" for c in prefix.lower()):
            if self.exists(prefix):
                return prefix.lower()
            raise ObjectNotFoundError(f"object {prefix} not found")
        matches = self.prefix_lookup(prefix)
        if not matches:
            raise ObjectNotFoundError(f"object {prefix} not found")
        if len(matches) > 1:
            raise AmbiguousRefError(f"prefix '{prefix}' is ambiguous: {matches}")
        return matches[0]
