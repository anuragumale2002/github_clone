# PyGit Architecture

High-level overview of the PyGit codebase and data flow.

---

## Layers

```
┌─────────────────────────────────────────────────────────────────┐
│  CLI (cli.py)                                                    │
│  argparse → cmd_init, cmd_add, cmd_commit, cmd_status, ...       │
└─────────────────────────────────────────────────────────────────┘
                                  │
┌─────────────────────────────────────────────────────────────────┐
│  Porcelain (porcelain.py)                                        │
│  add_path, commit, status, log, merge, checkout_branch, ...       │
└─────────────────────────────────────────────────────────────────┘
                                  │
┌─────────────────────────────────────────────────────────────────┐
│  Plumbing (plumbing.py) + Helpers                                │
│  rev_parse, ls_tree, write_tree, commit_tree, merge_base, ...     │
│  graph.py, refs.py, reflog.py, config.py, ignore.py              │
└─────────────────────────────────────────────────────────────────┘
                                  │
┌─────────────────────────────────────────────────────────────────┐
│  Repository (repo.py)                                            │
│  init, load_index, save_index, store_object, load_object,        │
│  create_tree_from_index, list_tree_paths, ...                    │
└─────────────────────────────────────────────────────────────────┘
                                  │
┌──────────────────┬──────────────────┬────────────────────────────┐
│  index.py        │  refs.py         │  Object store               │
│  DIRC v2 index   │  HEAD, refs/     │  odb.py (loose)             │
│  load/save       │  packed-refs     │  objectstore.py (loose+pack)│
│                  │                  │  pack.py, idx.py            │
└──────────────────┴──────────────────┴────────────────────────────┘
                                  │
┌─────────────────────────────────────────────────────────────────┐
│  objects.py                                                      │
│  Blob, Tree, Commit, Tag — serialize/deserialize, SHA1           │
└─────────────────────────────────────────────────────────────────┘
```

---

## Object model

Git objects (blob, tree, commit, tag) live under `.git/objects/` (loose: `aa/bb...`; packed: `.git/objects/pack/*.pack` + `.idx`). PyGit uses:

- **objects.py**: `GitObject`, `Blob`, `Tree`, `Commit`, `Tag` with `serialize` / `from_content` and SHA1 from `type size\0content`.
- **odb.py**: Loose object DB (store, load, exists).
- **objectstore.py**: Unified interface over loose + pack (load, exists, store to loose).
- **pack.py**: Read packfiles (OFS-delta, REF-delta); write pack (no deltas).
- **idx.py**: Idx v2 format for pack indices.

---

## Clone / fetch flow

```
clone(src, dest)
    │
    ├─ init(dest)
    ├─ remote_add(dest, "origin", src)
    ├─ fetch(dest, "origin")  ──► transport.list_refs() → get_object() for want list
    │       │                     LocalTransport or HttpDumbTransport (http(s))
    │       └─ update refs/remotes/origin/*, write refs/heads/<default>, checkout
    └─ checkout_branch(dest, default_branch)
```

---

## Key files

| Area        | Files |
|------------|--------|
| CLI        | `cli.py`, `__main__.py` |
| Porcelain  | `porcelain.py` |
| Plumbing   | `plumbing.py`, `graph.py`, `refs.py`, `reflog.py` |
| Repo       | `repo.py`, `config.py`, `ignore.py`, `index.py` |
| Objects    | `objects.py`, `odb.py`, `objectstore.py`, `pack.py`, `idx.py` |
| Transport  | `transport.py`, `http_dumb.py`, `fetch.py`, `push.py`, `clone.py` |

See **docs/RECON.md** for detailed reconnaissance (tests, CLI routing, storage, refs, index, transports).
