# PyGit — A minimal Git clone

A minimal Git implementation in Python. Uses the same `.git` layout as Git: loose objects in `.git/objects`, binary index (DIRC v2) for `.git/index`, and standard refs. Supports init, add, commit, merge, fetch, push, and clone so you can use it alongside Git or on its own.

**Requirements:** Python 3.11+, macOS/Linux, standard library only.

---

## Install

From the project root (recommended for development):

```bash
pip install -e .
```

Then run PyGit from anywhere:

```bash
pygit init
pygit add .
pygit commit -m "First commit"
```

Without installing, from the project root:

```bash
PYTHONPATH=. python -m pygit <command> ...
```

---

## How to use

### Basic workflow

```bash
# Create a repo
pygit init

# Stage and commit
pygit add file.txt
pygit commit -m "First commit"

# Check status and log
pygit status
pygit log -n 5
```

### Push to a local backup (not GitHub)

PyGit **push** only supports a **local path** or **file://** URL. It does **not** support pushing to GitHub (SSH or HTTPS). Use real Git for that: `git push origin main`.

To push to another folder on your machine:

1. **Create the backup repo:**  
   `mkdir backup_folder && cd backup_folder && pygit init`

2. **In your project:** add the backup as a remote and push:
   ```bash
   pygit remote add backup /path/to/backup_folder
   pygit push backup
   ```

3. **In the backup folder:** push only updates `.git` (refs and objects). To see files in the backup folder, run:
   ```bash
   cd /path/to/backup_folder
   pygit checkout main
   ```

See **USAGE.md** for a full step-by-step example and why you must run **checkout** in the backup repo to see the files.

### Pushing to GitHub

Use Git (not PyGit) for push/pull to GitHub. In the same repo:

```bash
git remote add origin https://github.com/USER/REPO.git
git push -u origin main
```

PyGit and Git share the same `.git` directory, so commits you make with PyGit are pushed by Git.

---

## Limitations

| Feature | PyGit | Use instead |
|--------|--------|-------------|
| Push to GitHub (SSH/HTTPS) | Not supported | `git push origin main` |
| Push to local path / file:// | Supported | `pygit push backup` |
| Working directory after push | Not updated automatically | Run `pygit checkout main` in the remote repo |

**More detail:** Ignore uses only repo excludes (no global/user); `**` is approximated. Tags: name validation (no space, `..`, `/`, etc.); PGP is preserved but **signature verification is a stub** (no GPG/crypto). Merge is 3-way with manual conflict resolution (markers in files). Index is DIRC v2 only (no extensions). Config is `.git/config` only; keys are `section.option`, case-sensitive. **No hooks.** Transport: local + file://; dumb HTTP (http/https); smart = minimal upload-pack TCP client only (no receive-pack, no fetch CLI integration, no SSH). Remotes: `refs/remotes/<name>/*`; branch/tag listing is loose refs only (resolve_ref uses packed-refs).

### Future work / Not implemented

- **Smart protocol:** Full fetch integration, receive-pack, SSH.
- **Signature verification:** Real GPG/PGP (verify_signature is a stub).
- **revert;** index extensions; global/user ignore; hooks.

---

## Project structure and folders

All of the following are run from the **project root** (the directory containing `pygit/`, `tests/`, etc.). Use `PYTHONPATH=.` when running Python modules so that `pygit`, `compat`, `demo`, and `bench` resolve.

