"""Restore: init, commit, modify file, restore working tree."""

OPS = [
    {"op": "init"},
    {"op": "write", "path": "a", "content": "a\n"},
    {"op": "add", "paths": ["a"]},
    {"op": "commit", "message": "first"},
    {"op": "write", "path": "a", "content": "a modified\n"},
    {"op": "restore", "paths": ["a"]},
]
