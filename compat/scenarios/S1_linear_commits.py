"""Linear history: init, add files, three commits."""

OPS = [
    {"op": "init"},
    {"op": "write", "path": "a", "content": "a\n"},
    {"op": "add", "paths": ["a"]},
    {"op": "commit", "message": "first"},
    {"op": "write", "path": "b", "content": "b\n"},
    {"op": "add", "paths": ["b"]},
    {"op": "commit", "message": "second"},
    {"op": "write", "path": "c", "content": "c\n"},
    {"op": "add", "paths": ["c"]},
    {"op": "commit", "message": "third"},
]
