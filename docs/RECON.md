# PyGit — Repository Reconnaissance

This document answers, using actual repository inspection, the questions required for post-feature-completion upgrades (compat testing, demos, benchmarks, packaging, docs). All paths and module names are from the real codebase.

---

## A. How to run the test suite (exact command(s))

- **Full suite (discover all tests):**
  ```bash
  PYTHONPATH=. python -m unittest discover -q -s tests
  ```
  Or with verbose output:
  ```bash
  PYTHONPATH=. python -m unittest discover -v -s tests
  ```

- **Single test module:**
  ```bash
  PYTHONPATH=. python -m unittest tests.test_clone -v
  ```

- **Single test class or method:**
  ```bash
  PYTHONPATH=. python -m unittest tests.test_clone.TestCloneLocal.test_clone_creates_dest_and_checkout -v
  ```

- **Notes:**
  - The project uses **unittest** (no pytest). Tests live under `tests/`.
  - `PYTHONPATH=.` is required so that `pygit` resolves when tests import `from pygit ...`.
  - Some tests create temp dirs with `tempfile.mkdtemp()`; sandbox/permission issues may require running with full permissions for those tests.
  - HTTP clone tests start a local `HTTPServer`; they need no external network beyond localhost.
  - Expected result: **131 tests OK, 2 skipped** (skipped = system-git pack read when object not found on that system).

---

## B. Where the CLI entry point is and how commands are routed

- **Entry points:**
  - **Module:** `python -m pygit` → `pygit/__main__.py` runs `from .cli import main` and `sys.exit(main())`.
  - **Root wrapper:** `main.py` at repo root does `from pygit.cli import main` and `sys.exit(main())` (same as `python -m pygit`).

- **CLI implementation:** `pygit/cli.py`
  - **`main()`** (around line 724): builds an `argparse.ArgumentParser` with `prog="pygit"`, adds subparsers with `dest="command"`, then parses args and dispatches:
    ```python
    args = parser.parse_args()
    if not args.command:
        parser.print_help()
        return 0
    handlers = {
        "init": cmd_init,
        "add": cmd_add,
        "commit": cmd_commit,
        "config": cmd_config,
        "status": cmd_status,
        "reflog": cmd_reflog,
        "cherry-pick": cmd_cherry_pick,
        "branch": cmd_branch,
        "checkout": cmd_checkout,
        "log": cmd_log,
        "merge": cmd_merge,
        "diff": cmd_diff,
        "reset": cmd_reset,
        "rm": cmd_rm,
        "restore": cmd_restore,
        "show": cmd_show,
        "tag": cmd_tag,
        "merge-base": cmd_merge_base,
        "rev-list": cmd_rev_list,
        "show-ref": cmd_show_ref,
        "symbolic-ref": cmd_symbolic_ref,
        "update-ref": cmd_update_ref,
        "hash-object": cmd_hash_object,
        "cat-file": cmd_cat_file,
        "ls-tree": cmd_ls_tree,
        "write-tree": cmd_write_tree,
        "commit-tree": cmd_commit_tree,
        "rev-parse": cmd_rev_parse,
        "gc": cmd_gc,
        "repack": cmd_repack,
        "prune": cmd_prune,
        "remote": cmd_remote,
        "fetch": cmd_fetch,
        "push": cmd_push,
        "clone": cmd_clone,
        "stash": cmd_stash,
        "rebase": cmd_rebase,
        "compat": cmd_compat,
    }
    handler = handlers.get(args.command)
    ...
    return handler(args) or 0
    ```
  - Each **`cmd_*`** function takes `args: argparse.Namespace`, uses `_repo()` (which returns `Repository(Path.cwd())`), calls into `pygit.porcelain`, `pygit.plumbing`, `pygit.rebase`, `pygit.stash`, `compat.runner`, etc., and returns an exit code (0 = success, non-zero = failure).

- **`compat`** subcommand runs Git-vs-PyGit scenarios: `pygit compat <scenario>` (e.g. `S1_linear_commits`); see `compat/runner.py`, `compat/scenarios/`.

---

## C. Where objects are implemented (blob/tree/commit/tag serialization)

- **Module:** `pygit/objects.py`

