from __future__ import annotations

"""
Logger backends for expbox.

This module provides concrete "experiment logger" implementations that can be
attached to an ``ExpContext``. The goal is to keep the interface very small and
dependency-light, while still supporting practical workflows.

"Logging" here refers to *experiment logging*:
- recording scalar metrics over time (loss, accuracy, etc.)
- optionally copying artifacts (models, tables, small files) into the
  experiment's artifacts directory
- (optionally) forwarding logs to external tools such as Weights & Biases

Design principles
-----------------
- Keep the interface minimal: a tiny base class with a few methods.
- Avoid global state; logger instances are attached to a single experiment.
- Avoid heavy dependencies by default; integrations (like W&B) are optional.
- Prefer fail-safe behavior: if logging fails, do not crash the experiment
  unless the failure is clearly critical.

Logger API
----------
Any logger must implement:

    log_metrics(step: int | None = None, **metrics)
    log_artifact(path: Path, name: str | None = None)
    close()

Metrics format is intentionally simple (JSONL for ``FileLogger``).
"""


import json
from pathlib import Path
from typing import Any, Dict, Optional


# ---------------------------------------------------------------------------
# Base class
# ---------------------------------------------------------------------------


class BaseLogger:
    """
    Abstract base class for expbox loggers.

    Minimal interface:

    - :meth:`log_metrics(step, **metrics)`
    - :meth:`log_artifact(path, name)`
    - :meth:`close()`

    Subclasses should override all methods but may choose to ignore
    unsupported functionality (e.g., :class:`NullLogger`).

    Attributes
    ----------
    backend_name:
        Short string identifying the backend (e.g., "none", "file", "wandb").
    """

    backend_name: str = "none"

    def log_metrics(self, step: Optional[int] = None, **metrics: Any) -> None:
        """
        Log scalar metrics for a given step.

        Parameters
        ----------
        step:
            Optional integer step index (e.g., epoch or iteration).
            If omitted, the backend may infer or ignore it.
        **metrics:
            Arbitrary scalar key-value pairs.

        Notes
        -----
        Implementations should be robust to being called many times and should
        not raise on repeated keys or partially overlapping metric sets.
        """
        raise NotImplementedError

    def log_artifact(self, path: Path, name: Optional[str] = None) -> None:
        """
        Record an artifact (file) for this experiment.

        Parameters
        ----------
        path:
            Source path to an existing file.
        name:
            Optional name for the artifact within the experiment's
            artifacts directory. If omitted, ``path.name`` may be used.

        Notes
        -----
        The default implementation raises :class:`NotImplementedError`.
        Backends that do not support artifacts can safely implement this
        as a no-op.
        """
        raise NotImplementedError

    def close(self) -> None:
        """
        Clean up any resources held by this logger.

        The default implementation is a no-op. Subclasses that keep open
        file handles or network connections should override this method.
        """
        # Intentionally no-op
        return


# ---------------------------------------------------------------------------
# NullLogger
# ---------------------------------------------------------------------------


class NullLogger(BaseLogger):
    """
    Logger that does nothing.

    Useful for:

    - unit tests and dry runs
    - extremely lightweight experiments
    - situations where logging is handled by a different system

    All methods are implemented as no-ops.
    """

    backend_name = "none"

    def log_metrics(self, step: Optional[int] = None, **metrics: Any) -> None:
        return

    def log_artifact(self, path: Path, name: Optional[str] = None) -> None:
        return

    def close(self) -> None:
        return


# ---------------------------------------------------------------------------
# FileLogger
# ---------------------------------------------------------------------------


class FileLogger(BaseLogger):
    """
    Simple metrics and artifact logger that writes JSONL and copies files
    into the experiment's results directory.

    Metrics are written to:

        <results_root>/<exp_id>/logs/metrics.jsonl

    Each line is a JSON object, for example::

        {"step": 10, "loss": 0.15, "acc": 0.92}

    Artifacts are simply *copied* into the artifacts directory.

    Notes
    -----
    - Designed to be extremely robust and dependency-free.
    - Does not attempt concurrency control (sufficient for typical ML runs).
    - If an artifact copy fails, the exception is propagated; this is usually
      desirable because it indicates a real filesystem issue.
    """

    backend_name = "file"

    def __init__(self, logs_dir: Path, artifacts_dir: Path):
        """
        Parameters
        ----------
        logs_dir:
            Directory where log files should be written.
        artifacts_dir:
            Directory where artifacts should be copied.
        """
        self.logs_dir = logs_dir
        self.artifacts_dir = artifacts_dir
        self.metrics_path = logs_dir / "metrics.jsonl"
        self._file = self.metrics_path.open("a", encoding="utf-8")

    def log_metrics(self, step: Optional[int] = None, **metrics: Any) -> None:
        """
        Append a metrics record as a single JSON line.

        Parameters
        ----------
        step:
            Optional integer step index.
        **metrics:
            Arbitrary scalar key-value pairs.

        Notes
        -----
        - The file is flushed after each write to reduce the risk of losing
          data if the process is interrupted.
        - Non-JSON-serializable values will raise a :class:`TypeError`.
        """
        entry: Dict[str, Any] = dict(metrics)
        if step is not None:
            entry["step"] = step

        json.dump(entry, self._file, ensure_ascii=False)
        self._file.write("\n")
        self._file.flush()

    def log_artifact(self, path: Path, name: Optional[str] = None) -> None:
        """
        Copy an artifact into the artifacts directory.

        Parameters
        ----------
        path:
            Source file to copy.
        name:
            Optional new file name inside ``artifacts_dir``. If omitted,
            ``path.name`` is used.

        Raises
        ------
        FileNotFoundError
            If ``path`` does not exist.
        IOError
            If the copy operation fails for any reason.
        """
        import shutil

        src = Path(path)
        if not src.exists():
            raise FileNotFoundError(f"Artifact does not exist: {src}")

        dst = self.artifacts_dir / (name or src.name)
        shutil.copy2(src, dst)

    def close(self) -> None:
        """
        Close the underlying metrics file handle.

        This should be called when the experiment is finished. In practice,
        :func:`expbox.save` will typically handle calling ``close()`` on the
        logger.
        """
        try:
            self._file.close()
        except Exception:
            # We do not want a logging close failure to break the whole
            # experiment at shutdown. Treat it as best-effort.
            pass  # pragma: no cover
