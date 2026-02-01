"""Git objects: GitObject, Blob, Tree, Commit with serialization/parsing. Phase F: PGP block preservation + verification stub."""

from __future__ import annotations

import zlib
from dataclasses import dataclass
from typing import List, Optional, Tuple

from .constants import MODE_DIR, MODE_FILE, MODE_FILE_EXECUTABLE, OBJ_BLOB, OBJ_COMMIT, OBJ_TAG, OBJ_TREE
from .util import sha1_hash


def _object_header(obj_type: str, content: bytes) -> bytes:
    """Header: '<type> <size>\\0'."""
    return f"{obj_type} {len(content)}\0".encode()


class GitObject:
    """Base git object (blob, tree, commit)."""

    def __init__(self, obj_type: str, content: bytes) -> None:
        self.type = obj_type
        self.content = content

    def hash_id(self) -> str:
        """SHA-1 of uncompressed representation: header + content."""
        header = _object_header(self.type, self.content)
        return sha1_hash(header + self.content)

    def serialize(self) -> bytes:
        """Compressed bytes for storage: zlib(header + content)."""
        header = _object_header(self.type, self.content)
        return zlib.compress(header + self.content)

    @classmethod
    def deserialize(cls, data: bytes) -> "GitObject":
        """Parse compressed object bytes into a GitObject (generic)."""
        raw = zlib.decompress(data)
        null_idx = raw.find(b"\0")
        if null_idx == -1:
            raise ValueError("invalid object: no null byte in header")
        header = raw[:null_idx].decode()
        content = raw[null_idx + 1 :]
        parts = header.split(" ", 1)
        if len(parts) != 2:
            raise ValueError("invalid object header")
        obj_type, _ = parts
        if obj_type == OBJ_BLOB:
            return Blob(content)
        if obj_type == OBJ_TREE:
            return Tree.from_content(content)
        if obj_type == OBJ_COMMIT:
            return Commit.from_content(content)
        if obj_type == OBJ_TAG:
            return Tag.from_content(content)
        return cls(obj_type, content)


class Blob(GitObject):
    """Blob object: raw file content."""

    def __init__(self, content: bytes) -> None:
        super().__init__(OBJ_BLOB, content)


@dataclass
class TreeEntry:
    """Single tree entry: mode, name, object hash (20-byte hex = 40 chars)."""
    mode: str
    name: str
    sha: str

    def to_bytes(self) -> bytes:
        """Format: b'{mode} {name}\\0' + 20-byte binary sha."""
        head = f"{self.mode} {self.name}\0".encode()
        return head + bytes.fromhex(self.sha)


class Tree(GitObject):
    """Tree object: sorted list of (mode, name, sha) entries."""

    def __init__(self, entries: List[Tuple[str, str, str]] | None = None) -> None:
        self.entries: List[Tuple[str, str, str]] = list(entries or [])
        content = self._serialize_entries()
        super().__init__(OBJ_TREE, content)

    def _serialize_entries(self) -> bytes:
        """Each entry: b'{mode} {name}\\0' + 20-byte sha. Sorted by name (trees first as 'tree' < 'blob' in git)."""
        parts: List[Tuple[str, str, str]] = []
        for mode, name, obj_hash in self.entries:
            parts.append((mode, name, obj_hash))
        # Git sorts: trees first (name with trailing slash conceptually), then by name
        parts.sort(key=lambda e: (not e[0].startswith("04"), e[1]))
        out = b""
        for mode, name, obj_hash in parts:
            out += f"{mode} {name}\0".encode()
            out += bytes.fromhex(obj_hash)
        return out

    def add_entry(self, mode: str, name: str, obj_hash: str) -> None:
        self.entries.append((mode, name, obj_hash))
        self.content = self._serialize_entries()

    @classmethod
    def from_content(cls, content: bytes) -> "Tree":
        tree = cls()
        i = 0
        while i < len(content):
            null_idx = content.find(b"\0", i)
            if null_idx == -1:
                break
            mode_name = content[i:null_idx].decode()
            sp = mode_name.find(" ")
            if sp == -1:
                break
            mode = mode_name[:sp]
            name = mode_name[sp + 1 :]
            sha_bin = content[null_idx + 1 : null_idx + 21]
            if len(sha_bin) != 20:
                break
            tree.entries.append((mode, name, sha_bin.hex()))
            i = null_idx + 21
        tree.content = content  # preserve exact bytes for correct hash
        return tree


