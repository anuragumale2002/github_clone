"""Reset: init, commit, add new file, reset --mixed, then reset --hard."""

OPS = [
    {"op": "init"},
    {"op": "write", "path": "a", "content": "a\n"},
    {"op": "add", "paths": ["a"]},
    {"op": "commit", "message": "first"},
    {"op": "write", "path": "b", "content": "b\n"},
    {"op": "add", "paths": ["b"]},
    {"op": "reset", "mode": "mixed", "commit": "HEAD"},
    {"op": "status"},
    {"op": "reset", "mode": "hard", "commit": "HEAD"},
]
