# How to Use PyGit

This guide explains how to run PyGit, verify that it works, and what to expect from each command (output and errors).

---

## Example file tree

These trees show a typical folder as you run PyGit commands. Replace `myproject` with your directory; run commands from **inside** that directory (or set `PYTHONPATH` to the PyGit repo root).

**Before `init`** (plain directory):

```
myproject/
├── hello.txt
└── readme.md
```

**After `pygit init`** (repository created):

```
myproject/
├── .git/
│   ├── HEAD              → refs/heads/main
│   ├── config            → [core] repositoryformatversion, filemode, bare
│   ├── objects/          (empty at first)
│   ├── refs/
│   │   ├── heads/         (empty until first commit)
│   │   └── tags/
│   └── index             (binary DIRC v2; created on first add)
├── hello.txt
└── readme.md
```

**After `pygit add hello.txt readme.md`** (staged):

```
myproject/
├── .git/
│   ├── index             (now contains hello.txt, readme.md)
│   └── ...
├── hello.txt
└── readme.md
```

**After `pygit commit -m "First"`** (first commit):

```
myproject/
├── .git/
│   ├── HEAD              → refs/heads/main
│   ├── objects/
│   │   └── <aa>/<bb...>   (blob, tree, commit objects)
│   ├── refs/heads/main    → 40-char commit hash
│   └── logs/HEAD         (reflog)
├── hello.txt
└── readme.md
```

---

## How to run PyGit

You can run PyGit in three ways. Use **one** of these consistently.

### 1. Installed (run from any directory)

After `pip install -e .` from the PyGit repo root:

```bash
pygit init
pygit add .
pygit commit -m "First commit"
```

### 2. As a module (no install, from repo root)

From the directory that contains the `pygit` package:

```bash
PYTHONPATH=. python -m pygit init
PYTHONPATH=. python -m pygit add README.md
PYTHONPATH=. python -m pygit commit -m "First commit"
```

From another directory (e.g. your project):

```bash
PYTHONPATH=/path/to/github_clone python -m pygit status
```

### 3. Via main.py (no install, from repo root only)

```bash
python main.py init
python main.py add .
python main.py commit -m "Initial commit"
```

**Wrong:** `python pygit init` — Python looks for a file named `pygit` in the current directory and fails. Use `python -m pygit` or `pygit` (after install) instead.

---

## Quick workflow example

```bash
# 1. Go to project root
cd /path/to/github_clone

# 2. Create a new repo (in a subdir or new folder)
mkdir myproject && cd myproject
# Use .. if myproject is inside github_clone; otherwise PYTHONPATH=/path/to/github_clone
PYTHONPATH=.. python -m pygit init

# 3. Add and commit
echo "Hello" > hello.txt
PYTHONPATH=.. python -m pygit add hello.txt
PYTHONPATH=.. python -m pygit commit -m "Add hello"

# 4. Check status and log
PYTHONPATH=.. python -m pygit status
PYTHONPATH=.. python -m pygit log -n 5

# 5. Tags (optional)
PYTHONPATH=.. python -m pygit tag v1              # lightweight tag at HEAD
PYTHONPATH=.. python -m pygit tag -a v2 -m "v2"    # annotated tag
PYTHONPATH=.. python -m pygit tag                  # list tags
PYTHONPATH=.. python -m pygit rev-parse v2^{}      # peel annotated tag to commit
```

---

## Making sure everything works

### 1. Run the test suite

From the **project root**:

```bash
PYTHONPATH=. python -m unittest discover -q -s tests
```

You should see:

```
----------------------------------------------------------------------
Ran 86 tests in 0.0XXs

OK
```

If you see `Permission denied` or similar when deleting `.git` inside temp dirs, run with full permissions (e.g. outside a restricted sandbox) or run the same command in a normal terminal.

### 2. Run a quick end-to-end check