| Folder | What it contains | How to use it |
|--------|------------------|---------------|
| **pygit/** | The PyGit implementation: CLI (`cli.py`), porcelain (`porcelain.py`), plumbing (`plumbing.py`), objects, refs, index, fetch/push/clone, stash, rebase, etc. | **CLI:** `pygit <cmd>` (after `pip install -e .`) or `PYTHONPATH=. python -m pygit <cmd>`. **From code:** `from pygit.porcelain import commit, add_path` etc.; use `Repository(path)` from `pygit.repo`. |
| **tests/** | Unit tests for PyGit (`test_*.py`). Covers objects, refs, index, merge, fetch, clone, compat, etc. | **Run all:** `PYTHONPATH=. python -m unittest discover -q -s tests`. **One file:** `PYTHONPATH=. python -m unittest tests.test_clone -v`. Tests create temp `.git` dirs; some environments may need permissions. |
| **compat/** | Git-vs-PyGit differential harness. Runs the same scenario in a system-Git workspace and a PyGit workspace and compares refs, tree, and status after each step. **Backends:** `backends.py` (Git, PyGit). **Scenarios:** `scenarios/S1_linear_commits.py` … `S8_multi_branch.py`. **Compare:** `compare.py`; **runner:** `runner.py`. | **CLI:** `pygit compat <scenario>` e.g. `pygit compat S1_linear_commits` (requires system `git`). **From root:** `PYTHONPATH=. python -m pygit compat S1_linear_commits -v`. Use `--keep` to leave temp dirs, `--failfast` to stop on first failure. |
| **demo/** | Runnable demos in isolated temp dirs: init, add, commit, log, status, branches/merge, clone, tags. **Entry:** `run.py` (`demo_basic_workflow`, `demo_branches_and_merge`, etc.). | **From root:** `PYTHONPATH=. python -m demo.run` (all) or `PYTHONPATH=. python -m demo.run basic`, `branches`, `clone`, `tags`. Add `-q` for quiet. Uses `pygit` and creates/removes temp dirs. |
| **bench/** | Timing benchmarks and profiling helpers: N commits, status with many files, clone. **Entry:** `run.py` (`bench_n_commits`, `bench_status_many_files`, `bench_clone_local`). | **From root:** `PYTHONPATH=. python -m bench.run` (all) or `PYTHONPATH=. python -m bench.run commits`, `status`, `clone`. Options: `commits -n 200`, `status -f 1000`, `clone -c 100`. For profiling: `python -m cProfile -o bench.prof -m bench.run commits -n 50`. See **bench/README.md**. |
| **docs/** | Documentation only (no code): **RECON.md** (repo reconnaissance, tests/CLI/storage/refs/transports), **ARCHITECTURE.md** (layers, object model), **INDEX.md** (doc index), **CHECKLIST.md** (post-feature checklist). | **Read only.** Start with **docs/INDEX.md**; use **docs/RECON.md** for “where is X implemented” and how to run tests. |

**Root files:** `main.py` — same as `python -m pygit` (wrapper that calls `pygit.cli.main`). **pyproject.toml** — package metadata and `pygit = pygit.cli:main` entry point. **README.md**, **USAGE.md** — usage and command reference.

---

## Usage

All commands are run as:

```bash
python -m pygit <command> [options]
```

From the project root you may need:

```bash
PYTHONPATH=. python -m pygit <command> ...
```

### Init, add, write-tree, commit-tree, commit, log

```bash
# Create repo (default branch: main)
python -m pygit init

# Stage files (.gitignore respected; use -f to add ignored paths)
python -m pygit add file.txt
python -m pygit add dir/
python -m pygit add -f ignored.txt   # force add ignored file

# Plumbing: build tree from index, then create commit (no ref update)
python -m pygit write-tree          # prints tree hash
python -m pygit commit-tree <treehash> -m "First commit"   # prints commit hash

# Config: set identity (used by commit and tag -a when --author/--tagger not given)
python -m pygit config --set user.name "Alice"
python -m pygit config --set user.email "alice@example.com"
python -m pygit config --get user.name
python -m pygit config --list

# Porcelain: commit (updates HEAD/branch; author from config if not --author)
python -m pygit commit -m "Initial commit"
python -m pygit log -n 5
python -m pygit log --oneline HEAD           # short hash + first line of message
python -m pygit log --oneline v2^{}           # from peeled tag
python -m pygit log --graph -n 3             # prefix * (merge commits: *   )
```

### Checkout: branch and detached HEAD

```bash
# Create and switch to new branch
python -m pygit checkout -b feature

# Switch to existing branch
python -m pygit checkout main

# Detached HEAD (use 40-char commit hash)
python -m pygit checkout <commithash>
```

### Merge (fast-forward and 3-way)

```bash
python -m pygit checkout main
python -m pygit merge feature        # fast-forward or 3-way merge
python -m pygit merge --ff-only feature   # refuse non-FF
python -m pygit merge --no-commit feature # stage merge, do not commit
python -m pygit merge -m "Merge feature" feature
python -m pygit merge -f feature     # allow merge with local changes (overwrites)
```

When history has diverged, a 3-way merge is performed. Conflicts write marker blocks into files; fix them and `commit` to complete. Merge refuses if the working tree is dirty unless `-f`/`--force` is used.

### Cherry-pick

```bash
python -m pygit cherry-pick <commit>   # apply commit onto current HEAD
# On conflict: fix files, pygit add ..., then:
python -m pygit cherry-pick --continue
# Or cancel:
python -m pygit cherry-pick --abort
```

### Diff and reset

```bash
# Working tree vs index
python -m pygit diff

# Index vs HEAD
python -m pygit diff --staged

# Reset (default: --mixed)
python -m pygit reset --soft <commit>   # move HEAD only
python -m pygit reset --mixed <commit>  # reset index too
python -m pygit reset --hard <commit>   # reset index and working tree
```

### Other porcelain

```bash
python -m pygit status
python -m pygit reflog                 # reflog for HEAD (default 10)
python -m pygit reflog main -n 5       # reflog for branch main, 5 entries
python -m pygit branch                 # list
python -m pygit branch new-branch     # create
python -m pygit branch -d branch-name  # delete
python -m pygit rm path/to/file       # remove from index and working tree
python -m pygit rm --cached file      # remove from index only
python -m pygit rm -r dir/             # remove directory (recursive)
python -m pygit show <commit>         # show commit and diff vs parent
python -m pygit restore <paths...>    # restore working tree from index/HEAD
python -m pygit restore --staged <paths...>   # unstage (reset index to HEAD)
python -m pygit restore --source <commit> <paths...>   # restore from commit
```

### Tags

```bash
# List tags
python -m pygit tag

# Lightweight tag (refs/tags/<name> -> commit hash)
python -m pygit tag v1
python -m pygit tag v1 <commit>      # tag at specific commit (default: HEAD)
python -m pygit rev-parse v1          # resolve to commit hash

# Annotated tag (tag object in ODB, refs/tags/<name> -> tag object)
python -m pygit tag -a v2 -m "release v2"
python -m pygit tag -a v2 -m "msg" <commit>   # optional target
python -m pygit cat-file -p v2        # show tag object (object, type, tag, tagger, message)
python -m pygit rev-parse v2^{}       # peel to commit hash
python -m pygit cat-file -t v2       # "tag"; cat-file -t v1 is "commit"

# Delete tag
python -m pygit tag -d v1
```

### Commit graph (merge-base, rev-list, log)

```bash
python -m pygit merge-base main feature      # common ancestor of two branches
python -m pygit rev-list --max-count 5 HEAD  # list up to 5 commits from HEAD
python -m pygit rev-list --parents --all     # all commits from all heads, with parent hashes
python -m pygit log [<rev>] -n 5             # log from rev (default HEAD), first-parent only
python -m pygit log --oneline HEAD           # one line per commit
python -m pygit log --oneline v2^{}          # from peeled tag
```

### Ref plumbing

```bash
python -m pygit show-ref              # list refs (heads and tags)
python -m pygit show-ref --heads      # only refs/heads
python -m pygit show-ref --tags       # only refs/tags
python -m pygit symbolic-ref HEAD refs/heads/main   # set HEAD to branch
python -m pygit update-ref refs/heads/main <newhash> [<oldhash>]   # update ref (optional oldhash check)
```

### Plumbing

```bash
python -m pygit hash-object -w path/to/file   # compute blob hash, write to ODB
python -m pygit cat-file -t <object>          # print type (blob/tree/commit)
python -m pygit cat-file -p <object>          # pretty-print content
python -m pygit ls-tree [-r] [--name-only] <tree-ish>
python -m pygit write-tree
python -m pygit commit-tree <tree> [-p <parent>]... -m "message"
python -m pygit rev-parse <name>              # resolve to 40-char hash
python -m pygit merge-base <revA> <revB>      # find common ancestor (prints hash or exit 1)
python -m pygit rev-list [--max-count N] [--parents] [--all] <rev>   # list commits reachable from rev
```

## Running tests

```bash
PYTHONPATH=. python -m unittest discover -q -s tests
```

Or, if the sandbox blocks creating `.git` dirs, run with permissions that allow `.git` creation.

---

## Documentation

| Document | Description |
|----------|-------------|
| **USAGE.md** | How to run PyGit, example file tree, command reference with expected output and errors, **push to local backup (step-by-step)** and why you must checkout in the backup repo. |
| **docs/RECON.md** | Repository reconnaissance: tests, CLI, objects, storage, refs, transports. |
| **docs/ARCHITECTURE.md** | High-level architecture and data flow. |
| **docs/INDEX.md** | Documentation index. |

## Implementation notes

- **HEAD:** Either `ref: refs/heads/<branch>` (symbolic) or a raw 40-hex commit hash (detached).
- **Refs:** Branches in `.git/refs/heads/`, tags in `.git/refs/tags/`. Use `show-ref`, `symbolic-ref`, `update-ref` for ref plumbing.
- **Objects:** Stored as `zlib.compress(b"<type> <size>\0" + content)` under `.git/objects/<aa>/<bb...>`.
- **Index:** Binary Git DIRC v2 format in `.git/index`. On load, if the file is JSON or legacy `{path: hash}`, it is migrated to binary (and a backup `.git/index.json.bak` may be written). Caching: if `size` and `mtime_ns` match, the file is treated as unchanged unless `PYGIT_PARANOID=1`.
- **Ignore:** `.gitignore` (repo root) and `.git/info/exclude`; `add` skips ignored paths unless `-f/--force`. `.git/` is always excluded.
- **Tags:** Lightweight tags are refs/tags/<name> → commit hash. Annotated tags are tag objects in ODB (`type="tag"`) with object, type, tag, tagger, message; refs/tags/<name> → tag object hash. `rev-parse <name>^{}` peels tag objects to the target (commit/tree/blob).
- **rev-parse order:** HEAD → refs/heads/<name> → refs/tags/<name> → full 40-hex → unique prefix (min 4 chars). Ambiguous prefix raises an error.