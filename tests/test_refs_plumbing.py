"""Tests for ref plumbing: show-ref, symbolic-ref, update-ref."""

import tempfile
import unittest
from pathlib import Path

from pygit.plumbing import show_ref, symbolic_ref, update_ref_cmd
from pygit.refs import current_branch_name, resolve_ref
from pygit.repo import Repository


def make_temp_repo() -> Path:
    d = tempfile.mkdtemp(prefix="pygit_refs_plumb_")
    p = Path(d)
    (p / ".git" / "objects").mkdir(parents=True)
    (p / ".git" / "refs" / "heads").mkdir(parents=True)
    (p / ".git" / "refs" / "tags").mkdir(parents=True)
    (p / ".git" / "HEAD").write_text("ref: refs/heads/main\n")
    (p / ".git" / "refs" / "heads" / "main").write_text("a" * 40 + "\n")
    return p


class TestShowRef(unittest.TestCase):
    def setUp(self) -> None:
        self.repo_dir = make_temp_repo()
        self.repo = Repository(str(self.repo_dir))

    def test_show_ref_prints_lines(self) -> None:
        import io
        from contextlib import redirect_stdout
        out = io.StringIO()
        with redirect_stdout(out):
            show_ref(self.repo, heads_only=False, tags_only=False)
        lines = out.getvalue().strip().splitlines()
        self.assertGreaterEqual(len(lines), 1)
        self.assertIn("refs/heads/main", lines[0])
        self.assertEqual(lines[0].split()[0], "a" * 40)


class TestSymbolicRef(unittest.TestCase):
    def setUp(self) -> None:
        self.repo_dir = make_temp_repo()
        self.repo = Repository(str(self.repo_dir))
        (self.repo.git_dir / "refs" / "heads" / "dev").write_text("b" * 40 + "\n")

    def test_symbolic_ref_updates_head(self) -> None:
        symbolic_ref(self.repo, "HEAD", "refs/heads/dev")
        self.assertEqual(current_branch_name(self.repo.git_dir), "dev")
        self.assertEqual(resolve_ref(self.repo.git_dir, "refs/heads/dev"), "b" * 40)


class TestUpdateRef(unittest.TestCase):
    def setUp(self) -> None:
        self.repo_dir = make_temp_repo()
        self.repo = Repository(str(self.repo_dir))

    def test_update_ref_respects_oldhash(self) -> None:
        update_ref_cmd(self.repo, "refs/heads/main", "c" * 40, old_hash="a" * 40)
        self.assertEqual(resolve_ref(self.repo.git_dir, "refs/heads/main"), "c" * 40)

    def test_update_ref_fails_when_oldhash_mismatch(self) -> None:
        from pygit.errors import InvalidRefError
        with self.assertRaises(InvalidRefError):
            update_ref_cmd(self.repo, "refs/heads/main", "d" * 40, old_hash="wrong" * 10)