```bash
cd /tmp
rm -rf pygit_demo && mkdir pygit_demo && cd pygit_demo
PYTHONPATH=/path/to/github_clone python -m pygit init
echo "test" > a.txt
PYTHONPATH=/path/to/github_clone python -m pygit add a.txt
PYTHONPATH=/path/to/github_clone python -m pygit commit -m "First"
PYTHONPATH=/path/to/github_clone python -m pygit log -n 1
PYTHONPATH=/path/to/github_clone python -m pygit status
```

You should see the commit and “nothing to commit, working tree clean”.

### 3. Install (optional)

From the project root you can install PyGit in editable mode and run `pygit` from anywhere:

```bash
pip install -e .
pygit init
pygit status
```

### 4. Demos and benchmarks

- **Demos** — Runnable workflows in isolated temp dirs:  
  `PYTHONPATH=. python -m demo.run` (all) or `python -m demo.run basic` (see `demo/README.md`).
- **Benchmarks** — Timing for commits, status, clone:  
  `PYTHONPATH=. python -m bench.run` (see `bench/README.md`).
- **Compat** — Git vs PyGit scenario runner (requires system git):  
  `pygit compat S1_linear_commits` or `PYTHONPATH=. python -m compat.runner S1_linear_commits`.

### 5. Check the index format

After the first `add` or `commit`, the index is written as binary (DIRC v2):

```bash
head -c 4 .git/index | xxd
# Should show: 44495243  ("DIRC")
```

---

## Cleaning the test folder

- **Future runs:** Tests now create temporary directories in the **system temp** (e.g. `/tmp`), so the `tests/` folder stays clean.
- **Existing leftovers:** If you still see `pygit_*` dirs or `__pycache__` inside `tests/` from older runs, they are **ignored by git** via `tests/.gitignore`. To remove them (from project root):

  ```bash
  rm -rf tests/pygit_* tests/__pycache__
  ```

  On some systems you may need to run this in a normal shell (not a restricted sandbox) if you get permission errors.

---

## Command reference: output and errors

For each command: **what it does**, **how to run it**, **expected output**, and **common errors with how to fix them**.

---

### init

**What it does:** Creates a new repository (`.git/`, HEAD → refs/heads/main, empty index).

**How to run:**

```bash
pygit init
# or: PYTHONPATH=. python -m pygit init
# or: python main.py init
```

**Expected output (success):**

```
Initialized empty Git repository in /path/to/myproject/.git
```

**Common errors:**

| Error | Cause | Fix |
|-------|--------|-----|
| `Repository already exists` | `.git` already present | Nothing to do, or remove `.git` and run again if you want a fresh repo. |
| `Not a git repository` | You ran a different command (e.g. `status`) before `init`. | Run `pygit init` first in this directory. |
| `python: can't open file '.../pygit'` | You ran `python pygit init`. | Use `python -m pygit init` or `pygit init` (after install). |

---

### add \<paths\>

**What it does:** Stages files or directories for the next commit. Respects `.gitignore` unless `-f` is used.

**How to run:**

```bash
pygit add hello.txt
pygit add dir/
pygit add -f ignored.txt    # force add ignored file
```

**Expected output (success):**

```
Added hello.txt
# or: Added 3 files from directory dir/
```

**Common errors:**

| Error | Cause | Fix |
|-------|--------|-----|
| `Not a git repository` | Not inside a repo. | Run `pygit init` in this directory first. |
| `Error: [Errno 2] No such file or directory` | Path does not exist. | Check path spelling and that the file/dir exists. |
| `Error: path escapes repository` | Path points outside repo (e.g. `../other`). | Use paths inside the repo only. |

---

### commit -m \<message\> [--author ...]

**What it does:** Creates a commit from the staged index and updates HEAD/branch. Author comes from config or `--author`.

**How to run:**

```bash
pygit commit -m "First commit"
pygit commit -m "Fix bug" --author "Alice <alice@example.com>"
```

**Expected output (success):**

```
Created commit a1b2c3d on branch main
```

**Common errors:**

