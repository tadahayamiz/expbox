from __future__ import annotations

"""
Disk I/O utilities for expbox.

This module centralizes all filesystem operations:

- Creating results directories
- Saving and loading meta.json
- Snapshotting and loading configuration files
- Ensuring directory structure exists

Design principles
-----------------
- Keep all pure I/O logic here. No git calls, no logger logic.
- Higher-level orchestration lives in `api.py`.
- In-memory representation (`ExpMeta`, `ExpPaths`, `ExpContext`) lives in `core.py`.
"""

import json
from pathlib import Path
from typing import Any, Dict, Mapping, Optional, Union

from .exceptions import MetaNotFoundError, ConfigLoadError, ResultsIOError
from .core import ExpMeta, ExpPaths


# ---------------------------------------------------------------------------
# Meta I/O
# ---------------------------------------------------------------------------

def save_meta(meta: ExpMeta, root: Path) -> None:
    """
    Write `meta.json` to `root`.

    Parameters
    ----------
    meta:
        ExpMeta instance.
    root:
        Experiment root directory.

    Raises
    ------
    ResultsIOError
        If writing to disk fails.
    """
    path = root / "meta.json"
    try:
        with path.open("w", encoding="utf-8") as f:
            json.dump(meta.__dict__, f, indent=2, ensure_ascii=False)
    except Exception as e:  # pragma: no cover
        raise ResultsIOError(f"Failed to write meta.json at {path}: {e}")


def load_meta(root: Path) -> ExpMeta:
    """
    Load `meta.json` from `root`.

    Parameters
    ----------
    root:
        Experiment root directory.

    Returns
    -------
    ExpMeta

    Raises
    ------
    MetaNotFoundError
        If meta.json does not exist.
    ResultsIOError
        If reading or parsing meta.json fails.
    """
    path = root / "meta.json"
    if not path.exists():
        raise MetaNotFoundError(f"meta.json not found under {root}")

    try:
        with path.open("r", encoding="utf-8") as f:
            data = json.load(f)
        return ExpMeta(**data)
    except Exception as e:  # pragma: no cover
        raise ResultsIOError(f"Failed to load meta.json from {path}: {e}")


# ---------------------------------------------------------------------------
# Config I/O
# ---------------------------------------------------------------------------

ConfigLike = Union[None, Mapping[str, Any], str, Path]


def load_config(config: ConfigLike) -> Dict[str, Any]:
    """
    Load configuration from one of:

    - None → empty dict
    - Mapping → shallow copy
    - string/path → JSON or YAML file

    This function purposely resolves YAML if PyYAML is available,
    but does not introduce a hard dependency.

    Raises
    ------
    ConfigLoadError
        If the config source cannot be parsed.
    """
    if config is None:
        return {}

    if isinstance(config, Mapping):
        return dict(config)

    # Treat as path-like
    path = Path(config)
    if not path.exists():
        raise ConfigLoadError(f"Config file does not exist: {path}")

    try:
        text = path.read_text(encoding="utf-8")
    except Exception as e:  # pragma: no cover
        raise ConfigLoadError(f"Failed to read config file: {path}: {e}")

    # Try JSON first
    if path.suffix.lower() in {".json"}:
        try:
            return json.loads(text)
        except Exception:
            raise ConfigLoadError(f"Config file is not valid JSON: {path}")

    # Try YAML if PyYAML exists
    if path.suffix.lower() in {".yaml", ".yml"}:
        try:
            import yaml  # type: ignore
        except Exception as e:  # pragma: no cover
            raise ConfigLoadError(
                f"PyYAML is not installed but YAML config was provided: {path}"
            )
        try:
            data = yaml.safe_load(text)
            if not isinstance(data, Mapping):
                raise ConfigLoadError(f"YAML config must be a mapping: {path}")
            return dict(data)
        except Exception as e:
            raise ConfigLoadError(f"Invalid YAML config: {path}: {e}")

    raise ConfigLoadError(f"Unsupported config file type: {path}")


