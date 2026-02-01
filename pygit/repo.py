"""Repository: ties paths, ODB, refs, and index together."""

from __future__ import annotations

from pathlib import Path
from typing import Dict, List, Optional, Set

from .constants import DEFAULT_BRANCH, MODE_DIR, MODE_FILE, OBJ_COMMIT
from .errors import NotARepositoryError, PathOutsideRepoError
from .index import index_entry_for_file, load_index as index_load, save_index as index_save
from .objects import Blob, Commit, GitObject, Tree
from .objectstore import ObjectStore
from .refs import (
    current_branch_name,
    head_commit,
    list_branches,
    update_ref,
    write_head_ref,
)
from .util import is_executable, normalize_path, read_bytes, write_bytes


class Repository:
    """Git repository: .git dir, objects, refs, index."""

    def __init__(self, path: str | Path = ".") -> None:
        self.path = Path(path).resolve()
        self.git_dir = self.path / ".git"
        self.objects_dir = self.git_dir / "objects"
        self.refs_dir = self.git_dir / "refs"
        self.heads_dir = self.refs_dir / "heads"
        self.tags_dir = self.refs_dir / "tags"
        self.head_file = self.git_dir / "HEAD"
        self.index_file = self.git_dir / "index"
        self.odb = ObjectStore(self.objects_dir)

    def require_repo(self) -> None:
        """Raise NotARepositoryError if not a git repo."""
        if not self.git_dir.is_dir():
            raise NotARepositoryError("not a git repository")

    def safe_path(self, path: str) -> Path:
        """Resolve path relative to repo root; reject escaping."""
        try:
            return normalize_path(self.path, path)
        except ValueError as e:
            raise PathOutsideRepoError(str(e)) from e

    def init(self) -> bool:
        """Create new repo. Return False if already exists."""
        if self.git_dir.exists():
            return False
        self.git_dir.mkdir()
        self.objects_dir.mkdir()
        self.refs_dir.mkdir()
        self.heads_dir.mkdir()
        self.tags_dir.mkdir()
        write_head_ref(self.git_dir, f"refs/heads/{DEFAULT_BRANCH}")
        index_save(self.git_dir, {})
        from . import config
        cfg = config.read_config(self)
        if not cfg.has_section("core"):
            cfg.add_section("core")
            cfg.set("core", "repositoryformatversion", "0")
            cfg.set("core", "filemode", "true")
            cfg.set("core", "bare", "false")
            config.write_config(self, cfg)
        print(f"Initialized empty Git repository in {self.git_dir}")
        return True

    def load_index(self) -> Dict[str, Dict]:
        """Load index (entries: path -> {sha1, mode, size, mtime_ns})."""
        return index_load(self.git_dir)

    def save_index(self, entries: Dict[str, Dict]) -> None:
        """Save index."""
        index_save(self.git_dir, entries)

    def store_object(self, obj: GitObject) -> str:
        """Store object in ODB; return full hash."""
        return self.odb.store(obj)

    def load_object(self, sha: str) -> GitObject:
        """Load object by full hash."""
        return self.odb.load(sha)

    def get_files_from_tree_recursive(self, tree_hash: str, prefix: str = "") -> Set[str]:
        """Return set of file paths (not dirs) under tree."""
        files: Set[str] = set()
        try:
            obj = self.load_object(tree_hash)
            tree = Tree.from_content(obj.content)
            for mode, name, obj_hash in tree.entries:
                full = f"{prefix}{name}"
                if mode.startswith("100"):
                    files.add(full)
                elif mode.startswith("04"):
                    files.update(
                        self.get_files_from_tree_recursive(obj_hash, f"{full}/")
                    )
        except Exception:
            pass
        return files

    def build_index_from_tree(self, tree_hash: str, prefix: str = "") -> Dict[str, str]:
        """Build path -> blob_hash from tree (for index compatibility)."""
        result: Dict[str, str] = {}
        try:
            obj = self.load_object(tree_hash)
            tree = Tree.from_content(obj.content)
            for mode, name, obj_hash in tree.entries:
                full = f"{prefix}{name}"
                if mode.startswith("100"):
                    result[full] = obj_hash
                elif mode.startswith("04"):
                    result.update(self.build_index_from_tree(obj_hash, f"{full}/"))
        except Exception:
            pass
        return result

    def restore_tree(self, tree_hash: str, base_path: Path) -> None:
        """Checkout tree into base_path (create files/dirs)."""
        obj = self.load_object(tree_hash)
        tree = Tree.from_content(obj.content)
        for mode, name, obj_hash in tree.entries:
            p = base_path / name
            if mode.startswith("100"):
                blob_obj = self.load_object(obj_hash)
                p.parent.mkdir(parents=True, exist_ok=True)
                p.write_bytes(blob_obj.content)
            elif mode.startswith("04"):
                p.mkdir(parents=True, exist_ok=True)
                self.restore_tree(obj_hash, p)

    def restore_index_from_tree(self, tree_hash: str) -> None:
        """Set index to match tree (path -> entry with sha1, mode, size, mtime_ns, ctime_ns)."""
        entries: Dict[str, Dict] = {}

        def walk(prefix: str, th: str) -> None:
            obj = self.load_object(th)
            tree = Tree.from_content(obj.content)
            for mode, name, ent_sha in tree.entries:
                path = f"{prefix}{name}" if prefix else name
                if mode.startswith("04"):
                    walk(path + "/", ent_sha)
                else:
                    blob = self.load_object(ent_sha)
                    size = len(blob.content) if hasattr(blob, "content") else 0
                    entries[path] = {
                        "sha1": ent_sha,
                        "mode": mode,
                        "size": size,
                        "mtime_ns": 0,
                        "ctime_ns": 0,
                    }

        walk("", tree_hash)
        self.save_index(entries)

    def create_tree_from_index(self) -> str:
        """Build tree from current index; return tree hash. Uses MODE_DIR 040000."""
        from .constants import MODE_DIR
        entries = self.load_index()
        if not entries:
            tree = Tree()
            return self.store_object(tree)
        # path -> (mode, sha) for files; dirs built as nested dict
        dirs: Dict = {}
        files: Dict[str, tuple[str, str]] = {}  # name -> (mode, sha)
        for file_path, ent in entries.items():
            sha = ent.get("sha1", "")
            mode = ent.get("mode", MODE_FILE)
            parts = file_path.split("/")
            if len(parts) == 1:
                files[parts[0]] = (mode, sha)
            else:
                current = dirs
                for part in parts[:-1]:
                    if part not in current:
                        current[part] = {}
                    current = current[part]
                current[parts[-1]] = (mode, sha)

        def make_tree(entries_dict: Dict) -> str:
            tree = Tree()
            for name in sorted(entries_dict.keys()):
                val = entries_dict[name]
                if isinstance(val, tuple):
                    mode, sha = val
                    tree.add_entry(mode, name, sha)
                else:
                    sub_hash = make_tree(val)
                    tree.add_entry(MODE_DIR, name, sub_hash)
            return self.store_object(tree)

        root: Dict = {}
        for name, t in files.items():
            root[name] = t
        for d, content in dirs.items():
            root[d] = content
        return make_tree(root)

    def create_tree_from_workdir(self) -> str:
        """Build tree from current working dir (paths from index). Missing files -> empty blob."""
        from .util import read_bytes
        entries = self.load_index()
        if not entries:
            tree = Tree()
            return self.store_object(tree)
        dirs: Dict = {}
        files: Dict[str, tuple[str, str]] = {}
        for file_path, ent in entries.items():
            full = self.path / file_path
            mode = ent.get("mode", MODE_FILE)
            if full.is_file():
                content = read_bytes(full)
                blob = Blob(content)
                sha = self.store_object(blob)
                mode = index_entry_for_file(full, sha).get("mode", mode)
            else:
                sha = self.store_object(Blob(b""))
            parts = file_path.split("/")
            if len(parts) == 1:
                files[parts[0]] = (mode, sha)
            else:
                current = dirs
                for part in parts[:-1]:
                    if part not in current:
                        current[part] = {}
                    current = current[part]
                current[parts[-1]] = (mode, sha)
        def make_tree(entries_dict: Dict) -> str:
            tree = Tree()
            for name in sorted(entries_dict.keys()):
                val = entries_dict[name]
                if isinstance(val, tuple):
                    mode, sha = val
                    tree.add_entry(mode, name, sha)
                else:
                    sub_hash = make_tree(val)
                    tree.add_entry(MODE_DIR, name, sub_hash)
            return self.store_object(tree)
        root = {}
        for name, t in files.items():
            root[name] = t
        for d, content in dirs.items():
            root[d] = content
        return make_tree(root)