| Error | Cause | Fix |
|-------|--------|-----|
| `Not a git repository` | Not inside a repo. | Run `pygit init` first. |
| `nothing to commit, working tree clean` | No changes staged or no changes at all. | Run `pygit add <paths>` then commit, or make file changes first. |
| Exit code 1, no message | Same as above (porcelain prints the message). | Stage files with `add` or ensure index differs from HEAD. |

---

### status

**What it does:** Shows current branch (or detached HEAD), staged changes, unstaged changes, untracked files.

**How to run:**

```bash
pygit status
```

**Expected output (clean repo):**

```
On branch main

nothing to commit, working tree clean
```

**Expected output (with changes):**

```
On branch main

Changes to be committed:
  new file:   foo.txt

Changes not staged for commit:
  modified:   readme.md

Untracked files:
  bar.txt
```

**Common errors:**

| Error | Cause | Fix |
|-------|--------|-----|
| `Not a git repository` | Current directory has no `.git`. | Run `pygit init` here or `cd` into a repo. |

---

### log [\<rev\>] [-n N] [--oneline] [--graph]

**What it does:** Shows commit log from the given rev (default HEAD). First-parent only; `-n` limits count.

**How to run:**

```bash
pygit log
pygit log -n 5
pygit log --oneline HEAD
pygit log --graph -n 3
```

**Expected output (success):**

```
commit a1b2c3d4e5...
Author: Alice <alice@example.com>
Date:   Mon Feb  1 12:00:00 2026 +0000

    First commit
```

**Common errors:**

| Error | Cause | Fix |
|-------|--------|-----|
| `Not a git repository` | Not in a repo. | Run `pygit init` first. |
| `No commits yet!` | No commits in repo. | Make at least one commit. |
| `Error: Invalid ref` / object not found | Rev does not exist. | Use a valid branch name, tag, or 40-char hash. |

---

### config --get / --set / --unset / --list

**What it does:** Reads or writes `.git/config`. Used for `user.name`, `user.email`, etc.

**How to run:**

```bash
pygit config --set user.name "Alice"
pygit config --set user.email "alice@example.com"
pygit config --get user.name
pygit config --list
pygit config --unset user.email
```

**Expected output (--get success):** Prints the value (e.g. `Alice`).

**Expected output (--list success):** Lines like `core.repositoryformatversion=0`, `user.name=Alice`.

**Common errors:**

| Error | Cause | Fix |
|-------|--------|-----|
| `Error: exactly one of --get, --set, --unset, --list required` | No option or more than one. | Use exactly one of `--get`, `--set`, `--unset`, `--list`. |
| `Error: --get requires <key>` | Used `--get` without key. | e.g. `pygit config --get user.name`. |
| `Error: --set requires <key> <value>` | Missing key or value. | e.g. `pygit config --set user.name Alice`. |
| `Error: Key not found: user.name` | Key not in config. | Use `--set` to add it first. |
| `Not a git repository` | Not in a repo. | Run `pygit init` first. |

---

### branch [name] [-d name]

**What it does:** Lists branches, creates a branch, or deletes a branch (`-d`).

**How to run:**

```bash
pygit branch
pygit branch feature
pygit branch -d feature
```

**Expected output (list):** One branch per line (e.g. `main`, `feature`). Current branch may be marked.

**Expected output (create):** `Created branch feature`

**Expected output (delete):** `Deleted branch feature`

**Common errors:**

| Error | Cause | Fix |
|-------|--------|-----|
| `No commits yet, cannot create a branch` | No commit in repo. | Make a commit first. |
| `Branch 'xyz' not found` | Branch does not exist. | Check name; use `pygit branch` to list. |
| `Cannot delete current branch main` | You are on that branch. | Checkout another branch, then delete. |
| `Not a git repository` | Not in a repo. | Run `pygit init` first. |

---

### checkout \<branch-or-commit\> [-b \<branch\>]

**What it does:** Switches to a branch or detaches HEAD at a commit. `-b` creates a new branch and switches to it.