- **Classes and behavior:**
  - **`GitObject`** — Base: `obj_type`, `content`; `hash_id()` (SHA-1 of `type size\0content`); `serialize()` (zlib compress); `deserialize(data)` routes to Blob/Tree/Commit/Tag by header type.
  - **`Blob`** — `content` bytes; no extra parsing.
  - **`Tree`** — `entries: List[Tuple[str, str, str]]` (mode, name, sha); `_serialize_entries()` / `from_content(content)`; preserves exact `content` for hash.
  - **`Commit`** — tree_hash, parent_hashes, author, committer, message, _timestamp, _tz_offset, optional **gpgsig**; `_serialize_commit()` / `from_content(content)`; preserves exact `content` for hash.
  - **`Tag`** — object_hash, object_type, tag_name, tagger, message, _timestamp, _tz_offset, optional **gpg_signature**; `_serialize_tag()` / `from_content(content)`; preserves exact `content` for hash.
  - **`verify_signature(obj)`** — Stub: returns `(bool, str)`; for signed objects returns `(False, "signature verification not implemented")`.

- **Constants:** Object type names (e.g. `OBJ_BLOB`, `OBJ_TREE`) come from `pygit/constants.py` and are used in `objects.py` and elsewhere.

---

## D. Where storage is implemented (loose objects, pack, idx v2, deltas)

- **Loose objects:**
  - **`pygit/odb.py`** — **`ObjectDB`**: loose only; `_object_path(sha)` → `.git/objects/<aa>/<bb...>`; `store(obj)`, `load(sha)`, `exists(sha)`, `prefix_lookup(prefix)`.

- **Unified store (loose + pack):**
  - **`pygit/objectstore.py`** — **`ObjectStore`**: holds `ObjectDB` (loose) and scans `.git/objects/pack/*.idx`; `_raw_load(sha)` (loose first, then pack via idx + pack file); `load(sha)` → `GitObject`; `exists(sha)`, `store(obj)` (writes loose); `prefix_lookup`, `resolve_prefix`; `rescan_packs()` (e.g. after gc/upload-pack). Uses **`pygit.idx.IdxV2`** and **`pygit.pack.read_pack_entries_with_bases`**.

- **Pack reading and deltas:**
  - **`pygit/pack.py`** — Pack format: `PACK` signature, version, num_objects; entry headers (type/size varint); **OBJ_REF_DELTA** (base sha) and **OBJ_OFS_DELTA** (base offset); **`_apply_delta(base_content, delta)`** for delta application; **`read_pack_entries_with_bases(pack_path, get_base_content=...)`** returns resolved entries; **`load_pack_object(...)`** for single object; **`read_pack_header`**, **`iter_pack_entries`**. Pack **writing** (no deltas): **`write_pack(path, object_ids, get_raw)`**; **`get_pack_sha_offsets(pack_path, get_base_content)`** for building idx from pack (used by gc and upload-pack).

- **Idx v2:**
  - **`pygit/idx.py`** — **`IdxV2`**: signature `\xfftOc`, version 2, fanout (256 × 4 bytes), names (20 bytes each), CRC, offsets (32-bit; large offsets in extension), trailer (pack sha + idx sha); **`lookup(sha)`**, **`iter_shas()`**, **`resolve_prefix(prefix, min_len)`**; **`write_idx(path, pack_sha, entries)`** for writing idx from list of `(sha_hex, entry_offset)`.

- **Repository usage:** `pygit/repo.py` — `Repository` has `self.odb = ObjectStore(self.objects_dir)`; all object access goes through `repo.odb` (load/store/exists), so packed objects are used automatically.

---

## E. Where refs / HEAD / packed-refs are implemented

- **Module:** `pygit/refs.py`

- **HEAD:**
  - **`_head_file(repo_git)`** → `.git/HEAD`.
  - **`read_head(repo_git)`** → `HeadState(kind="ref"|"detached", value=refname|commit_hash)` or None.
  - **`write_head_ref(repo_git, refname)`** — symbolic ref (e.g. `ref: refs/heads/main\n`).
  - **`write_head_detached(repo_git, commit_hash)`** — 40-hex content.

- **Loose refs:**
  - **`_ref_path(repo_git, refname)`** → `.git/<refname>` (e.g. `.git/refs/heads/main`).
  - **`resolve_ref(repo_git, refname, _packed=None)`** — reads loose ref file; if missing, uses **packed-refs** (see below); if value is 40-hex returns it, else resolves recursively (symbolic).
  - **`update_ref(repo_git, refname, new_hash)`** — write ref file.
  - **`update_ref_verify(repo_git, refname, new_hash, old_hash=None)`** — optional old value check; uses lock file (refname + `.lock`) then atomic replace.

