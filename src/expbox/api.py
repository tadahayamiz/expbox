from __future__ import annotations

"""
High-level experiment lifecycle API for expbox.

This module provides the three main entry points that back the public
top-level API:

    import expbox as xb

    ctx = xb.init(...)
    ctx = xb.load(...)
    xb.save(ctx, ...)

The responsibilities of this module are:

- Orchestrate paths, metadata, config, and logger construction.
- Delegate all disk I/O to :mod:`expbox.io`.
- Delegate in-memory structures to :mod:`expbox.core`.
- Provide a minimal, stable interface for Python, CLI, and notebooks.

Design principles
-----------------
- Keep the number of public functions very small (init_exp, load_exp, save_exp).
- Avoid heavy dependencies; only standard library is used here.
- Be explicit about what is written to disk and when.
"""

from dataclasses import replace
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Mapping, Optional

from .core import ExpContext, ExpMeta
from .exceptions import ResultsIOError
from .ids import generate_exp_id, IdStyle
from .io import (
    ConfigLike,
    ensure_experiment_dirs,
    load_config,
    load_meta,
    save_meta,
    snapshot_config,
)
from .logger import BaseLogger, FileLogger, NullLogger


# ---------------------------------------------------------------------------
# Git helpers (best-effort, no hard dependency)
# ---------------------------------------------------------------------------


def _collect_git_metadata(project_root: Path) -> Dict[str, Any]:
    """
    Collect basic Git metadata for the current project, if available.

    This function is intentionally best-effort:
    - If the directory is not a git repository, returns an empty dict.
    - If git is not installed or any command fails, returns an empty dict.

    Parameters
    ----------
    project_root:
        Directory assumed to be inside a git repository (typically ``Path.cwd()``).

    Returns
    -------
    dict
        A dictionary that may contain:
        - "repo_root": absolute path to the git repository root
        - "project_root": project root used for detection
        - "commit": current HEAD commit hash
        - "branch": current branch name (if available)
        - "dirty": bool indicating uncommitted changes
        - "remote": {"name": str, "url": str} if an "origin" remote exists
    """
    import subprocess

    def _run(args: list[str]) -> Optional[str]:
        try:
            res = subprocess.run(
                ["git", *args],
                cwd=project_root,
                capture_output=True,
                text=True,
                check=True,
            )
            return res.stdout.strip()
        except Exception:
            return None

    repo_root_str = _run(["rev-parse", "--show-toplevel"])
    if not repo_root_str:
        return {}

    repo_root = Path(repo_root_str).resolve()

    commit = _run(["rev-parse", "HEAD"])
    branch = _run(["rev-parse", "--abbrev-ref", "HEAD"])
    status_out = _run(["status", "--porcelain"])
    dirty = bool(status_out)

    remote_url = _run(["config", "--get", "remote.origin.url"])
    remote: Dict[str, Any] = {}
    if remote_url:
        remote = {"name": "origin", "url": remote_url}

    return {
        "repo_root": str(repo_root),
        "project_root": str(project_root.resolve()),
        "commit": commit,
        "branch": branch,
        "dirty": dirty,
        "remote": remote or None,
    }


def _build_logger(
    backend: str,
    logs_dir: Path,
    artifacts_dir: Path,
) -> BaseLogger:
    """
    Construct a logger backend instance.

    Parameters
    ----------
    backend:
        Name of the logger backend. Currently supported:
        - "none" : :class:`NullLogger`
        - "file" : :class:`FileLogger`
    logs_dir:
        Logs directory (only used for "file").
    artifacts_dir:
        Artifacts directory (only used for "file").

    Returns
    -------
    BaseLogger

    Raises
    ------
    ValueError
        If an unknown backend is requested.
    """
    backend = backend.lower()
    if backend in ("none", "", "null"):
        return NullLogger()
    if backend == "file":
        return FileLogger(logs_dir=logs_dir, artifacts_dir=artifacts_dir)
    # TODO: add "wandb" backend in a separate module to avoid hard dependency.
    raise ValueError(f"Unsupported logger backend: {backend!r}")


