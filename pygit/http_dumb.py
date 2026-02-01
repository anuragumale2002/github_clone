"""Dumb HTTP transport: GET .git/HEAD, packed-refs, objects (Phase A)."""

from __future__ import annotations

import re
import zlib
from typing import List, Tuple
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from .constants import REF_HEADS_PREFIX, SHA1_HEX_LEN
from .errors import PygitError

# Timeout for HTTP requests (seconds)
HTTP_TIMEOUT = 30

# Regex for 40-char hex (for ref parsing)
_HEX_SHA_RE = re.compile(r"\A[0-9a-fA-F]{40}\Z")


def _is_hex_sha(s: str) -> bool:
    return len(s) == SHA1_HEX_LEN and bool(_HEX_SHA_RE.match(s))


def _get(url: str, timeout: float = HTTP_TIMEOUT) -> bytes | None:
    """GET url; return response body or None on 404/error. Follows redirects."""
    try:
        req = Request(url, method="GET")
        with urlopen(req, timeout=timeout) as resp:
            return resp.read()
    except HTTPError as e:
        if e.code == 404:
            return None
        raise PygitError(f"HTTP {e.code}: {url}") from e
    except URLError as e:
        raise PygitError(f"HTTP request failed: {url}: {e.reason}") from e
    except OSError as e:
        raise PygitError(f"HTTP request failed: {url}: {e}") from e


def _parse_packed_refs(data: bytes) -> dict[str, str]:
    """Parse packed-refs content; return refname -> sha."""
    result: dict[str, str] = {}
    for line in data.decode("utf-8", errors="replace").splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        if line.startswith("^"):
            continue
        parts = line.split(None, 1)
        if len(parts) < 2:
            continue
        sha, refname = parts[0], parts[1]
        if _is_hex_sha(sha):
            result[refname] = sha.lower()
    return result


class HttpDumbTransport:
    """Dumb HTTP transport: read refs and objects via GET .git/HEAD, packed-refs, objects/aa/bb."""

    def __init__(self, base_url: str, timeout: float = HTTP_TIMEOUT) -> None:
        self.base_url = base_url.rstrip("/")
        self._git_prefix = f"{self.base_url}/.git/"
        self._timeout = timeout
        self._refs_cache: List[Tuple[str, str]] | None = None

    def _url(self, path: str) -> str:
        """Build full URL for a path under .git/ (path should not start with /)."""
        return self._git_prefix + path.lstrip("/")

    def list_refs(self) -> List[Tuple[str, str]]:
        """Return [(refname, sha), ...]. Uses HEAD + packed-refs; falls back to GET refs/heads/<branch>."""
        if self._refs_cache is not None:
            return self._refs_cache
        refs: dict[str, str] = {}

        # packed-refs
        packed = _get(self._url("packed-refs"), timeout=self._timeout)
        if packed:
            refs.update(_parse_packed_refs(packed))

        # HEAD
        head_data = _get(self._url("HEAD"), timeout=self._timeout)
        if head_data:
            head_str = head_data.decode("utf-8", errors="replace").strip()
            if head_str.startswith("ref: "):
                refname = head_str[5:].strip()
                if refname not in refs:
                    # Try GET .git/refs/heads/<branch> etc.
                    ref_url = self._url(refname)
                    ref_body = _get(ref_url, timeout=self._timeout)
                    if ref_body:
                        sha = ref_body.decode("utf-8", errors="replace").strip()
                        if _is_hex_sha(sha):
                            refs[refname] = sha.lower()
            elif _is_hex_sha(head_str):
                refs["HEAD"] = head_str.lower()

        result = [(name, sha) for name, sha in sorted(refs.items())]
        self._refs_cache = result
        return result

    def get_object(self, sha: str) -> bytes:
        """Return raw object bytes (type size\\0content). GET .git/objects/aa/bb...; decompress."""
        sha = sha.lower()
        if len(sha) != SHA1_HEX_LEN or not _is_hex_sha(sha):
            raise PygitError(f"invalid object hash: {sha}")
        path = f"objects/{sha[:2]}/{sha[2:]}"
        data = _get(self._url(path), timeout=self._timeout)
        if not data:
            raise PygitError(f"object not found: {sha}")
        try:
            return zlib.decompress(data)
        except zlib.error as e:
            raise PygitError(f"invalid object data: {sha}: {e}") from e

    def has_object(self, sha: str) -> bool:
        """Return True if object exists (HEAD request or GET and discard)."""
        sha = sha.lower()
        if len(sha) != SHA1_HEX_LEN:
            return False
        path = f"objects/{sha[:2]}/{sha[2:]}"
        data = _get(self._url(path), timeout=self._timeout)
        return data is not None
