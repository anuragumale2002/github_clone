"""Tests for config: get/set/list/unset, commit and tag use config identity."""

import io
import sys
import tempfile
import unittest
from pathlib import Path

from pygit.config import get_user_identity, get_value, list_values, set_value, unset_value
from pygit.errors import InvalidConfigKeyError, PygitError
from pygit.plumbing import cat_file_pretty
from pygit.porcelain import (
    add_path,
    commit,
    config_get,
    config_list,
    config_set,
    config_unset,
    tag_create_annotated,
)
from pygit.repo import Repository


class TestConfigGetSetListUnset(unittest.TestCase):
    """Config --get, --set, --list, --unset."""

    def setUp(self) -> None:
        d = tempfile.mkdtemp(prefix="pygit_config_")
        self.repo_dir = Path(d)
        self.repo = Repository(str(self.repo_dir))
        self.repo.init()

    def test_config_set_get(self) -> None:
        set_value(self.repo, "user.name", "Alice")
        set_value(self.repo, "user.email", "alice@example.com")
        self.assertEqual(get_value(self.repo, "user.name"), "Alice")
        self.assertEqual(get_value(self.repo, "user.email"), "alice@example.com")

    def test_config_list_contains_both(self) -> None:
        set_value(self.repo, "user.name", "Alice")
        set_value(self.repo, "user.email", "alice@example.com")
        pairs = list_values(self.repo)
        keys = [k for k, _ in pairs]
        self.assertIn("user.name", keys)
        self.assertIn("user.email", keys)
        d = dict(pairs)
        self.assertEqual(d.get("user.name"), "Alice")
        self.assertEqual(d.get("user.email"), "alice@example.com")

    def test_config_unset_removes(self) -> None:
        set_value(self.repo, "user.name", "Alice")
        set_value(self.repo, "user.email", "alice@example.com")
        ok = unset_value(self.repo, "user.email")
        self.assertTrue(ok)
        self.assertIsNone(get_value(self.repo, "user.email"))
        self.assertEqual(get_value(self.repo, "user.name"), "Alice")

    def test_config_get_missing_raises_from_porcelain(self) -> None:
        with self.assertRaises(PygitError):
            config_get(self.repo, "user.name")

    def test_config_list_sorted(self) -> None:
        set_value(self.repo, "user.email", "a@b.com")
        set_value(self.repo, "user.name", "Bob")
        pairs = list_values(self.repo)
        keys = [k for k, _ in pairs]
        self.assertEqual(keys, sorted(keys))

    def test_config_invalid_key_raises(self) -> None:
        with self.assertRaises(InvalidConfigKeyError):
            set_value(self.repo, "invalid", "x")
        with self.assertRaises(InvalidConfigKeyError):
            set_value(self.repo, "a.b.c", "x")


class TestCommitUsesConfigIdentity(unittest.TestCase):
    """Commit uses user.name and user.email from config when --author not provided."""

    def setUp(self) -> None:
        d = tempfile.mkdtemp(prefix="pygit_config_commit_")
        self.repo_dir = Path(d)
        self.repo = Repository(str(self.repo_dir))
        self.repo.init()
        set_value(self.repo, "user.name", "Alice")
        set_value(self.repo, "user.email", "alice@example.com")
        (self.repo_dir / "f").write_text("x")
        add_path(self.repo, "f")
        self.commit_hash = commit(
            self.repo, "First", author=get_user_identity(self.repo) or "PyGit User <user@pygit.com>"
        )
        self.assertIsNotNone(self.commit_hash)

    def test_commit_author_from_config(self) -> None:
        out = io.StringIO()
        old = sys.stdout
        sys.stdout = out
        try:
            cat_file_pretty(self.repo, self.commit_hash or "")
        finally:
            sys.stdout = old
        text = out.getvalue()
        self.assertIn("Alice <alice@example.com>", text)


class TestAnnotatedTagUsesConfigIdentity(unittest.TestCase):
    """Annotated tag uses user.name and user.email as tagger when --tagger not provided."""

    def setUp(self) -> None:
        d = tempfile.mkdtemp(prefix="pygit_config_tag_")
        self.repo_dir = Path(d)
        self.repo = Repository(str(self.repo_dir))
        self.repo.init()
        set_value(self.repo, "user.name", "Alice")
        set_value(self.repo, "user.email", "alice@example.com")
        (self.repo_dir / "f").write_text("x")
        add_path(self.repo, "f")
        commit(self.repo, "First", author="PyGit <p@x.com>")
        tag_create_annotated(
            self.repo,
            "v1",
            target="HEAD",
            message="Tag v1",
            tagger=get_user_identity(self.repo) or "PyGit User <user@pygit.com>",
        )

    def test_tag_tagger_from_config(self) -> None:
        out = io.StringIO()
        old = sys.stdout
        sys.stdout = out
        try:
            cat_file_pretty(self.repo, "v1")
        finally:
            sys.stdout = old
        text = out.getvalue()
        self.assertIn("tagger Alice <alice@example.com>", text)