# ---------------------------------------------------------------------------
# Public API functions (backing xb.init / xb.load / xb.save)
# ---------------------------------------------------------------------------


def init_exp(
    *,
    project: str = "",
    title: Optional[str] = None,
    purpose: Optional[str] = None,
    config: ConfigLike = None,
    results_root: str | Path = "results",
    exp_id: Optional[str] = None,
    id_style: IdStyle = "datetime",
    id_prefix: Optional[str] = None,
    id_suffix: Optional[str] = None,
    logger: str = "none",
    config_snapshot_name: str = "config.yaml",
    status: Optional[str] = "running",
    env_note: Optional[str] = None,
    extra_meta: Optional[Dict[str, Any]] = None,
) -> ExpContext:
    """
    Initialize a new experiment and return its context.

    This function performs the following steps:

    1. Determine the experiment id (exp_id). If not provided, generate one
       using :func:`expbox.ids.generate_exp_id`.
    2. Create the experiment directory structure under ``results_root/exp_id``.
    3. Load the provided config (mapping, path, or None) via
       :func:`expbox.io.load_config`.
    4. Snapshot the config into ``artifacts/config_snapshot_name`` if non-empty.
    5. Collect basic Git metadata (best-effort).
    6. Construct an :class:`ExpMeta` and write ``meta.json``.
    7. Construct a logger backend (:class:`NullLogger` or :class:`FileLogger`).
    8. Return an :class:`ExpContext` bundling everything.

    Parameters
    ----------
    project:
        Logical project name. If empty, the current working directory name
        may be a reasonable choice for callers.
    title:
        Human-readable experiment title.
    purpose:
        Short free-text description of the experiment purpose.
    config:
        Configuration source. One of:
        - None → empty dict
        - Mapping → shallow copy
        - str/Path → JSON or YAML file
    results_root:
        Root directory under which experiments are stored (default: "results").
    exp_id:
        Optional explicit experiment ID. If omitted, an ID is generated.
    id_style:
        Style for generated IDs (see :func:`generate_exp_id`).
    id_prefix:
        Optional prefix for generated IDs.
    id_suffix:
        Optional suffix for generated IDs.
    logger:
        Logger backend name ("none" or "file").
    config_snapshot_name:
        File name (relative to artifacts dir) to save the config snapshot as.
    status:
        Initial status string (e.g. "running", "queued").
    env_note:
        Optional free-text note about the environment.
    extra_meta:
        Optional extra key-value pairs stored in ``ExpMeta.extra``.

    Returns
    -------
    ExpContext
        Fully constructed experiment context.
    """
    project_root = Path.cwd()
    results_root_path = Path(results_root).resolve()

    if not exp_id:
        exp_id = generate_exp_id(
            style=id_style,
            prefix=id_prefix,
            suffix=id_suffix,
        )

    exp_root = results_root_path / exp_id
    paths = ensure_experiment_dirs(exp_root)

    # 1) Config loading & snapshot
    cfg: Dict[str, Any] = load_config(config)
    config_path_rel: Optional[str] = None
    if cfg:
        snapshot_path = paths.artifacts / config_snapshot_name
        snapshot_config(cfg, snapshot_path)
        # Store a path relative to experiment root for portability
        config_path_rel = str(snapshot_path.relative_to(paths.root))

    # 2) Git metadata
    git_meta = _collect_git_metadata(project_root)
    git_commit = git_meta.get("commit")

    # 3) Fill metadata
    if not project:
        project = project_root.name

    meta = ExpMeta(
        exp_id=exp_id,
        project=project,
        title=title,
        purpose=purpose,
        git_commit=git_commit,
        git=git_meta,
        config_path=config_path_rel,
        logger_backend=logger,
        status=status,
        env_note=env_note,
        extra=extra_meta or {},
    )

    # 4) Write meta.json to disk
    save_meta(meta, paths.root)

    # 5) Logger backend
    logger_backend = _build_logger(
        backend=logger,
        logs_dir=paths.logs,
        artifacts_dir=paths.artifacts,
    )

    # 6) Construct context
    ctx = ExpContext(
        exp_id=exp_id,
        project=project,
        paths=paths,
        config=cfg,
        meta=meta,
        logger=logger_backend,
    )

    return ctx