@dataclass
class CommitParsed:
    """Parsed commit fields."""
    tree_hash: str
    parent_hashes: List[str]
    author: str
    committer: str
    author_ts: int
    author_tz: str
    committer_ts: int
    committer_tz: str
    message: str


class Commit(GitObject):
    """Commit object: tree, parents, author, committer, message."""

    def __init__(
        self,
        tree_hash: str,
        parent_hashes: List[str],
        author: str,
        committer: str,
        message: str,
        timestamp: int | None = None,
        tz_offset: str | None = None,
        gpgsig: Optional[str] = None,
    ) -> None:
        from .util import timestamp_with_tz
        if timestamp is not None and tz_offset is not None:
            ts, tz = timestamp, tz_offset
        else:
            ts, tz = timestamp_with_tz(timestamp)
        self.tree_hash = tree_hash
        self.parent_hashes = list(parent_hashes)
        self.author = author
        self.committer = committer
        self.message = message
        self._timestamp = ts
        self._tz_offset = tz_offset if tz_offset is not None else tz
        self.gpgsig = gpgsig
        content = self._serialize_commit()
        super().__init__(OBJ_COMMIT, content)

    def _serialize_commit(self) -> bytes:
        lines = [f"tree {self.tree_hash}"]
        for p in self.parent_hashes:
            lines.append(f"parent {p}")
        lines.append(f"author {self.author} {self._timestamp} {self._tz_offset}")
        lines.append(f"committer {self.committer} {self._timestamp} {self._tz_offset}")
        if self.gpgsig:
            # Multi-line gpgsig: first line after "gpgsig ", continuation lines prefixed with " "
            sig = self.gpgsig
            sig_lines = sig.split("\n")
            lines.append("gpgsig " + sig_lines[0])
            for rest in sig_lines[1:]:
                lines.append(" " + rest)
        lines.append("")
        # Git stores commit message with trailing newline
        msg = self.message if self.message.endswith("\n") else self.message + "\n"
        lines.append(msg)
        return "\n".join(lines).encode()

    @classmethod
    def from_content(cls, content: bytes) -> "Commit":
        """Parse commit content; preserve exact bytes for hash consistency. Preserve gpgsig header (Phase F)."""
        text = content.decode()
        lines = text.split("\n")
        tree_hash = ""
        parent_hashes: List[str] = []
        author = ""
        committer = ""
        author_ts = 0
        author_tz = "+0000"
        committer_ts = 0
        committer_tz = "+0000"
        gpgsig: Optional[str] = None
        message_start = 0
        i = 0
        while i < len(lines):
            line = lines[i]
            if line.startswith("tree "):
                tree_hash = line[5:]
            elif line.startswith("parent "):
                parent_hashes.append(line[7:])
            elif line.startswith("author "):
                rest = line[7:]
                parts = rest.rsplit(" ", 2)
                if len(parts) == 3:
                    author, author_ts, author_tz = parts[0], int(parts[1]), parts[2]
            elif line.startswith("committer "):
                rest = line[10:]
                parts = rest.rsplit(" ", 2)
                if len(parts) == 3:
                    committer, committer_ts, committer_tz = parts[0], int(parts[1]), parts[2]
            elif line.startswith("gpgsig "):
                # Multi-line gpgsig: first line after "gpgsig ", continuation lines prefixed with " "
                sig_parts = [line[7:]]
                i += 1
                while i < len(lines) and lines[i].startswith(" "):
                    sig_parts.append(lines[i][1:])
                    i += 1
                gpgsig = "\n".join(sig_parts)
                i -= 1  # so outer loop advances from same blank/msg
            elif line == "":
                message_start = i + 1
                break
            i += 1
        message = "\n".join(lines[message_start:])
        if message.endswith("\n"):
            message = message[:-1]
        commit = cls.__new__(cls)
        commit.tree_hash = tree_hash
        commit.parent_hashes = parent_hashes
        commit.author = author
        commit.committer = committer
        commit.message = message
        commit._timestamp = committer_ts
        commit._tz_offset = committer_tz
        commit.gpgsig = gpgsig
        commit.content = content  # keep exact bytes for correct hash
        commit.type = OBJ_COMMIT
        return commit


