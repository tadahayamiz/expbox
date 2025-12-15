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
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Mapping, Optional

import os
import platform
import sys
import subprocess

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
    save_index_record,
)
from .logger import BaseLogger, FileLogger, NullLogger


# ---------------------------------------------------------------------------
# Git helpers (best-effort, no hard dependency)
# ---------------------------------------------------------------------------


def _run_git(args: list[str], cwd: Path) -> Optional[str]:
    """
    Run a git command and return stdout (stripped), or None on failure.

    Git failures MUST NOT crash experiment lifecycle; they simply result
    in missing git metadata.
    """
    try:
        res = subprocess.run(
            ["git", *args],
            cwd=cwd,
            capture_output=True,
            text=True,
            check=False,
        )
    except Exception:
        return None

    if res.returncode != 0:
        return None
    out = res.stdout.strip()
    return out or None


def _find_git_root(start: Path) -> Optional[Path]:
    """
    Walk up from `start` to find a `.git` directory.

    Returns
    -------
    Path or None
        Repository root if found, else None.
    """
    cur = start.resolve()
    for p in (cur, *cur.parents):
        if (p / ".git").exists():
            return p
    return None


def _get_git_status(repo_root: Path) -> Optional[Dict[str, Any]]:
    """
    Collect basic git status information for the repository.

    Returns
    -------
    dict or None
        {
          "commit": str,
          "branch": str | None,
          "dirty": bool,
          "dirty_files": [str, ...],
          "remote": {
            "name": "origin",
            "url": "...",
            "github_commit_url": "https://github.com/.../commit/<hash>"
          } or None,
        }
    """
    commit = _run_git(["rev-parse", "HEAD"], cwd=repo_root)
    if not commit:
        return None

    subject = _run_git(["log", "-1", "--pretty=%s", "HEAD"], cwd=repo_root)
    branch = _run_git(["rev-parse", "--abbrev-ref", "HEAD"], cwd=repo_root)
    status_out = _run_git(["status", "--porcelain"], cwd=repo_root) or ""
    dirty = bool(status_out.strip())

    dirty_files: list[str] = []
    for line in status_out.splitlines():
        if not line.strip():
            continue
        # format: "XY path"
        if len(line) > 3:
            dirty_files.append(line[3:])
        else:
            dirty_files.append(line.strip())

    remote_url = _run_git(["config", "--get", "remote.origin.url"], cwd=repo_root)
    remote: Dict[str, Any] = {}
    if remote_url:
        remote["name"] = "origin"
        remote["url"] = remote_url

        commit_url: Optional[str] = None
        if "github.com" in remote_url:
            base: Optional[str] = None
            # git@github.com:you/repo.git
            if remote_url.startswith("git@github.com:"):
                path = remote_url[len("git@github.com:") :]
                if path.endswith(".git"):
                    path = path[:-4]
                base = f"https://github.com/{path}"
            # https://github.com/you/repo(.git)
            elif remote_url.startswith(("https://github.com/", "http://github.com/")):
                base = remote_url
                if base.endswith(".git"):
                    base = base[:-4]
            if base:
                commit_url = f"{base}/commit/{commit}"

        if commit_url:
            remote["github_commit_url"] = commit_url

    return {
        "commit": commit,
        "branch": branch,
        "dirty": dirty,
        "dirty_files": dirty_files,
        "remote": remote or None,
        "subject": subject,
    }


def _init_git_section(project_root: Path) -> Dict[str, Any]:
    """
    Initialize the `git` section for ExpMeta at init_exp time.

    - Finds the repo root (walking up from project_root).
    - Captures both `start` and initial `last` (same values).
    - If no git repo is found, returns an empty dict.
    """
    repo_root = _find_git_root(project_root)
    if repo_root is None:
        return {}

    status = _get_git_status(repo_root)
    if status is None:
        return {}

    now_iso = datetime.now(timezone.utc).isoformat()

    try:
        project_relpath = str(project_root.resolve().relative_to(repo_root))
    except ValueError:
        project_relpath = None

    git_section: Dict[str, Any] = {
        "repo_root": str(repo_root),
        "project_relpath": project_relpath,
        "start": {
            "commit": status["commit"],
            "branch": status["branch"],
            "dirty": status["dirty"],
            "captured_at": now_iso,
            "subject": status["subject"],
        },
        "last": {
            "commit": status["commit"],
            "branch": status["branch"],
            "dirty": status["dirty"],
            "saved_at": None,
            "subject": status["subject"],
        },
        "dirty_files": status["dirty_files"],
        "remote": status["remote"],
    }
    return git_section