def load_exp(
    exp_id: str,
    *,
    results_root: str | Path = "results",
    logger: str = "none",
) -> ExpContext:
    """
    Load an existing experiment and return its context.

    This function:

    1. Locates the experiment root at ``results_root / exp_id``.
    2. Loads ``meta.json`` via :func:`expbox.io.load_meta`.
    3. Loads the config snapshot if ``meta.config_path`` is set.
    4. Constructs a logger backend (default: "none").
    5. Returns an :class:`ExpContext`.

    Parameters
    ----------
    exp_id:
        ID of the experiment to load (directory name under results_root).
    results_root:
        Root directory where experiments are stored (default: "results").
    logger:
        Logger backend to attach to the context. Default is "none". This is
        intentionally decoupled from the logger used when the experiment was
        originally run, so callers can decide whether to resume logging.

    Returns
    -------
    ExpContext

    Raises
    ------
    MetaNotFoundError
        If meta.json is not found under the experiment root.
    ResultsIOError
        If loading meta or config fails.
    """
    results_root_path = Path(results_root).resolve()
    exp_root = results_root_path / exp_id

    # Paths (ensure directories exist in case they were partially removed)
    paths = ensure_experiment_dirs(exp_root)

    # Metadata
    meta = load_meta(exp_root)

    # Config (reload from snapshot if available)
    if meta.config_path:
        cfg_path = exp_root / meta.config_path
        cfg: Mapping[str, Any] = load_config(cfg_path)
    else:
        cfg = {}

    # Logger backend (fresh instance)
    logger_backend = _build_logger(
        backend=logger,
        logs_dir=paths.logs,
        artifacts_dir=paths.artifacts,
    )

    ctx = ExpContext(
        exp_id=meta.exp_id,
        project=meta.project,
        paths=paths,
        config=cfg,
        meta=meta,
        logger=logger_backend,
    )
    return ctx


def save_exp(
    ctx: ExpContext,
    *,
    status: Optional[str] = None,
    final_note: Optional[str] = None,
    update_git: bool = True,
) -> None:
    """
    Finalize (or checkpoint) an experiment and persist its metadata.

    This function:

    - Optionally updates the status (e.g. "done", "failed").
    - Sets ``finished_at`` to the current UTC time.
    - Optionally refreshes Git metadata (best-effort).
    - Updates ``logger_backend`` to match the attached logger.
    - Writes ``meta.json`` to disk.
    - Closes the logger backend.

    Parameters
    ----------
    ctx:
        Experiment context to save.
    status:
        Optional new status string. If None, the existing status is kept.
    final_note:
        Optional note summarizing the outcome of this experiment.
    update_git:
        If True, re-collects Git metadata at save-time. If False, keeps the
        original values (useful for debugging or deterministic tests).

    Raises
    ------
    ResultsIOError
        If writing meta.json fails.
    """
    meta = ctx.meta

    # Status and notes
    if status is not None:
        meta.status = status
    if final_note is not None:
        meta.final_note = final_note

    # Timestamps
    meta.finished_at = datetime.utcnow().isoformat()

    # Refresh git metadata if requested
    if update_git:
        git_meta = _collect_git_metadata(Path.cwd())
        # Preserve any existing git keys but update with current info
        if meta.git:
            merged_git = dict(meta.git)
            merged_git.update({k: v for k, v in git_meta.items() if v is not None})
        else:
            merged_git = git_meta
        meta.git = merged_git
        if git_meta.get("commit"):
            meta.git_commit = git_meta["commit"]

    # Logger backend name
    if isinstance(ctx.logger, BaseLogger):
        meta.logger_backend = getattr(ctx.logger, "backend_name", "unknown")

    # Persist meta.json
    save_meta(meta, ctx.paths.root)

    # Close logger (best-effort)
    try:
        ctx.logger.close()
    except Exception as e:  # pragma: no cover
        # We do not want a logging close failure to break the experiment.
        raise ResultsIOError(f"Failed to close logger for exp {meta.exp_id}: {e}")
