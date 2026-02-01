"""Tests for clone (Phase 6, local path; Phase A, dumb HTTP)."""

import tempfile
import threading
import unittest
from http.server import HTTPServer, SimpleHTTPRequestHandler
from pathlib import Path

from pygit.clone import clone
from pygit.porcelain import add_path, commit
from pygit.repo import Repository


def _start_http_server(serve_dir: Path, host: str = "127.0.0.1") -> tuple[HTTPServer, int]:
    """Start HTTP server serving serve_dir in a daemon thread. Returns (server, port)."""
    class Handler(SimpleHTTPRequestHandler):
        def __init__(self, *args, **kwargs):
            kwargs["directory"] = str(serve_dir)
            super().__init__(*args, **kwargs)

    server = HTTPServer((host, 0), Handler)
    port = server.server_address[1]
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    return server, port


class TestCloneLocal(unittest.TestCase):
    """Clone local repo; verify working tree matches."""

    def setUp(self) -> None:
        self.tmp = Path(tempfile.mkdtemp(prefix="pygit_clone_"))
        (self.tmp / "src").mkdir()
        self.repo_src = Repository(str(self.tmp / "src"))
        self.repo_src.init()

    def test_clone_creates_dest_and_checkout(self) -> None:
        (self.tmp / "src" / "f").write_text("hello\n")
        add_path(self.repo_src, "f")
        commit(self.repo_src, "first", "A <a@b.c>")

        dest = self.tmp / "dest"
        clone(self.tmp / "src", dest)

        self.assertTrue(dest.is_dir())
        self.assertTrue((dest / ".git").is_dir())
        self.assertTrue((dest / "f").is_file())
        self.assertEqual((dest / "f").read_text(), "hello\n")

    def test_clone_sets_origin_remote(self) -> None:
        (self.tmp / "src" / "x").write_text("x\n")
        add_path(self.repo_src, "x")
        commit(self.repo_src, "first", "A <a@b.c>")

        dest = self.tmp / "dest"
        repo_dest = clone(self.tmp / "src", dest)

        from pygit.remote import get_remote_url

        url = get_remote_url(repo_dest, "origin")
        self.assertIsNotNone(url)
        self.assertIn("src", str(url))


class TestCloneHttp(unittest.TestCase):
    """Clone via dumb HTTP: serve .git over HTTP, clone from http://localhost:port/repo."""

    def setUp(self) -> None:
        self.tmp = Path(tempfile.mkdtemp(prefix="pygit_clone_http_"))
        self.repo_dir = self.tmp / "repo"
        self.repo_dir.mkdir()
        self.repo_src = Repository(str(self.repo_dir))
        self.repo_src.init()

    def test_clone_http_creates_dest_and_checkout(self) -> None:
        (self.repo_dir / "f").write_text("hello\n")
        add_path(self.repo_src, "f")
        commit(self.repo_src, "first", "A <a@b.c>")

        server, port = _start_http_server(self.tmp)
        try:
            url = f"http://127.0.0.1:{port}/repo"
            dest = self.tmp / "dest"
            clone(url, dest)

            self.assertTrue(dest.is_dir())
            self.assertTrue((dest / ".git").is_dir())
            self.assertTrue((dest / "f").is_file())
            self.assertEqual((dest / "f").read_text(), "hello\n")
        finally:
            server.shutdown()

    def test_clone_http_sets_origin_remote(self) -> None:
        (self.repo_dir / "x").write_text("x\n")
        add_path(self.repo_src, "x")
        commit(self.repo_src, "first", "A <a@b.c>")

        server, port = _start_http_server(self.tmp)
        try:
            url = f"http://127.0.0.1:{port}/repo"
            dest = self.tmp / "dest"
            repo_dest = clone(url, dest)

            from pygit.remote import get_remote_url

            origin_url = get_remote_url(repo_dest, "origin")
            self.assertIsNotNone(origin_url)
            self.assertIn(str(port), origin_url)
            self.assertIn("/repo", origin_url)
        finally:
            server.shutdown()

    def test_clone_http_objects_readable_and_log_matches(self) -> None:
        (self.repo_dir / "g").write_text("world\n")
        add_path(self.repo_src, "g")
        commit(self.repo_src, "first", "B <b@b.c>")

        server, port = _start_http_server(self.tmp)
        try:
            url = f"http://127.0.0.1:{port}/repo"
            dest = self.tmp / "dest"
            repo_dest = clone(url, dest)

            from pygit.objects import Commit
            from pygit.plumbing import rev_parse

            head = rev_parse(repo_dest, "HEAD")
            self.assertTrue(len(head) == 40 and head.isalnum())
            self.assertTrue(repo_dest.odb.exists(head))
            obj = repo_dest.load_object(head)
            self.assertEqual(obj.type, "commit")
            commit_obj = Commit.from_content(obj.content)
            self.assertEqual(commit_obj.message.strip(), "first")
        finally:
            server.shutdown()
