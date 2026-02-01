# PyGit Post-Feature Completion Checklist

Use this checklist to verify that compat, demos, benchmarks, packaging, and docs are in place and working.

---

## 1. Tests

- [ ] **Full test suite passes**
  ```bash
  PYTHONPATH=. python -m unittest discover -q -s tests
  ```
  Expected: `OK` (all tests pass; some may be skipped if system git is unavailable).

- [ ] **Compat tests** (optional, requires system git)
  ```bash
  PYTHONPATH=. python -m unittest tests.test_compat -v
  ```

---

## 2. Compat harness

- [ ] **Compat runner** — Run one scenario (e.g. S1_linear_commits)
  ```bash
  PYTHONPATH=. python -m compat.runner S1_linear_commits
  ```
  Or via CLI: `pygit compat S1_linear_commits`

- [ ] **Scenarios** — `compat/scenarios/` contains S1–S8 (linear commits, branches, tags, reset, restore, status, stash, multi-branch).

---

## 3. Demo harness

- [ ] **Run all demos**
  ```bash
  PYTHONPATH=. python -m demo.run
  ```
- [ ] **Run one demo** — `python -m demo.run basic` (or branches, clone, tags).

---

## 4. Benchmarks

- [ ] **Run benchmarks**
  ```bash
  PYTHONPATH=. python -m bench.run
  ```
- [ ] **Optional** — Profile with cProfile or py-spy (see `bench/README.md`).

---

## 5. Packaging and install

- [ ] **pyproject.toml** — Present at repo root with `[build-system]`, `[project]`, and entry point `pygit = pygit.cli:main`.
- [ ] **Editable install**
  ```bash
  pip install -e .
  pygit init
  pygit status
  ```

---

## 6. Documentation

- [ ] **docs/RECON.md** — Repository reconnaissance (tests, CLI, objects, storage, refs, index, transports, structure).
- [ ] **docs/ARCHITECTURE.md** — High-level layers, object model, clone/fetch flow.
- [ ] **docs/INDEX.md** — Documentation index.
- [ ] **README.md** — Install section with `pip install -e .` and `PYTHONPATH=.` usage.
- [ ] **USAGE.md** — How to run PyGit, quick workflow, verification.

---

## 7. Status and RECON

- [ ] **README** — Limitations and future work (not implemented) are documented in README.
- [ ] **docs/RECON.md** — Structure section includes compat/, demo/, bench/, pyproject.toml.

---

When all items are checked, the post-feature completion work (Sections 2–7) is done.
