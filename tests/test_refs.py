"""Tests for refs: HEAD ref vs detached, update_ref, resolve_ref."""

import tempfile
import unittest
from pathlib import Path

from pygit.refs import (
    HeadState,
    current_branch_name,
    head_commit,
    read_head,
    resolve_ref,
    update_ref,
    write_head_detached,
    write_head_ref,
)


def make_temp_repo() -> Path:
    d = tempfile.mkdtemp(prefix="pygit_refs_")
    p = Path(d)
    (p / "refs" / "heads").mkdir(parents=True)
    (p / "refs" / "tags").mkdir(parents=True)
    return p


class TestRefs(unittest.TestCase):
    def setUp(self) -> None:
        self.repo_git = make_temp_repo()

    def test_write_head_ref(self) -> None:
        write_head_ref(self.repo_git, "refs/heads/main")
        state = read_head(self.repo_git)
        self.assertIsNotNone(state)
        self.assertEqual(state.kind, "ref")
        self.assertEqual(state.value, "refs/heads/main")
        self.assertEqual(current_branch_name(self.repo_git), "main")
        self.assertIsNone(head_commit(self.repo_git))

    def test_write_head_detached(self) -> None:
        sha = "a" * 40
        write_head_detached(self.repo_git, sha)
        state = read_head(self.repo_git)
        self.assertIsNotNone(state)
        self.assertEqual(state.kind, "detached")
        self.assertEqual(state.value, sha)
        self.assertIsNone(current_branch_name(self.repo_git))
        self.assertEqual(head_commit(self.repo_git), sha)

    def test_resolve_ref(self) -> None:
        ref = "refs/heads/main"
        sha = "b" * 40
        update_ref(self.repo_git, ref, sha)
        self.assertEqual(resolve_ref(self.repo_git, ref), sha)
        write_head_ref(self.repo_git, ref)
        self.assertEqual(head_commit(self.repo_git), sha)

    def test_resolve_ref_missing(self) -> None:
        self.assertIsNone(resolve_ref(self.repo_git, "refs/heads/nonexistent"))
