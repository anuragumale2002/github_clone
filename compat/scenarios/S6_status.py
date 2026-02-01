"""Status: init, commit, add untracked and modified, run status."""

OPS = [
    {"op": "init"},
    {"op": "write", "path": "a", "content": "a\n"},
    {"op": "add", "paths": ["a"]},
    {"op": "commit", "message": "first"},
    {"op": "write", "path": "b", "content": "untracked\n"},
    {"op": "write", "path": "a", "content": "a modified\n"},
    {"op": "status"},
]
