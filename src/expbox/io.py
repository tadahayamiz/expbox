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
