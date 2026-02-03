# PyGit — A minimal Git clone

A single-file "git clone" refactored into a modular, git-correct implementation. Stores objects in `.git/objects` (loose, zlib-compressed). Uses a **binary Git index (DIRC v2)** for `.git/index`; JSON/legacy index is migrated to binary on first load.

**Requirements:** Python 3.11+, macOS/Linux, standard library only.

---

## Install

From the project root (recommended for development):

```bash
pip install -e .
```

Or install as a regular package (e.g. from a built wheel or `pip install .`). The package installs the `pygit` CLI and the `compat` module (for `pygit compat <scenario>`).

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

## Project structure

```
github-clone/
  pygit/
    __init__.py
    __main__.py
    cli.py
    constants.py
    util.py
    objects.py
    odb.py
    refs.py
  index.py
  ignore.py
  repo.py
  graph.py
  porcelain.py
  plumbing.py
  errors.py
  tests/
    test_objects.py
    test_refs.py
    test_index.py
    test_revparse.py
  README.md
```

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
python -m pygit merge --no-ff feature -m "Merge feature"   # always create merge commit (visible in log)
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
| **LINKEDIN_SCREENSHOTS.md** | Step-by-step script for LinkedIn post screenshots (empty folder → init → commit → branch → merge → all commands). |
| **LINKEDIN_TERMINAL_OUTPUT.md** | Recorded terminal output for each screenshot step; copy commands and output for your post. Run `python run_linkedin_demo.py` to regenerate. |

## Implementation notes

- **HEAD:** Either `ref: refs/heads/<branch>` (symbolic) or a raw 40-hex commit hash (detached).
- **Refs:** Branches in `.git/refs/heads/`, tags in `.git/refs/tags/`. Use `show-ref`, `symbolic-ref`, `update-ref` for ref plumbing.
- **Objects:** Stored as `zlib.compress(b"<type> <size>\0" + content)` under `.git/objects/<aa>/<bb...>`.
- **Index:** Binary Git DIRC v2 format in `.git/index`. On load, if the file is JSON or legacy `{path: hash}`, it is migrated to binary (and a backup `.git/index.json.bak` may be written). Caching: if `size` and `mtime_ns` match, the file is treated as unchanged unless `PYGIT_PARANOID=1`.
- **Ignore:** `.gitignore` (repo root) and `.git/info/exclude`; `add` skips ignored paths unless `-f/--force`. `.git/` is always excluded.
- **Tags:** Lightweight tags are refs/tags/<name> → commit hash. Annotated tags are tag objects in ODB (`type="tag"`) with object, type, tag, tagger, message; refs/tags/<name> → tag object hash. `rev-parse <name>^{}` peels tag objects to the target (commit/tree/blob).
- **rev-parse order:** HEAD → refs/heads/<name> → refs/tags/<name> → full 40-hex → unique prefix (min 4 chars). Ambiguous prefix raises an error. **Revision syntax:** `HEAD~1` (first parent), `HEAD~2` (grandparent), `main~1`, `rev^` or `rev^1` (first parent), `rev^2` (second parent for merges).
