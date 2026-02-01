"""Branch and merge: init, commit, create branch b1, commit on b1, checkout main, merge b1."""

OPS = [
    {"op": "init"},
    {"op": "write", "path": "a", "content": "a\n"},
    {"op": "add", "paths": ["a"]},
    {"op": "commit", "message": "first"},
    {"op": "branch", "name": "b1"},
    {"op": "checkout", "target": "b1"},
    {"op": "write", "path": "b", "content": "b\n"},
    {"op": "add", "paths": ["b"]},
    {"op": "commit", "message": "on b1"},
    {"op": "checkout", "target": "main"},
    {"op": "merge", "name": "b1"},
]
