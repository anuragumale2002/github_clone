"""Tests for ignore: ignored file not untracked, add skips unless -f, negation."""

import tempfile
import unittest
from pathlib import Path

from pygit.ignore import IgnoreMatcher, load_ignore_patterns, _parse_patterns


def make_temp_repo() -> tuple[Path, Path]:
    d = tempfile.mkdtemp(prefix="pygit_ignore_")
    root = Path(d)
    git = root / ".git"
    git.mkdir()
    (git / "info").mkdir(parents=True, exist_ok=True)
    return root, git


class TestIgnore(unittest.TestCase):
    def setUp(self) -> None:
        self.repo_root, self.repo_git = make_temp_repo()

    def test_ignored_file_not_untracked(self) -> None:
        (self.repo_root / ".gitignore").write_text("ignore_me.txt\n")
        ign = load_ignore_patterns(self.repo_root)
        self.assertTrue(ign.is_ignored("ignore_me.txt", is_dir=False))
        self.assertFalse(ign.is_ignored("other.txt", is_dir=False))

    def test_add_skips_ignored_unless_force(self) -> None:
        (self.repo_root / ".gitignore").write_text("skip.txt\n")
        (self.repo_root / "skip.txt").write_text("content")
        from pygit.repo import Repository
        from pygit.porcelain import add_path
        repo = Repository(str(self.repo_root))
        repo.git_dir.mkdir(parents=True, exist_ok=True)
        (repo.git_dir / "refs" / "heads").mkdir(parents=True, exist_ok=True)
        (repo.git_dir / "refs" / "tags").mkdir(parents=True, exist_ok=True)
        (repo.git_dir / "HEAD").write_text("ref: refs/heads/main\n")
        add_path(repo, "skip.txt", force=False)
        index = repo.load_index()
        self.assertNotIn("skip.txt", index)
        add_path(repo, "skip.txt", force=True)
        index = repo.load_index()
        self.assertIn("skip.txt", index)

    def test_negation(self) -> None:
        patterns = _parse_patterns("*.log\n!important.log\n")
        ign = IgnoreMatcher(patterns)
        self.assertTrue(ign.is_ignored("a.log", is_dir=False))
        self.assertFalse(ign.is_ignored("important.log", is_dir=False))

    def test_git_always_excluded(self) -> None:
        ign = IgnoreMatcher([])
        self.assertTrue(ign.is_ignored(".git", is_dir=True))
        self.assertTrue(ign.is_ignored(".git/HEAD", is_dir=False))