def snapshot_config(config: Mapping[str, Any], dest: Path) -> None:
    """
    Save config into `dest` as either JSON or YAML.

    - If `dest` ends with `.yaml` or `.yml`, attempts YAML.
    - Otherwise JSON is used.

    Raises
    ------
    ResultsIOError
        If writing to disk fails.
    """
    dest = dest.resolve()

    try:
        if dest.suffix.lower() in {".yaml", ".yml"}:
            try:
                import yaml  # type: ignore
            except Exception:  # pragma: no cover
                raise ResultsIOError(
                    f"PyYAML is required to write YAML config: {dest}"
                )
            with dest.open("w", encoding="utf-8") as f:
                yaml.safe_dump(dict(config), f, sort_keys=False)
        else:
            # Default: JSON
            with dest.open("w", encoding="utf-8") as f:
                json.dump(config, f, indent=2, ensure_ascii=False)

    except Exception as e:  # pragma: no cover
        raise ResultsIOError(f"Failed to write config snapshot: {dest}: {e}")


# ---------------------------------------------------------------------------
# Directory helpers
# ---------------------------------------------------------------------------

def ensure_experiment_dirs(root: Path) -> ExpPaths:
    """
    Create the standard directory layout under `root`.

    Returns
    -------
    ExpPaths
    """
    return ExpPaths.create(root)


# ---------------------------------------------------------------------------
# Project-level state: active experiment id
# ---------------------------------------------------------------------------

from typing import Optional  # すでに import 済みなら不要

_ACTIVE_STATE_DIR = ".expbox"
_ACTIVE_STATE_FILE = "active"
_INDEX_DIR = "index"


def _get_project_root(start: Optional[Path] = None) -> Path:
    """
    Return the current project root.

    For now this is simply the current working directory resolved.
    If needed, this can be made smarter (e.g., walk up to find pyproject.toml).
    """
    if start is None:
        start = Path.cwd()
    return start.resolve()


def _get_state_dir(project_root: Optional[Path] = None) -> Path:
    """
    Return the directory used to store project-level expbox state,
    creating it if necessary.

    Typically: <project_root>/.expbox
    """
    root = _get_project_root(project_root)
    state_dir = root / _ACTIVE_STATE_DIR
    state_dir.mkdir(parents=True, exist_ok=True)
    return state_dir


def set_active_exp_id(exp_id: str, project_root: Optional[Path] = None) -> None:
    """
    Persist the given experiment id as the active box for this project.

    This writes `<project_root>/.expbox/active`.
    """
    state_dir = _get_state_dir(project_root)
    path = state_dir / _ACTIVE_STATE_FILE
    path.write_text(exp_id, encoding="utf-8")


def get_active_exp_id(project_root: Optional[Path] = None) -> Optional[str]:
    """
    Read the active experiment id for this project, if any.

    Returns
    -------
    str or None
        The exp_id stored in `.expbox/active`, or None if not found.
    """
    state_dir = _get_state_dir(project_root)
    path = state_dir / _ACTIVE_STATE_FILE
    if not path.exists():
        return None
    text = path.read_text(encoding="utf-8").strip()
    return text or None


def get_index_dir(project_root: Optional[Path] = None) -> Path:
    """
    Return the directory used to store expbox index records.

    Typically: <project_root>/.expbox/index
    """
    state_dir = _get_state_dir(project_root)
    index_dir = state_dir / _INDEX_DIR
    index_dir.mkdir(parents=True, exist_ok=True)
    return index_dir


def save_index_record(
    exp_id: str,
    record: Mapping[str, Any],
    project_root: Optional[Path] = None,
) -> Path:
    """
    Write a single experiment index record as JSON:
      <project_root>/.expbox/index/<exp_id>.json
    """
    index_dir = get_index_dir(project_root)
    path = index_dir / f"{exp_id}.json"
    try:
        with path.open("w", encoding="utf-8") as f:
            json.dump(dict(record), f, indent=2, ensure_ascii=False)
    except Exception as e:  # pragma: no cover
        raise ResultsIOError(f"Failed to write index record at {path}: {e}")
    return path


def load_index_record(
    exp_id: str,
    project_root: Optional[Path] = None,
) -> Optional[Dict[str, Any]]:
    """
    Read a single index record. Returns None if missing or unreadable.
    """
    index_dir = get_index_dir(project_root)
    path = index_dir / f"{exp_id}.json"
    if not path.exists():
        return None
    try:
        with path.open("r", encoding="utf-8") as f:
            data = json.load(f)
        return data if isinstance(data, dict) else None
    except Exception:
        return None