**How to run:**

```bash
pygit checkout main
pygit checkout -b feature
pygit checkout a1b2c3d4e5...
```

**Expected output (success):** `Switched to branch main` or `Created and switched to branch feature` or `Switched to detached HEAD at a1b2c3d`.

**Common errors:**

| Error | Cause | Fix |
|-------|--------|-----|
| `Branch 'xyz' not found` / `Invalid ref` | Branch or commit does not exist. | Use `pygit branch` or a valid 40-char hash. |
| `No commits yet, cannot create a branch` | Repo has no commits. | Make a commit first. |
| `Not a git repository` | Not in a repo. | Run `pygit init` first. |

---

### merge \<name\> [--no-ff] [--ff-only] [--no-commit] [-m msg] [-f]

**What it does:** Merges a branch or rev into the current branch (fast-forward or 3-way). Refuses if working tree is dirty unless `-f`. Use `--no-ff` to always create a merge commit (so the merge appears in `pygit log`).

**Normal merge (no flags):** Run `pygit merge feature` with no flags. When your branch hasn’t diverged (e.g. you only added commits on `feature`), PyGit does a **fast-forward**: it moves `main` to the tip of `feature` and prints `Fast-forward`. The merge **has** worked — `main` now has all of `feature`’s commits. No merge commit is created unless you use `--no-ff`.

**How to run:**

```bash
pygit checkout main
pygit merge feature                    # normal merge: fast-forwards when possible (no flags needed)
pygit merge feature --no-ff -m "Merge feature into main"   # always create a merge commit (visible in log)
pygit merge --ff-only feature
```

**Expected output (normal merge / fast-forward):** `Updating 2b5cea8..8ac6734` and `Fast-forward` — main now includes the feature commits; run `pygit log --oneline -n 3` to confirm.

**Expected output (--no-ff or 3-way):** `Merge made by 3-way merge. New commit abc1234`

**Expected output (already up to date):** `Already up to date.`

**Common errors:**

| Error | Cause | Fix |
|-------|--------|-----|
| `Error: Cannot merge: you have local changes.` | Uncommitted changes. | Commit or stash, or use `merge -f` (overwrites like reset --hard). |
| `Error: Merge conflict.` | Conflicting file changes. | Edit conflicted files (remove `<<<<<<<` / `=======` / `>>>>>>>`), then `pygit add` and `pygit commit`. |
| `Automatic merge failed; fix conflicts and then commit the result.` | Same as above. | Resolve conflicts, `add`, then `commit`. |
| `Not a git repository` | Not in a repo. | Run `pygit init` first. |

---

### reset [--soft | --mixed | --hard] \<commit\>

**What it does:** Moves HEAD to the given commit. `--soft`: only HEAD; `--mixed`: HEAD + index; `--hard`: HEAD + index + working tree.

**How to run:**

```bash
pygit reset --soft HEAD~1
pygit reset --mixed HEAD
pygit reset --hard a1b2c3d
```

**Expected output:** e.g. `HEAD and index reset to a1b2c3d` or `HEAD, index, and working tree reset to a1b2c3d`.

**Common errors:**

| Error | Cause | Fix |
|-------|--------|-----|
| `Error: Invalid ref` / object not found | Commit does not exist. | Use valid branch name or 40-char hash. |
| `Not a git repository` | Not in a repo. | Run `pygit init` first. |

---

### restore \<paths\> [--staged] [--source \<commit\>]

**What it does:** Restores files from index (or HEAD / `--source`). `--staged` unstages only.

**How to run:**

```bash
pygit restore hello.txt
pygit restore --staged hello.txt
pygit restore --source HEAD~1 readme.md
```

**Expected output (success):** No output.

**Common errors:**

| Error | Cause | Fix |
|-------|--------|-----|
| `Error: ...` (path/ref) | Path missing or invalid ref. | Check path and ref. |
| `Not a git repository` | Not in a repo. | Run `pygit init` first. |

---