def list_tree_paths(repo: Repository, tree_hash: str) -> Set[str]:
    """Recursively list all tracked file paths in the tree (not directories)."""
    return repo.get_files_from_tree_recursive(tree_hash, "")


def read_blob_from_tree(repo: Repository, tree_hash: str, rel_path: str) -> Optional[bytes]:
    """Return blob content at rel_path in tree, or None if path does not exist."""
    parts = [p for p in rel_path.split("/") if p]
    if not parts:
        return None
    try:
        obj = repo.load_object(tree_hash)
        tree = Tree.from_content(obj.content)
        for i, part in enumerate(parts):
            found = None
            for mode, name, ent_sha in tree.entries:
                if name == part:
                    found = (mode, ent_sha)
                    break
            if found is None:
                return None
            mode, ent_sha = found
            if i == len(parts) - 1:
                if mode.startswith("100"):
                    blob = repo.load_object(ent_sha)
                    return blob.content
                return None
            if mode.startswith("04"):
                obj = repo.load_object(ent_sha)
                tree = Tree.from_content(obj.content)
            else:
                return None
        return None
    except Exception:
        return None


def tree_hash_for_commit(repo: Repository, commit_hash: str) -> Optional[str]:
    """Load commit and return its tree hash, or None if not a commit."""
    try:
        obj = repo.load_object(commit_hash)
        if obj.type != OBJ_COMMIT:
            return None
        commit = Commit.from_content(obj.content)
        return commit.tree_hash or None
    except Exception:
        return None
