from __future__ import annotations

"""
Core data structures for expbox.

This module defines the minimal in-memory representation of an experiment:

- `ExpPaths`  : concrete filesystem locations under `results_root/exp_id/`.
- `ExpMeta`   : machine-readable metadata stored as `meta.json`.
- `ExpContext`: the single context object passed to user code, bundling
                paths, config, metadata, and logger.

Design principles
-----------------
- Keep this module free of heavy dependencies (no Git, no W&B, no I/O).
  All disk access lives in `io.py` and higher-level coordination in `api.py`.
- Use dataclasses for clarity, introspection, and easy JSON (de)serialization.
- Favor explicit fields in `ExpMeta` and allow user extensions via `extra`.

Typical usage
-------------
The typical flow is:

    from expbox.core import ExpPaths, ExpMeta, ExpContext

    # (In api.init_exp)
    paths = ExpPaths.create(results_root / exp_id)
    meta = ExpMeta(exp_id=exp_id, project="my-project", title="baseline")
    ctx = ExpContext(
        exp_id=exp_id,
        project="my-project",
        paths=paths,
        config=config_dict,
        meta=meta,
        logger=my_logger,
    )

User code normally does not construct these objects directly; instead it
receives an `ExpContext` from `expbox.init` / `expbox.load`.
"""

from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Mapping, Optional


# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------


@dataclass
class ExpPaths:
    """
    Collection of paths for a single experiment.

    All paths are rooted under `results_root / exp_id`. The directory
    structure is intentionally kept simple:

        results/
          <exp_id>/
            meta.json
            artifacts/
            figures/
            logs/
            notebooks/

    Attributes
    ----------
    root:
        Root directory of the experiment (`results_root / exp_id`).
    artifacts:
        Directory for configuration snapshots, model weights, tables, etc.
    figures:
        Directory for generated figures.
    logs:
        Directory for log files and metrics.
    notebooks:
        Directory intended for experiment-specific notebooks (optional use).
    """

    root: Path
    artifacts: Path
    figures: Path
    logs: Path
    notebooks: Path

    @classmethod
    def create(cls, root: Path) -> "ExpPaths":
        """
        Create the standard directory layout under `root`.

        Directories are created if they do not already exist.

        Parameters
        ----------
        root:
            Experiment root directory (usually `results_root / exp_id`).

        Returns
        -------
        ExpPaths
            Constructed instance with all subdirectories created.
        """
        root = root.resolve()
        artifacts = root / "artifacts"
        figures = root / "figures"
        logs = root / "logs"
        notebooks = root / "notebooks"

        for p in (root, artifacts, figures, logs, notebooks):
            p.mkdir(parents=True, exist_ok=True)

        return cls(
            root=root,
            artifacts=artifacts,
            figures=figures,
            logs=logs,
            notebooks=notebooks,
        )


# ---------------------------------------------------------------------------
# Metadata
# ---------------------------------------------------------------------------


@dataclass
class ExpMeta:
    """
    Machine-readable metadata for a single experiment.

    This is stored as `meta.json` in the experiment root and is the primary
    source of truth for external integrations (Notion, W&B, reporting
    scripts, etc.).

    The structure is intentionally flexible:
    - Common fields are explicit dataclass attributes.
    - The `extra` dictionary can be used for user extensions without
      breaking compatibility.

    Attributes
    ----------
    exp_id:
        Experiment identifier, used as directory name under results_root.
    project:
        Logical project name (free-form string).
    title:
        Short experiment title.
    purpose:
        Short description of the experiment purpose.

    created_at:
        ISO8601 timestamp when the experiment was created (UTC).
    finished_at:
        ISO8601 timestamp when the experiment was finished (UTC), or None.

    git_commit:
        Legacy / compatibility field for the main commit hash (optional).
    git:
        Free-form dictionary holding richer Git metadata. Typical shape:

        {
          "repo_root": "...",
          "project_relpath": "...",
          "start": {
            "commit": "...",
            "branch": "...",
            "dirty": bool,
            "captured_at": "ISO8601",
          },
          "last": {
            "commit": "...",
            "branch": "...",
            "dirty": bool,
            "saved_at": "ISO8601 | None",
          },
          "dirty_files": ["path/to/file.py", ...],
          "remote": {
            "name": "origin",
            "url": "...",
            "github_commit_url": "https://github.com/.../commit/<hash>"
          } or None,
        }

    config_path:
        Relative path (from experiment root) to the stored config snapshot,
        e.g. "artifacts/config.yaml".
    logger_backend:
        Name of the logger backend in use (e.g. "none", "file", "wandb").
    wandb_run_id:
        Optional W&B run id if a WandbLogger was used.

    status:
        Optional free-form status string (e.g. "running", "done", "failed").
    env_note:
        Optional free-text note about the environment (cluster, GPU, etc.).
    final_note:
        Optional free-text note summarizing the outcome of this experiment.
    extra:
        Free-form dictionary for user extensions.
    """

    exp_id: str
    project: str

    title: Optional[str] = None
    purpose: Optional[str] = None

    created_at: str = field(default_factory=lambda: datetime.utcnow().isoformat())
    finished_at: Optional[str] = None

    # Git metadata
    git_commit: Optional[str] = None  # legacy / compatibility
    git: Dict[str, Any] = field(default_factory=dict)

    config_path: Optional[str] = None
    logger_backend: str = "none"
    wandb_run_id: Optional[str] = None

    status: Optional[str] = None

    env_note: Optional[str] = None
    final_note: Optional[str] = None
    extra: Dict[str, Any] = field(default_factory=dict)


# ---------------------------------------------------------------------------
# Context
# ---------------------------------------------------------------------------


@dataclass
class ExpContext:
    """
    Full experiment context handed to user code.

    This bundles together:

    - `paths`  : where to read/write files for this experiment.
    - `config` : configuration mapping used for this run.
    - `meta`   : structured metadata describing the experiment.
    - `logger` : logger backend for metrics and artifacts.

    The intention is that user code only needs to keep track of a single
    `ExpContext` instance, rather than juggling multiple paths and configs.

    Attributes
    ----------
    exp_id:
        Experiment id (convenience alias, same as `meta.exp_id`).
    project:
        Project name (convenience alias, same as `meta.project`).
    paths:
        `ExpPaths` for this experiment.
    config:
        Loaded configuration as a mapping.
    meta:
        `ExpMeta` describing this experiment.
    logger:
        A `BaseLogger` implementation used for metrics/figures/artifacts.
        The concrete class is defined in `logging.py`.
    """

    exp_id: str
    project: str
    paths: ExpPaths
    config: Mapping[str, Any]
    meta: ExpMeta
    logger: "BaseLogger"  # defined in logging.py

    # NOTE:
    # - `BaseLogger` is a forward reference to avoid circular imports.
    # - The actual logger implementation is provided by higher-level code
    #   (e.g., `api.init_exp`) and injected into the context.