### tag [name] [target] / tag -a -m / tag -d

**What it does:** Lists tags, creates lightweight or annotated tag, or deletes a tag.

**How to run:**

```bash
pygit tag
pygit tag v1
pygit tag -a v2 -m "Release v2"
pygit tag -d v1
```

**Expected output (list):** One tag per line. **Create:** No output. **Delete:** `Deleted tag 'v1'`

**Common errors:**

| Error | Cause | Fix |
|-------|--------|-----|
| `Error: Invalid ref` / object not found | Target commit does not exist. | Use valid rev (e.g. HEAD or 40-char hash). |
| `Not a git repository` | Not in a repo. | Run `pygit init` first. |

---

### clone \<src\> \<dest\>

**What it does:** Clones a repository from a local path or http(s) URL into \<dest\>.

**How to run:**

```bash
pygit clone /path/to/repo /path/to/dest
pygit clone http://example.com/repo.git dest
```

**Expected output (success):** e.g. `Cloned.` and checkout message; in `dest`, `pygit log` shows history.

**Common errors:**

| Error | Cause | Fix |
|-------|--------|-----|
| `Error: ...` (remote/ref) | Remote not reachable or invalid. | Check URL/path and network; for HTTP, server must expose `.git`. |
| `Not a git repository` | Source is not a repo. | Ensure source has a valid `.git`. |

---

### push \<remote\> [refspec]

**What it does:** Pushes your branch (e.g. `main`) to another repository. **Only local path or `file://` URL is supported** — PyGit cannot push to GitHub (SSH/HTTPS). Use real Git for that: `git push origin main`.

**How to run:**

```bash
pygit remote add backup /path/to/other/repo    # once: add the remote
pygit push backup                              # push current branch (e.g. main)
pygit push backup main                         # or: push branch main explicitly
```

**Important:** Push updates only the **remote’s `.git`** (refs and objects). It does **not** update the remote’s **working directory**. So after you push, the backup folder may still look empty until you run **checkout** (or `reset --hard`) **inside the backup repo**. See the example below.

---

## Push to a local backup (step-by-step example)

This example mirrors a typical workflow: two folders (`my_project` and `my_project_backup`), commit in one, push to the other, then **checkout in the backup** so files appear there.

### 1. Create the backup repo (destination)

```bash
mkdir -p ~/Developer/my_project_backup
cd ~/Developer/my_project_backup
pygit init
```

Output: `Initialized empty Git repository in .../my_project_backup/.git`

### 2. Go to your project (source)

```bash
cd ~/Developer/my_project
```

### 3. Make sure your files are committed

```bash
pygit status
pygit add file1.txt    # if needed
pygit commit -m "Add file1"
```

Output: e.g. `Created commit a1b2c3d on branch main`

### 4. Add the backup folder as a remote

```bash
pygit remote add backup ~/Developer/my_project_backup
```

No output means success.

### 5. Push to the backup

```bash
pygit push backup
```

Push sends your commits and objects to `my_project_backup/.git` and updates its `refs/heads/main`. **The backup’s working directory is not updated** — so if you `cd ~/Developer/my_project_backup` and run `ls`, you may not see `file1.txt` yet.

### 6. In the backup repo, checkout so files appear

```bash
cd ~/Developer/my_project_backup
pygit checkout main
```

Now the working directory is updated to match the commit that `main` points to. Running `ls` should show `file1.txt`.

### Why you must checkout in the backup repo

| What push does | What push does *not* do |
|----------------|--------------------------|
| Updates the remote’s **.git** (refs and objects) | Update the remote’s **working directory** |
| The backup “has” the commit and file content in its object store | The file is not written into the backup folder until you run checkout or reset |

So: **push** = “copy commits/refs into the other repo’s `.git`”. **checkout** (or `reset --hard main`) = “make my working directory match that commit.” Running **checkout** in the backup repo is what makes the files visible there. Git/PyGit do not update the working tree on push by design (to avoid overwriting uncommitted changes on the remote).

