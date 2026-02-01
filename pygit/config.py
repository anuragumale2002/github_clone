"""Git-like configuration: read/write .git/config (INI format)."""

from __future__ import annotations

import configparser
import io
from pathlib import Path
from typing import TYPE_CHECKING, Optional

from .errors import InvalidConfigKeyError, PygitError
from .util import read_text_safe, write_text_atomic

if TYPE_CHECKING:
    from .repo import Repository

CONFIG_FILENAME = "config"


def _config_path(repo: "Repository") -> Path:
    return repo.git_dir / CONFIG_FILENAME


def _parse_key(key: str) -> tuple[str, str]:
    """Return (section, option). Raises InvalidConfigKeyError if key invalid."""
    parts = key.split(".")
    if len(parts) != 2 or not parts[0].strip() or not parts[1].strip():
        raise InvalidConfigKeyError(f"invalid config key: {key!r} (expected section.option)")
    return parts[0].strip(), parts[1].strip()


def read_config(repo: "Repository") -> configparser.ConfigParser:
    """Read .git/config. Return empty parser if file missing. Does not raise."""
    repo.require_repo()
    path = _config_path(repo)
    cfg = configparser.ConfigParser()
    if path.exists():
        try:
            content = read_text_safe(path)
            if content:
                cfg.read_string(content)
        except (configparser.Error, OSError):
            pass
    return cfg


def write_config(repo: "Repository", cfg: configparser.ConfigParser) -> None:
    """Write config to .git/config atomically."""
    repo.require_repo()
    path = _config_path(repo)
    path.parent.mkdir(parents=True, exist_ok=True)
    buf = io.StringIO()
    cfg.write(buf)
    write_text_atomic(path, buf.getvalue())


def get_value(repo: "Repository", key: str) -> Optional[str]:
    """Get config value for key (section.option). Return None if missing."""
    repo.require_repo()
    section, option = _parse_key(key)
    cfg = read_config(repo)
    if cfg.has_section(section) and cfg.has_option(section, option):
        return cfg.get(section, option)
    return None


def set_value(repo: "Repository", key: str, value: str) -> None:
    """Set config value. Creates section if needed."""
    repo.require_repo()
    section, option = _parse_key(key)
    cfg = read_config(repo)
    if not cfg.has_section(section):
        cfg.add_section(section)
    cfg.set(section, option, value)
    write_config(repo, cfg)


def unset_value(repo: "Repository", key: str) -> bool:
    """Remove config option. Remove section if empty. Return True if something removed."""
    repo.require_repo()
    section, option = _parse_key(key)
    cfg = read_config(repo)
    if not cfg.has_section(section) or not cfg.has_option(section, option):
        return False
    cfg.remove_option(section, option)
    if not cfg.options(section):
        cfg.remove_section(section)
    write_config(repo, cfg)
    return True


def list_values(repo: "Repository") -> list[tuple[str, str]]:
    """Return [(key, value), ...] sorted by key (section.option)."""
    repo.require_repo()
    cfg = read_config(repo)
    result: list[tuple[str, str]] = []
    for section in sorted(cfg.sections()):
        for option in sorted(cfg.options(section)):
            result.append((f"{section}.{option}", cfg.get(section, option)))
    return result


def get_user_identity(repo: "Repository") -> Optional[str]:
    """Return 'Name <email>' from user.name and user.email if both set, else None."""
    name = get_value(repo, "user.name")
    email = get_value(repo, "user.email")
    if name is not None and email is not None:
        return f"{name} <{email}>"
    return None
