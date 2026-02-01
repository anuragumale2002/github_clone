"""Multiple branches: init, commit, create A and B, commit on A, commit on B."""

OPS = [
    {"op": "init"},
    {"op": "write", "path": "a", "content": "a\n"},
    {"op": "add", "paths": ["a"]},
    {"op": "commit", "message": "first"},
    {"op": "branch", "name": "A"},
    {"op": "branch", "name": "B"},
    {"op": "checkout", "target": "A"},
    {"op": "write", "path": "x", "content": "x\n"},
    {"op": "add", "paths": ["x"]},
    {"op": "commit", "message": "on A"},
    {"op": "checkout", "target": "B"},
    {"op": "write", "path": "y", "content": "y\n"},
    {"op": "add", "paths": ["y"]},
    {"op": "commit", "message": "on B"},
]
