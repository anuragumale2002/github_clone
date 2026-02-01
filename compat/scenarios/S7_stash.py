"""Stash: init, commit, modify, stash save, stash list, stash apply."""

OPS = [
    {"op": "init"},
    {"op": "write", "path": "a", "content": "a\n"},
    {"op": "add", "paths": ["a"]},
    {"op": "commit", "message": "first"},
    {"op": "write", "path": "a", "content": "a modified\n"},
    {"op": "stash_save", "message": "wip"},
    {"op": "stash_list"},
    {"op": "stash_apply"},
]