def _update_git_on_save(meta: ExpMeta) -> None:
    """
    Update the `git.last` section on each save_exp call.

    - If repo_root is known, use it; otherwise try to rediscover.
    - Does NOT create or push any commits.
    - Best-effort: never raises; failures simply leave git metadata unchanged.
    """
    try:
        git_section: Dict[str, Any] = dict(meta.git) if meta.git else {}

        repo_root_str = git_section.get("repo_root")
        if repo_root_str:
            repo_root = Path(repo_root_str)
        else:
            repo_root = _find_git_root(Path.cwd())
            if repo_root is None:
                return
            git_section["repo_root"] = str(repo_root)

        status = _get_git_status(repo_root)
        if status is None:
            return

        last = dict(git_section.get("last") or {})
        last.update(
            {
                "commit": status["commit"],
                "branch": status["branch"],
                "dirty": status["dirty"],
                "saved_at": datetime.now(timezone.utc).isoformat(),
                "subject": status["subject"],
            }
        )
        git_section["last"] = last
        git_section["dirty_files"] = status["dirty_files"]
        git_section["remote"] = status["remote"]

        # Fill project_relpath if missing
        if git_section.get("project_relpath") is None:
            try:
                git_section["project_relpath"] = str(
                    Path.cwd().resolve().relative_to(repo_root)
                )
            except ValueError:
                pass

        meta.git = git_section

        # Backward compatibility: keep git_commit in sync with last.commit
        commit = status["commit"]
        if isinstance(commit, str):
            meta.git_commit = commit
    except Exception:
        # Git metadata should never break save_exp
        return


# ---------------------------------------------------------------------------
# Environment snapshot (best-effort, no hard dependency)
# ---------------------------------------------------------------------------

def _collect_env_info() -> Dict[str, Any]:
    """
    Collect a small, best-effort snapshot of the runtime environment.

    This is intentionally limited to coarse information that is useful for
    reproducibility but unlikely to leak secrets:

    - OS / platform
    - Python version and executable
    - current working directory
    - CUDA / GPU (via nvidia-smi if available)
    - basic cluster hints (SLURM_* env vars)
    """
    info: Dict[str, Any] = {
        "platform": platform.platform(),
        "python_version": sys.version.splitlines()[0],
        "python_executable": sys.executable,
        "cwd": str(Path.cwd()),
    }

    # CUDA / GPU info (if nvidia-smi is available)
    gpu: Optional[list[Dict[str, Optional[str]]]] = None
    try:
        out = subprocess.check_output(
            [
                "nvidia-smi",
                "--query-gpu=name,memory.total",
                "--format=csv,noheader",
            ],
            stderr=subprocess.DEVNULL,
            timeout=2,
            text=True,
        )
        lines = [line.strip() for line in out.splitlines() if line.strip()]
        if lines:
            gpu = []
            for line in lines:
                # e.g. "NVIDIA RTX A6000, 49140 MiB"
                parts = [p.strip() for p in line.split(",")]
                gpu.append(
                    {
                        "name": parts[0],
                        "memory": parts[1] if len(parts) > 1 else None,
                    }
                )
    except Exception:
        gpu = None

    info["gpu"] = gpu
    info["cuda_visible_devices"] = os.environ.get("CUDA_VISIBLE_DEVICES")

    # Simple SLURM hints (if running on a cluster)
    slurm = {
        "job_id": os.environ.get("SLURM_JOB_ID"),
        "ntasks": os.environ.get("SLURM_NTASKS"),
        "nodelist": os.environ.get("SLURM_NODELIST"),
    }
    # すべて None なら不要なので省く
    if any(slurm.values()):
        info["slurm"] = slurm

    return info


# ---------------------------------------------------------------------------
# Logger helpers
# ---------------------------------------------------------------------------


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
def _as_relpath(path: Path, base: Path) -> str:
    """
    Convert `path` to a path relative to `base` if possible; otherwise return str(path).
    """
    try:
        return str(path.resolve().relative_to(base.resolve()))
    except Exception:
        return str(path)