---

### stash save / list / apply / pop

**What it does:** Saves working tree and index, lists stashes, or applies/removes a stash.

**How to run:**

```bash
pygit stash save
pygit stash save -m "WIP"
pygit stash list
pygit stash apply
pygit stash pop
```

**Expected output (list):** Lines like `a1b2c3d stash@{0}: WIP on main: ...`

**Common errors:**

| Error | Cause | Fix |
|-------|--------|-----|
| `Not a git repository` | Not in a repo. | Run `pygit init` first. |

---

### Plumbing and other commands

| Command | What it does | How to run | Typical error |
|--------|----------------|------------|----------------|
| `rev-parse <name>` | Resolves name to 40-char hash | `pygit rev-parse HEAD` | Invalid ref → check name/hash |
| `cat-file -t <obj>` | Prints object type | `pygit cat-file -t HEAD` | Object not found → check ref |
| `cat-file -p <obj>` | Pretty-prints object | `pygit cat-file -p HEAD` | Same as above |
| `ls-tree [-r] [--name-only] <tree>` | Lists tree contents | `pygit ls-tree -r HEAD` | Invalid ref → check tree-ish |
| `show-ref [--heads] [--tags]` | Lists refs | `pygit show-ref` | Not a repo → init first |
| `hash-object [-w] <path>` | Computes (and optionally writes) blob hash | `pygit hash-object file.txt` | File not found → check path |
| `write-tree` | Writes index to tree, prints hash | `pygit write-tree` | Not a repo / empty index |
| `commit-tree <tree> -m msg [-p parent]...` | Creates commit object (no ref update) | `pygit commit-tree <hash> -m "msg"` | Invalid tree/parent |
| `merge-base <revA> <revB>` | Prints common ancestor | `pygit merge-base main feature` | Invalid ref → check revs |
| `rev-list [--all] [--max-count N] <rev>` | Lists commit hashes | `pygit rev-list --all` | Invalid ref |
| `reflog [ref] [-n N]` | Shows reflog | `pygit reflog` | Not a repo → init first |
| `diff [--staged]` | Working vs index or index vs HEAD | `pygit diff` | Not a repo |
| `show <commit>` | Commit info + diff vs parent | `pygit show HEAD` | Invalid ref |
| `rm [-r] [--cached] <paths>` | Remove from index/work tree | `pygit rm file.txt` | `'path' not in index` → add first or use correct path |
| `remote add/remove/list` | Manage remotes | `pygit remote add origin <url>` | Wrong usage → see `pygit remote` |
| `fetch <remote>` | Fetch from remote | `pygit fetch origin` | Remote/URL error |
| `push <remote> [refspec]` | Push to remote | `pygit push origin` | Remote/ref error |
| `rebase [upstream]` / --continue / --abort | Rebase or continue/abort | `pygit rebase main` | Conflict → resolve and `rebase --continue` |
| `gc` / `repack` / `prune` | Pack objects, prune loose | `pygit gc` | Not a repo |

For any command, **how to run** is one of:

- `pygit <command> ...` (after `pip install -e .`)
- `PYTHONPATH=/path/to/github_clone python -m pygit <command> ...`
- `python main.py <command> ...` (from PyGit repo root only)

---

## Additional notes (config, reflog, merge, cherry-pick, tags)

### Config (.git/config)

- **Set identity:** `pygit config --set user.name "Alice"` and `pygit config --set user.email "alice@example.com"`.
- **Get:** `pygit config --get user.name` prints the value (exits non-zero if key missing).
- **List:** `pygit config --list` prints `key=value` lines sorted by key.
- **Unset:** `pygit config --unset user.email` removes the key.
- **Commit and tag identity:** When you do not pass `--author` to `commit` or `--tagger` to `tag -a`, PyGit uses `user.name` and `user.email` from `.git/config` if both are set (format `"Name <email>"`). Otherwise it falls back to the default `PyGit User <user@pygit.com>`.