- **Packed-refs:**
  - **`_read_packed_refs(repo_git)`** — reads `.git/packed-refs`; parses lines `sha refname`; skips blank, `#`, and `^` (peeled tag) lines; returns `dict[refname, sha]`.
  - **`resolve_ref`** uses this when the loose ref file does not exist.

- **Helpers:**
  - **`current_branch_name(repo_git)`**, **`head_commit(repo_git)`**, **`list_branches(repo_git)`** (loose refs/heads only), **`list_ref_names_with_prefix(repo_git, prefix)`** (loose + packed), **`list_tags(repo_git)`** (loose refs/tags only), **`validate_tag_name(name)`**.

- **Constants:** `HEAD_FILE`, `REF_HEADS_PREFIX`, `REF_TAGS_PREFIX`, etc. in `pygit/constants.py`.

---

## F. Where the index (DIRC v2) parsing/writing is implemented

- **Module:** `pygit/index.py`

- **Format:** Git binary index: **DIRC** signature (4 bytes), **version** 2 (4 bytes), **entry count** (4 bytes), then entries; **trailing SHA-1 checksum** (20 bytes) of everything before it (Phase B). Entry: ctime, mtime, dev, ino, mode, uid, gid, size, sha1 (20 bytes), flags, path (null-padded to multiple of 8). **Entry order** must be sorted by path (validated on read; `IndexCorruptError` if not).

- **Reading:**
  - **`_read_dirc(repo_git)`** — reads `.git/index` (path from **`_index_path(repo_git)`** → `.git/index`); verifies checksum when file length ≥ 32; validates path order; returns `Dict[path, {sha1, mode, size, mtime_ns, ...}]`.
  - **`load_index(repo_git)`** — if file starts with DIRC, uses `_read_dirc`; else treats as JSON and migrates to binary (writes binary, optionally backs up to `index.json.bak`), then returns entries.

- **Writing:**
  - **`_write_dirc(repo_git, entries)`** — writes binary DIRC v2 with entries sorted by path; appends SHA-1 checksum of body; uses **`write_bytes`** (atomic write via `util.write_bytes_atomic`).

- **Helpers:** **`save_index(repo_git, entries)`**, **`index_entry_for_file(file_path, blob_sha)`**, **`index_entries_unchanged(repo_root, path, entry)`** (size + mtime_ns cache; disabled if `PYGIT_PARANOID=1`).

- **Errors:** **`IndexChecksumError`**, **`IndexCorruptError`** from `pygit/errors.py`.

- **Constants:** `INDEX_FILENAME` in `pygit/constants.py`.

---

## G. Where transports / remotes are implemented