def _sanitize_index_record(record: Dict[str, Any], *, privacy: str) -> Dict[str, Any]:
    """
    Apply privacy rules to a structured index record.

    safe:
      - no absolute paths (keep relative-only where possible)
      - drop dirty_files
      - drop dataset path
      - drop env_auto keys that may leak runtime paths/cluster hints (if present)

    full:
      - keep as-is
    """
    if privacy != "safe":
        return record

    rec = dict(record)

    # Paths: keep only relpaths (already designed to be rel), ensure no absolute fallbacks
    paths = dict(rec.get("paths") or {})
    for k in ("project_root_rel", "box_rel", "config_rel"):
        v = paths.get(k)
        if not isinstance(v, str) or not v:
            continue
        try:
            if Path(v).is_absolute():
                paths[k] = ""
        except Exception:
            # If v isn't a valid path string, keep it as-is.
            pass
    rec["paths"] = paths

    # Drop dirty_files entirely
    if "dirty_files" in rec:
        rec.pop("dirty_files", None)

    # Config-derived dataset path is most sensitive
    cfgd = dict(rec.get("config_derived") or {})
    ds = dict(cfgd.get("dataset") or {})
    if "path" in ds:
        ds["path"] = None
    cfgd["dataset"] = ds
    rec["config_derived"] = cfgd

    # Env auto: keep coarse info only (platform/gpu/cuda_visible_devices)
    env_auto = dict(rec.get("env_auto") or {})
    safe_env = {
        "platform": env_auto.get("platform"),
        "gpu": env_auto.get("gpu"),
        "cuda_visible_devices": env_auto.get("cuda_visible_devices"),
    }
    rec["env_auto"] = safe_env

    return rec


