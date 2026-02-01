"""Transport abstraction: local path (Phase 4). Dumb HTTP later (Phase 6)."""

from __future__ import annotations

from pathlib import Path
from typing import List, Tuple

from .constants import REF_HEADS_PREFIX, REF_TAGS_PREFIX
from .objectstore import ObjectStore
from .refs import list_ref_names_with_prefix, resolve_ref


def is_local_path(url: str) -> bool:
    """Return True if url is a local path (directory)."""
    u = url.strip()
    if u.startswith("file://"):
        return True
    if not u.startswith("http://") and not u.startswith("https://") and not u.startswith("git@"):
        return True
    return False


def _url_to_path(url: str) -> Path:
    """Convert URL to local Path. file:///path -> /path; else path as-is."""
    u = url.strip()
    if u.startswith("file://"):
        return Path(u[7:].lstrip("/"))
    return Path(u)


class LocalTransport:
    """Local filesystem transport: read refs and objects from another repo."""

    def __init__(self, path_or_url: str | Path) -> None:
        self.path = Path(path_or_url).resolve()
        if (self.path / ".git").is_dir():
            self.git_dir = self.path / ".git"
        else:
            self.git_dir = self.path
        self.objects_dir = self.git_dir / "objects"
        self._store = ObjectStore(self.objects_dir)

    def list_refs(self) -> List[Tuple[str, str]]:
        """Return [(refname, sha), ...] for refs/heads/* and refs/tags/* (resolved)."""
        result: List[Tuple[str, str]] = []
        for prefix in (REF_HEADS_PREFIX, REF_TAGS_PREFIX):
            for refname in list_ref_names_with_prefix(self.git_dir, prefix):
                sha = resolve_ref(self.git_dir, refname)
                if sha:
                    result.append((refname, sha))
        return result

    def get_object(self, sha: str) -> bytes:
        """Return raw object bytes (type size\\0content). Raises ObjectNotFoundError."""
        return self._store.get_raw(sha)

    def has_object(self, sha: str) -> bool:
        """Return True if object exists in remote."""
        return self._store.exists(sha)


# Dumb HTTP transport: implemented in http_dumb.py for clone/fetch over http(s).
from .http_dumb import HttpDumbTransport as DumbHttpTransport