- **Transport abstraction and local:**
  - **`pygit/transport.py`** — **`is_local_path(url)`** (file:// or no scheme → True); **`_url_to_path(url)`**; **`LocalTransport`**: `list_refs()`, `get_object(sha)`, `has_object(sha)` using another repo’s `.git` (refs + ObjectStore). **`DumbHttpTransport`** is aliased to **`HttpDumbTransport`** from `http_dumb.py`.

- **Dumb HTTP:**
  - **`pygit/http_dumb.py`** — **`HttpDumbTransport`**: takes base URL (e.g. `http://host:port/repo`); **`list_refs()`** via GET `.git/HEAD`, `.git/packed-refs`, `.git/refs/heads/*`; **`get_object(sha)`** via GET `.git/objects/<aa>/<bb...>`; **`has_object(sha)`**. Used when URL is `http://` or `https://`.

- **Remote config and refspecs:**
  - **`pygit/remote.py`** — **`remote_add(repo, name, url, fetch_refspec=None)`**, **`remote_remove(repo, name)`**, **`remote_list(repo)`** → `[(name, fetch_url, push_url), ...]`; **`get_remote_url(repo, name)`**, **`get_remote_fetch_refspecs(repo, name)`**; **`Refspec`** dataclass and **`parse_refspec(refspec_str)`**, **`refspec_expand`**, **`refspec_expand_src_list`**. Remote-tracking refs live under `refs/remotes/<name>/*`.

- **Fetch / push / clone:**
  - **`pygit/fetch.py`** — **`fetch(repo, remote_name, refspecs=None)`**: gets URL via `get_remote_url`; chooses **LocalTransport** or **HttpDumbTransport** via **`is_local_path(url)`** and URL scheme; `transport.list_refs()`, refspec expansion, `_reachable_from_tips`, then copies missing objects and **`update_ref`** for remote-tracking refs.
  - **`pygit/push.py`** — Push to local remote (reachable objects, update ref; non-FF refused unless `--force`).
  - **`pygit/clone.py`** — **`clone(src, dest)`**: init dest, add origin remote, fetch, checkout default branch; supports local path and http(s) URL (same transport selection as fetch).

- **Smart protocol (minimal):** **`pygit/upload_pack.py`** (TCP upload-pack client) and **`pygit/pkt_line.py`** exist but are not wired into the fetch CLI; they are used by tests and programmatic `fetch_via_upload_pack_tcp`.

---

## H. What helper utilities exist for creating temp repos in tests

- **No shared test-runner module:** Tests do not use a single `tests/helpers.py` or `tests/conftest.py`. Each test file that needs a repo creates its own temp dir and repo.

- **Common pattern:**
  - **`tempfile.mkdtemp(prefix="pygit_<feature>_")`** → get a `Path` or `str` for the temp directory.
  - **`Repository(str(path))`** from `pygit.repo.Repository`.
  - **`repo.init()`** to create `.git`, refs, objects, HEAD, index, config.
  - Optionally create files, then **`add_path(repo, path)`**, **`commit(repo, message, author)`** from `pygit.porcelain`.

- **Examples:**
  - **`tests/test_tags.py`** — **`make_temp_repo_with_commit()`**: `tempfile.mkdtemp(prefix="pygit_tags_")`, manually creates `.git/objects`, `.git/refs/heads`, `.git/refs/tags`, then `Repository(str(p))`, creates blob/tree/commit, writes `.git/HEAD` and `.git/refs/heads/main`; returns `(path, repo, commit_sha)`.
  - **`tests/test_fetch.py`** — `setUp`: `mkdtemp(prefix="pygit_fetch_")`, `(tmp/"A").mkdir()`, `(tmp/"B").mkdir()`, `Repository(str(tmp/"A")).init()`, `Repository(str(tmp/"B")).init()`.
  - **`tests/test_clone.py`** — `mkdtemp(prefix="pygit_clone_")`, `(tmp/"src").mkdir()`, `Repository(str(tmp/"src")).init()`; for HTTP: `mkdtemp(prefix="pygit_clone_http_")`, `(tmp/"repo").mkdir()`, `Repository(str(tmp/"repo")).init()`.
  - **`tests/test_clone.py`** — **`_start_http_server(serve_dir, host="127.0.0.1")`**: `HTTPServer` with `SimpleHTTPRequestHandler` and `directory=serve_dir`, bound to port 0; started in a daemon thread; returns `(server, port)`.

- **Takeaway for compat/demos:** New code can either (1) call `tempfile.mkdtemp()` and `Repository(...).init()` (and optionally `add_path`/`commit`), or (2) introduce a small shared helper under e.g. `tests/helpers.py` or `compat/helpers.py` that creates an isolated temp repo and returns path + repo, without changing existing test files.

---

## I. Current repo structure (top-level tree summary)

```
.
├── .gitignore
├── main.py                 # CLI wrapper: from pygit.cli import main; sys.exit(main())
├── README.md
├── USAGE.md
├── docs/
│   ├── RECON.md            # This file (single source of truth: repo reconnaissance)
│   ├── ARCHITECTURE.md     # High-level architecture, layers, object model
│   ├── CHECKLIST.md        # Post-feature completion checklist
│   └── INDEX.md            # Documentation index
├── compat/                 # Git vs PyGit compat harness
│   ├── backends.py         # GitBackend, PyGitBackend
│   ├── compare.py         # compare_refs, compare_rev_list, compare_tree_maps, compare_clean
│   ├── ops.py             # run_op, op_from_spec
│   ├── runner.py          # run_scenario, load_scenario
│   └── scenarios/         # S1_linear_commits, S2_branches, S3_tags, ...
├── demo/                   # Demo harness
│   ├── run.py             # demo_basic_workflow, demo_branches_and_merge, demo_clone_local, demo_tags
│   └── README.md
├── bench/                  # Benchmarks and profiling
│   ├── run.py             # bench_n_commits, bench_status_many_files, bench_clone_local
│   └── README.md
├── pyproject.toml          # setuptools, [project], entry point pygit = pygit.cli:main
├── pygit/
│   ├── __init__.py
│   ├── __main__.py         # python -m pygit → cli.main()
│   ├── cli.py              # argparse + cmd_* handlers
│   ├── clone.py            # clone(src, dest)
│   ├── config.py           # read_config, write_config, get_user_identity, etc.
│   ├── constants.py       # OBJ_*, REF_*, INDEX_FILENAME, etc.
│   ├── errors.py           # PygitError, NotARepositoryError, ObjectNotFoundError, ...
│   ├── fetch.py            # fetch(repo, remote_name, refspecs)
│   ├── gc.py               # gc, repack, prune, reachable_objects
│   ├── graph.py            # iter_commits, get_commit_parents, is_ancestor
│   ├── http_dumb.py        # HttpDumbTransport
│   ├── idx.py              # IdxV2, write_idx
│   ├── ignore.py           # load_ignore_patterns
│   ├── index.py            # load_index, save_index, _read_dirc, _write_dirc
│   ├── objects.py          # GitObject, Blob, Tree, Commit, Tag, verify_signature
│   ├── objectstore.py      # ObjectStore (loose + pack)
│   ├── odb.py              # ObjectDB (loose only)
│   ├── pack.py             # read_pack_*, write_pack, get_pack_sha_offsets, _apply_delta
│   ├── pkt_line.py         # pkt-line encode/decode (smart protocol)
│   ├── plumbing.py         # rev_parse, cat_file_*, ls_tree, write_tree, commit_tree, ...
│   ├── porcelain.py        # add_path, commit, status, log, merge, cherry_pick, ...
│   ├── push.py             # push(repo, remote, src, dst, force)
│   ├── rebase.py           # rebase, rebase_continue, rebase_abort
│   ├── reflog.py           # append_reflog, read_reflog
│   ├── refs.py             # read_head, write_head_*, resolve_ref, update_ref, packed-refs
│   ├── remote.py           # remote_add/remove/list, get_remote_url, refspec parsing
│   ├── repo.py             # Repository, init, load_index, store_object, list_tree_paths, ...
│   ├── stash.py            # stash_save, stash_list, stash_apply, stash_pop
│   ├── transport.py        # LocalTransport, is_local_path
│   ├── upload_pack.py      # fetch_via_upload_pack_tcp (TCP smart client)
│   └── util.py             # sha1_hash, write_bytes_atomic, normalize_path, is_executable, ...
└── tests/
    ├── __init__.py
    ├── .gitignore           # pygit_*, __pycache__
    ├── test_cherry_pick.py
    ├── test_clone.py
    ├── test_compat.py
    ├── test_config.py
    ├── test_fetch.py
    ├── test_gc.py
    ├── test_graph_tools.py
    ├── test_ignore.py
    ├── test_index.py
    ├── test_merge_3way.py
    ├── test_merge_ff.py
    ├── test_objects.py
    ├── test_pack_read.py
    ├── test_push.py
    ├── test_rebase.py
    ├── test_reflog.py
    ├── test_refs_plumbing.py
    ├── test_refs.py
    ├── test_remote.py
    ├── test_revparse.py
    ├── test_show_restore.py
    ├── test_signature.py
    ├── test_stash.py
    ├── test_tags.py
    └── test_upload_pack.py
```

See **docs/INDEX.md** for the documentation index; **docs/ARCHITECTURE.md** for high-level architecture.

---

## J. Implementation phases (reference)

| Phase | Where implemented / extended |
|-------|------------------------------|
| A (dumb HTTP) | `http_dumb.py`; fetch/clone wired for http(s) URLs. |
| B (index) | `index.py`: checksum on write/read; validate/sort entries; skip unknown extensions in `_read_dirc`; `IndexChecksumError`, `IndexCorruptError`. |
| C (stash) | `pygit/stash.py`; CLI `stash` with save/list/apply/pop; refs/stash, reflog. |
| D (rebase) | `pygit/rebase.py`; reuse cherry_pick + state dir; CLI `rebase`, `rebase --continue`, `rebase --abort`. |
| E (smart) | `pygit/upload_pack.py`, `pygit/pkt_line.py`; pkt-line + want/have + receive pack; `fetch_via_upload_pack_tcp` (not wired into fetch CLI). |
| F (signed) | `pygit/objects.py`: preserve PGP blocks in tag/commit parse/serialize; `verify_signature` stub. |

**Merge / cherry-pick / reset (for reuse):** Merge in `porcelain.py` (fast-forward or 3-way, merge_base); cherry-pick and reset in `porcelain.py`; state under `.git/pygit/` (CHERRY_PICK_HEAD, ORIG_HEAD, etc.). Refs in `refs.py`.

---

*This recon was produced by inspecting the repository. Use it as the single source of truth for integrating compat, demos, benchmarks, packaging, and docs.*