def _build_index_record(ctx: ExpContext) -> Dict[str, Any]:
    """
    Build a structured index record (full) from an ExpContext.
    The caller applies privacy sanitization.
    """
    meta = ctx.meta
    extra = meta.extra or {}
    env_auto = extra.get("env_auto") or {}

    git_section: Dict[str, Any] = dict(meta.git or {})
    git_start = dict(git_section.get("start") or {})
    git_last = dict(git_section.get("last") or {})

    # Best-effort config-derived dataset fields (expects config like {"dataset": {...}})
    dataset = {}
    if isinstance(ctx.config, dict):
        dataset = ctx.config.get("dataset") or {}
    elif isinstance(ctx.config, Mapping):
        dataset = dict(ctx.config).get("dataset") or {}

    project_root = Path.cwd().resolve()
    box_root = ctx.paths.root

    record: Dict[str, Any] = {
        "schema_version": 1,
        "exp_id": meta.exp_id,
        "project": meta.project,
        "title": meta.title,
        "purpose": meta.purpose,
        "status": meta.status,
        "created_at": meta.created_at,
        "finished_at": meta.finished_at,
        "final_note": meta.final_note,
        "env_note": meta.env_note,
        "logger_backend": meta.logger_backend,
        "paths": {
            # keep relative paths to project root where possible
            "project_root_rel": ".",  # explicit anchor
            "box_rel": _as_relpath(box_root, project_root),
            "config_rel": meta.config_path or "",
        },
        "git": {
            "start": {
                "commit": git_start.get("commit"),
                "branch": git_start.get("branch"),
                "dirty": git_start.get("dirty"),
                "subject": git_start.get("subject"),
            },
            "last": {
                "commit": git_last.get("commit"),
                "branch": git_last.get("branch"),
                "dirty": git_last.get("dirty"),
                "saved_at": git_last.get("saved_at"),
                "subject": git_last.get("subject"),
            },
            "remote": git_section.get("remote"),
        },
        # full record keeps dirty files (safe will drop this)
        "dirty_files": {
            "files": git_section.get("dirty_files") or [],
        },
        "env_auto": env_auto,
        "config_derived": {
            "dataset": {
                "name": dataset.get("name") if isinstance(dataset, dict) else None,
                "path": dataset.get("path") if isinstance(dataset, dict) else None,
                "version": dataset.get("version") if isinstance(dataset, dict) else None,
            }
        },
    }
    return record


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
    5. Collect Git metadata (best-effort), storing both `git.start` and
       an initial `git.last`.
    6. Construct an :class:`ExpMeta` and write ``meta.json``.
    7. Construct a logger backend (:class:`NullLogger` or :class:`FileLogger`).
    8. Return an :class:`ExpContext` bundling everything.

    Parameters
    ----------
    project:
        Logical project name. If empty, the current working directory name
        is used.
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
    project_root = Path.cwd().resolve()
    results_root_path = Path(results_root).resolve()

    # 1) Decide exp_id
    if not exp_id:
        exp_id = generate_exp_id(
            style=id_style,
            prefix=id_prefix,
            suffix=id_suffix,
        )

    # 2) Paths & directories
    exp_root = results_root_path / exp_id
    paths = ensure_experiment_dirs(exp_root)

    # 3) Config loading & snapshot
    cfg: Dict[str, Any] = load_config(config)
    config_path_rel: Optional[str] = None
    if cfg:
        snapshot_path = paths.artifacts / config_snapshot_name
        snapshot_config(cfg, snapshot_path)
        # Store a path relative to experiment root for portability
        config_path_rel = str(snapshot_path.relative_to(paths.root))

    # 4) Git metadata (start + initial last)
    git_section = _init_git_section(project_root)
    git_commit: Optional[str] = None
    if git_section:
        start_info = git_section.get("start") or {}
        c = start_info.get("commit")
        if isinstance(c, str):
            git_commit = c

    # 5) Metadata (including environment snapshot)
    if not project:
        project = project_root.name
    env_auto = _collect_env_info()
    if extra_meta is None:
        extra_meta = {}
    extra_meta.setdefault("env_auto", env_auto)

    meta = ExpMeta(
        exp_id=exp_id,
        project=project,
        title=title,
        purpose=purpose,
        git_commit=git_commit,
        git=git_section,
        config_path=config_path_rel,
        logger_backend=logger,
        status=status,
        env_note=env_note,
        extra=extra_meta,
    )

    # 6) Write meta.json to disk
    save_meta(meta, paths.root)

    # 7) Logger backend
    logger_backend = _build_logger(
        backend=logger,
        logs_dir=paths.logs,
        artifacts_dir=paths.artifacts,
    )

    # 8) Construct context
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
    verbose: bool = True,
) -> None:
    """
    Save a snapshot of an experiment and persist its metadata.

    This function is intended to be called multiple times over the lifetime
    of a single experiment "box". Each call:

    - Optionally updates the status (e.g. "running", "done").
    - Updates ``finished_at`` to the current UTC time (last-saved timestamp).
    - Optionally refreshes Git metadata:
        * updates ``git.last`` to the current HEAD
        * updates ``git.dirty_files`` and ``git.remote``
        * keeps ``git.start`` untouched
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
        Optional note summarizing the experiment at this snapshot.
    update_git:
        If True, refreshes Git metadata at save-time. If False, keeps the
        existing values (useful for debugging or deterministic tests).
    verbose:
        If True, prints a brief message to stdout upon successful save.

    Raises
    ------
    ResultsIOError
        If writing meta.json fails or if logger closing fails.
    """
    meta = ctx.meta

    # Status and notes
    if status is not None:
        meta.status = status
    if final_note is not None:
        meta.final_note = final_note

    # Timestamp: last snapshot/save time
    meta.finished_at = datetime.now(timezone.utc).isoformat()

    # Refresh git metadata if requested (best-effort)
    if update_git:
        _update_git_on_save(meta)

    # Logger backend name
    if isinstance(ctx.logger, BaseLogger):
        meta.logger_backend = getattr(ctx.logger, "backend_name", meta.logger_backend)

    # Persist meta.json
    try:
        save_meta(meta, ctx.paths.root)
    except Exception as e:  # pragma: no cover
        raise ResultsIOError(f"Failed to write meta.json for exp {meta.exp_id}: {e}")

    # Write/update per-experiment index record under .expbox/index/<exp_id>.json
    # Index is best-effort: failures must not break save_exp.
    try:
        privacy = (meta.extra or {}).get("privacy") or "safe"
        record_full = _build_index_record(ctx)
        record = _sanitize_index_record(record_full, privacy=str(privacy))
        save_index_record(meta.exp_id, record)
    except Exception:
        pass

    # Close logger (best-effort but reported)
    try:
        ctx.logger.close()
    except Exception as e:  # pragma: no cover
        # We do not want a logging close failure to silently pass in tests.
        raise ResultsIOError(f"Failed to close logger for exp {meta.exp_id}: {e}")

    # Verbose output
    if verbose:
        git = meta.git or {}
        last = (git.get("last") or {}) if isinstance(git, dict) else {}
        commit = last.get("commit") or meta.git_commit
        branch = last.get("branch")
        dirty = last.get("dirty")
        subject = last.get("subject")

        short = commit[:7] if isinstance(commit, str) and len(commit) >= 7 else commit
        dirty_str = "dirty" if dirty else "clean" if dirty is not None else "unknown"

        print(
            "[expbox] saved\n"
            f"  exp_id : {meta.exp_id}\n"
            f"  project: {meta.project}\n"
            f"  status : {meta.status}\n"
            f"  git    : {(branch or '-') } @ {(short or '-') } ({dirty_str})\n"
            f"  path   : {ctx.paths.root}"
            + (f"\n  subject: {subject}" if subject else "")
        )