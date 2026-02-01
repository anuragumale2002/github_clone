"""Object database: store/load by hash, prefix lookup."""

from __future__ import annotations

from pathlib import Path
from typing import List, Optional

from .constants import MIN_PREFIX_LEN, SHA1_HEX_LEN
from .errors import AmbiguousRefError, ObjectNotFoundError
from .objects import GitObject
from .util import write_bytes


class ObjectDB:
    """Loose object storage under .git/objects/<aa>/<bb...>."""

    def __init__(self, objects_dir: Path) -> None:
        self.objects_dir = Path(objects_dir)

    def _object_path(self, sha: str) -> Path:
        """Path to loose object file. sha must be full 40-char hex."""
        if len(sha) != SHA1_HEX_LEN or not all(c in "0123456789abcdef" for c in sha):
            raise ValueError(f"invalid full sha: {sha}")
        return self.objects_dir / sha[:2] / sha[2:]

    def exists(self, sha: str) -> bool:
        """Return True if object exists (sha must be full 40-char)."""
        return self._object_path(sha).exists()

    def store(self, obj: GitObject) -> str:
        """Write object to ODB; return full 40-char hash."""
        sha = obj.hash_id()
        path = self._object_path(sha)
        if path.exists():
            return sha
        path.parent.mkdir(parents=True, exist_ok=True)
        write_bytes(path, obj.serialize())
        return sha

    def load(self, sha: str) -> GitObject:
        """Load object by full 40-char hash. Raises ObjectNotFoundError."""
        path = self._object_path(sha)
        if not path.exists():
            raise ObjectNotFoundError(f"object {sha} not found")
        import zlib
        raw = path.read_bytes()
        data = zlib.decompress(raw)
        null_idx = data.find(b"\0")
        if null_idx == -1:
            raise ValueError("invalid object")
        return GitObject.deserialize(raw)

    def prefix_lookup(self, prefix: str) -> List[str]:
        """Return list of full 40-char hashes that start with prefix. Prefix min 4 chars."""
        if len(prefix) < MIN_PREFIX_LEN:
            return []
        prefix = prefix.lower()
        if not all(c in "0123456789abcdef" for c in prefix):
            return []
        if len(prefix) == SHA1_HEX_LEN:
            path = self._object_path(prefix)
            return [prefix] if path.exists() else []
        # List objects in prefix dir
        pre_dir = self.objects_dir / prefix[:2]
        if not pre_dir.is_dir():
            return []
        matches = []
        suffix = prefix[2:]
        for f in pre_dir.iterdir():
            if f.is_file() and (f.name.startswith(suffix) if suffix else True):
                full_sha = prefix[:2] + f.name
                if len(full_sha) == SHA1_HEX_LEN and full_sha.startswith(prefix):
                    matches.append(full_sha)
        return sorted(matches)

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
