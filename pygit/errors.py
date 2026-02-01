"""Custom exceptions for pygit."""

from __future__ import annotations


class PygitError(Exception):
    """Base exception for pygit."""

    pass


class NotARepositoryError(PygitError):
    """Raised when not in a git repository."""

    pass


class ObjectNotFoundError(PygitError):
    """Raised when an object is not found in the ODB."""

    pass


class AmbiguousRefError(PygitError):
    """Raised when a rev-parse prefix matches multiple objects."""

    pass


class InvalidRefError(PygitError):
    """Raised when a ref name or rev cannot be resolved."""

    pass


class PathOutsideRepoError(PygitError):
    """Raised when a path would escape the repository root."""

    pass


class InvalidConfigKeyError(PygitError):
    """Raised when a config key is invalid (e.g. not section.option)."""

    pass


class PackError(PygitError):
    """Raised when pack file is invalid or unsupported."""

    pass


class IdxError(PygitError):
    """Raised when pack index file is invalid or unsupported."""

    pass


class IndexChecksumError(PygitError):
    """Raised when index file trailing SHA-1 checksum does not match contents."""

    pass


class IndexCorruptError(PygitError):
    """Raised when index file is corrupt or entries are not sorted by path."""

    pass