class Tag(GitObject):
    """Tag object: annotated tag with object, type, tag name, tagger, message."""

    def __init__(
        self,
        object_hash: str,
        object_type: str,
        tag_name: str,
        tagger: str,
        message: str,
        timestamp: int | None = None,
        tz_offset: str | None = None,
        gpg_signature: Optional[bytes] = None,
    ) -> None:
        from .util import timestamp_with_tz
        ts, tz = timestamp_with_tz(timestamp)
        self.object_hash = object_hash
        self.object_type = object_type
        self.tag_name = tag_name
        self.tagger = tagger
        self.message = message
        self._timestamp = ts
        self._tz_offset = tz_offset or tz
        self.gpg_signature = gpg_signature
        content = self._serialize_tag()
        super().__init__(OBJ_TAG, content)

    def _serialize_tag(self) -> bytes:
        lines = [
            f"object {self.object_hash}",
            f"type {self.object_type}",
            f"tag {self.tag_name}",
            f"tagger {self.tagger} {self._timestamp} {self._tz_offset}",
            "",
            self.message,
        ]
        out = "\n".join(lines).encode()
        if getattr(self, "gpg_signature", None):
            out += b"\n" + (self.gpg_signature if isinstance(self.gpg_signature, bytes) else self.gpg_signature.encode())
        return out

    @classmethod
    def from_content(cls, content: bytes) -> "Tag":
        """Parse tag content; preserve exact bytes for hash consistency. Preserve PGP block if present (Phase F)."""
        text = content.decode()
        lines = text.split("\n")
        object_hash = ""
        object_type = ""
        tag_name = ""
        tagger = ""
        timestamp = 0
        tz_offset = "+0000"
        message_start = 0
        for i, line in enumerate(lines):
            if line.startswith("object "):
                object_hash = line[7:]
            elif line.startswith("type "):
                object_type = line[5:]
            elif line.startswith("tag "):
                tag_name = line[4:]
            elif line.startswith("tagger "):
                rest = line[7:]
                parts = rest.rsplit(" ", 2)
                if len(parts) == 3:
                    tagger, timestamp, tz_offset = parts[0], int(parts[1]), parts[2]
            elif line == "":
                message_start = i + 1
                break
        rest_content = "\n".join(lines[message_start:])
        # Split message and optional PGP signature block (-----BEGIN PGP SIGNATURE----- ... -----END PGP SIGNATURE-----)
        gpg_signature: Optional[bytes] = None
        begin = b"-----BEGIN PGP SIGNATURE-----"
        idx_blank = content.find(b"\n\n")
        if idx_blank >= 0 and begin in content:
            msg_part = content[idx_blank + 2 :]
            idx = msg_part.find(begin)
            if idx != -1:
                message = msg_part[:idx].decode().rstrip("\n")
                gpg_signature = msg_part[idx:]
            else:
                message = rest_content
        else:
            message = rest_content
        tag = cls.__new__(cls)
        tag.object_hash = object_hash
        tag.object_type = object_type
        tag.tag_name = tag_name
        tag.tagger = tagger
        tag.message = message
        tag._timestamp = timestamp
        tag._tz_offset = tz_offset
        tag.gpg_signature = gpg_signature
        tag.content = content
        tag.type = OBJ_TAG
        return tag


def verify_signature(obj: GitObject) -> Tuple[bool, str]:
    """Stub: report whether object has a PGP/GPG signature; do not perform verification (Phase F).
    Returns (valid, message). For unsigned objects returns (True, ""). For signed objects returns
    (False, 'signature verification not implemented') until real verification is added."""
    if obj.type == OBJ_COMMIT:
        sig = getattr(obj, "gpgsig", None)
    elif obj.type == OBJ_TAG:
        sig = getattr(obj, "gpg_signature", None)
    else:
        return (True, "")
    if not sig:
        return (True, "")
    return (False, "signature verification not implemented")
