# PyGit Demo Harness

Runnable demos that exercise PyGit in isolated temp dirs.

## Run

From the **project root** (so `pygit` and `demo` resolve):

```bash
# Run all demos
PYTHONPATH=. python -m demo.run

# Run one demo
PYTHONPATH=. python -m demo.run basic
PYTHONPATH=. python -m demo.run branches
PYTHONPATH=. python -m demo.run clone
PYTHONPATH=. python -m demo.run tags

# Quiet (minimal output)
PYTHONPATH=. python -m demo.run basic -q
```

## Demos

| Demo      | Description                          |
|-----------|--------------------------------------|
| `basic`   | Init, add files, commit, log, status |
| `branches`| Create branch, commit, merge         |
| `clone`   | Create source repo, clone to dest     |
| `tags`    | Lightweight and annotated tags        |

Temp dirs are created under the system temp and removed after each demo.
