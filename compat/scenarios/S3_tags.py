"""Tags: init, commit, lightweight tag, second commit, annotated tag."""

OPS = [
    {"op": "init"},
    {"op": "write", "path": "a", "content": "a\n"},
    {"op": "add", "paths": ["a"]},
    {"op": "commit", "message": "first"},
    {"op": "tag", "name": "t1"},
    {"op": "write", "path": "b", "content": "b\n"},
    {"op": "add", "paths": ["b"]},
    {"op": "commit", "message": "second"},
    {"op": "tag", "name": "t2", "annotated": True, "message": "annotated t2"},
]
