"""Constants for pygit: default branch, file modes, ref paths."""

from __future__ import annotations

# Default branch name (git uses 'master', modern default is 'main')
DEFAULT_BRANCH = "main"

# Git file modes
MODE_FILE = "100644"
MODE_FILE_EXECUTABLE = "100755"
MODE_DIR = "040000"

# Ref paths under .git
REF_HEADS_PREFIX = "refs/heads/"
REF_TAGS_PREFIX = "refs/tags/"
REF_REMOTES_PREFIX = "refs/remotes/"
HEAD_FILE = "HEAD"

# Object types
OBJ_BLOB = "blob"
OBJ_TREE = "tree"
OBJ_COMMIT = "commit"
OBJ_TAG = "tag"

# Index
INDEX_VERSION = 1
INDEX_FILENAME = "index"

# Minimum prefix length for rev-parse (git uses 4)
MIN_PREFIX_LEN = 4

# SHA-1 hex length
SHA1_HEX_LEN = 40