### Reflog

Reflog records when HEAD and branch refs move (commit, checkout, reset, merge, update-ref, symbolic-ref). Entries are stored in `.git/logs/HEAD` and `.git/logs/refs/heads/<branch>`.

- **Show reflog:** `pygit reflog` (default: HEAD, 10 entries); `pygit reflog main -n 5` for branch `main` limited to 5 entries.
- **Output:** `<short_hash> <ref>@{<idx>}: <message>` (most recent first). Empty reflog prints nothing.

### Merge (fast-forward and 3-way)

- **Fast-forward:** `pygit checkout main` then `pygit merge feature` — if HEAD is an ancestor of `feature`, updates current branch/HEAD to the target commit and restores working tree and index. Prints `Updating <old>..<new>` and `Fast-forward`.
- **Already up to date:** If current commit equals the target, prints `Already up to date.`
- **Non-fast-forward (3-way):** When history has diverged, PyGit performs a 3-way merge using the common ancestor. If there are no conflicts, it creates a merge commit (two parents) and updates the branch. Use `--no-commit` to stage the merge without committing; use `-m "msg"` for a custom merge message.
- **Conflicts:** If there are conflicts, conflicted files are written with `<<<<<<< HEAD` / `=======` / `>>>>>>> <name>` markers (text) or left as one version with “Binary file conflict” printed. No commit is created; fix conflicts and run `commit` to finish.
- **--ff-only:** Refuse non-fast-forward merges (same as previous “fast-forward only” behavior).
- **Dirty working tree:** Merge is refused if there are uncommitted changes (unstaged, staged, or untracked) unless you pass `-f`/`--force` (overwrites like a hard reset).

### Cherry-pick

Apply the changes introduced by a commit onto the current HEAD (3-way apply: base = commit’s parent, ours = HEAD, theirs = picked commit).

- **Apply:** `pygit cherry-pick <commit>` — applies the commit; creates a new commit with the same message. Refused if working tree is dirty or a cherry-pick is already in progress.
- **Conflict:** On conflict, files get `<<<<<<< HEAD` / `=======` / `>>>>>>> <short>` markers (same style as merge). State is stored under `.git/pygit/` (CHERRY_PICK_HEAD, CHERRY_PICK_ORIG_HEAD, CHERRY_PICK_MSG, CHERRY_PICK_CONFLICTS). No new commit is created.
- **Continue:** Fix conflicted files, then `pygit add <paths>` and `pygit cherry-pick --continue` to create the commit and clear state.
- **Abort:** `pygit cherry-pick --abort` restores working tree and index to the state before the cherry-pick (reset --hard ORIG_HEAD) and removes state files.
- **Reflog:** Successful cherry-pick and abort append reflog entries (`cherry-pick: <subject>` and `cherry-pick: abort`).

### Commit graph and log

- **merge-base:** `pygit merge-base main feature` — prints the best common ancestor commit hash (e.g. after branching).
- **rev-list:** `pygit rev-list --max-count 5 HEAD` — list up to 5 commits from HEAD; `pygit rev-list --parents --all` — list all commits from all branches with parent hashes on each line.
- **log with rev:** `pygit log --oneline HEAD` — one line per commit (short hash + first line of message); `pygit log --oneline v2^{}` — same starting from peeled tag `v2`.
- **log --graph:** `pygit log --graph -n 3` — prefix each commit with `* ` (merge commits get `*   `).

### Tags

- **List:** `pygit tag`
- **Lightweight:** `pygit tag v1` or `pygit tag v1 <commit>` — refs/tags/v1 points to commit hash.
- **Annotated:** `pygit tag -a v2 -m "release v2"` — creates a tag object in the ODB; refs/tags/v2 points to that object. Use `pygit cat-file -p v2` to show tag content, `pygit rev-parse v2^{}` to get the commit hash.
- **Delete:** `pygit tag -d v1`

See **README.md** for more examples, implementation notes, limitations, and future work (not implemented).
