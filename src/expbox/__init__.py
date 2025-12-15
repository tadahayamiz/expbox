from __future__ import annotations

"""
Top-level package for expbox.

This module provides a notebook-friendly, stateful API around the
stateless lifecycle functions in :mod:`expbox.api`.

Typical usage
-------------

    import expbox as xb

    xb.init(project="demo", logger="file")
    for step in range(100):
        loss = ...
        xb.log_metrics(step=step, loss=float(loss))

    xb.final_note("baseline run finished")
    xb.save()

The currently active "box" (experiment) is:

- stored in-memory as a module-level `_active_ctx`
- shared across processes via `.expbox/active` in the project root.

Advanced users can still access the lower-level API:

- :func:`expbox.api.init_exp`
- :func:`expbox.api.load_exp`
- :func:`expbox.api.save_exp`
"""

from importlib.metadata import PackageNotFoundError, version
from typing import Any, Optional

from .api import init_exp, load_exp, save_exp
from .core import ExpContext, ExpMeta, ExpPaths
from .io import get_active_exp_id, set_active_exp_id

# ---------------------------------------------------------------------------
# Package version
# ---------------------------------------------------------------------------

try:
    __version__ = version("expbox")
except PackageNotFoundError:  # pragma: no cover - dev / editable install etc.
    # Fallback for editable installs or non-standard environments.
    __version__ = "0.0.0"


# ---------------------------------------------------------------------------
# Active experiment context (in-memory)
# ---------------------------------------------------------------------------

_active_ctx: Optional[ExpContext] = None


def _require_active() -> ExpContext:
    """
    Return the currently active experiment context, or raise a helpful error.
    """
    if _active_ctx is None:
        raise RuntimeError(
            "No active experiment box. "
            "Call expbox.init(...) or expbox.load(...) first."
        )
    return _active_ctx


def get_active() -> ExpContext:
    """
    Return the currently active experiment context.

    This is a thin wrapper around the internal `_require_active()` and is
    mainly provided for advanced users.
    """
    return _require_active()


# ---------------------------------------------------------------------------
# Public high-level lifecycle API
# ---------------------------------------------------------------------------


def init(*, set_active: bool = True, **kwargs) -> ExpContext:
    """
    Initialize a new experiment box and (optionally) make it active.

    Parameters
    ----------
    set_active:
        If True (default), the created experiment becomes the active box:
        - stored in-memory as `_active_ctx`
        - persisted to `.expbox/active` in the current project.
    **kwargs:
        Passed through to :func:`expbox.api.init_exp`.

    Returns
    -------
    ExpContext
        The newly created experiment context.
    """
    global _active_ctx

    ctx = init_exp(**kwargs)
    if set_active:
        _active_ctx = ctx
        set_active_exp_id(ctx.exp_id)
    return ctx


def load(
    exp_id: Optional[str] = None,
    *,
    set_active: bool = True,
    **kwargs,
) -> ExpContext:
    """
    Load an existing experiment and (optionally) make it active.

    Parameters
    ----------
    exp_id:
        Experiment id to load. If omitted, tries to read from
        `.expbox/active`. If that also fails, raises RuntimeError.
    set_active:
        If True (default), the loaded experiment becomes the active box.
    **kwargs:
        Passed through to :func:`expbox.api.load_exp`
        (e.g., results_root, logger).

    Returns
    -------
    ExpContext
    """
    global _active_ctx

    if exp_id is None:
        exp_id = get_active_exp_id()
        if not exp_id:
            raise RuntimeError(
                "No exp_id was given and no active experiment was found "
                "under .expbox/active. Call expbox.init(...) first."
            )

    ctx = load_exp(exp_id=exp_id, **kwargs)
    if set_active:
        _active_ctx = ctx
        set_active_exp_id(ctx.exp_id)
    return ctx


def save(
    ctx: Optional[ExpContext] = None,
    *,
    verbose: bool = True,
    **kwargs,
) -> None:
    """
    Save a snapshot of an experiment box.

    Parameters
    ----------
    ctx:
        Experiment context to save. If omitted, uses the currently active
        context (see :func:`get_active`).
    verbose:
        If True (default), print a one-shot summary including exp_id and git commit.
    **kwargs:
        Passed through to :func:`expbox.api.save_exp`, e.g.:

        - status: Optional[str]
        - final_note: Optional[str]
        - update_git: bool = True
    """
    if ctx is None:
        ctx = _require_active()
    save_exp(ctx, verbose=verbose, **kwargs)


# ---------------------------------------------------------------------------
# Public high-level logging & meta shortcuts
# ---------------------------------------------------------------------------


def log_metrics(step: Optional[int] = None, **metrics: Any) -> None:
    """
    Log scalar metrics to the active experiment.

    This is a thin wrapper around ``get_active().logger.log_metrics(...)``.
    """
    ctx = _require_active()
    ctx.logger.log_metrics(step=step, **metrics)


def log_table(name: str, table: Any) -> None:
    """
    Log a tabular object (e.g., a pandas DataFrame) to the active experiment.

    By default this writes ``<name>.csv`` under ``paths.artifacts`` if the
    object implements a ``to_csv(path)`` method. This keeps expbox free of a
    hard dependency on pandas while supporting common workflows.

    Parameters
    ----------
    name:
        Logical table name (without extension).
    table:
        An object with a ``to_csv(path)`` method (e.g., pandas.DataFrame).
    """
    ctx = _require_active()
    path = ctx.paths.artifacts / f"{name}.csv"
    to_csv = getattr(table, "to_csv", None)
    if to_csv is None:
        raise TypeError(
            "log_table expects an object with a .to_csv(path) method "
            f"(got {type(table)!r})"
        )
    to_csv(path)


def log_figure(name: str, fig: Any, *, dpi: int = 150) -> None:
    """
    Log a matplotlib-like figure to the active experiment.

    This saves ``<name>.png`` under ``paths.figures`` by calling
    ``fig.savefig(path, dpi=dpi, bbox_inches=\"tight\")``.

    Parameters
    ----------
    name:
        Logical figure name (without extension).
    fig:
        An object with a ``savefig(path, ...)`` method (e.g., matplotlib.Figure).
    dpi:
        Resolution for the saved PNG (default: 150).
    """
    ctx = _require_active()
    path = ctx.paths.figures / f"{name}.png"
    savefig = getattr(fig, "savefig", None)
    if savefig is None:
        raise TypeError(
            "log_figure expects an object with a .savefig(path, ...) method "
            f"(got {type(fig)!r})"
        )
    savefig(path, dpi=dpi, bbox_inches="tight")


def final_note(text: str) -> None:
    """
    Set the final_note field on the active experiment's metadata.
    """
    ctx = _require_active()
    ctx.meta.final_note = text


def set_status(status: str) -> None:
    """
    Set the status field on the active experiment's metadata.
    """
    ctx = _require_active()
    ctx.meta.status = status


# ---------------------------------------------------------------------------
# Dynamic attribute forwarding to the active context
# ---------------------------------------------------------------------------


def __getattr__(name: str):
    """
    Provide convenient accessors for the active box:

    - expbox.paths   -> active_ctx.paths
    - expbox.config  -> active_ctx.config
    - expbox.meta    -> active_ctx.meta
    - expbox.logger  -> active_ctx.logger
    - expbox.exp_id  -> active_ctx.exp_id
    - expbox.project -> active_ctx.project
    - expbox.env     -> active_ctx.meta.extra["env_auto"]
    """
    if name in {"paths", "config", "meta", "logger", "exp_id", "project"}:
        ctx = _require_active()
        return getattr(ctx, name)
    if name == "env":
        ctx = _require_active()
        return (ctx.meta.extra or {}).get("env_auto", {})
    raise AttributeError(...)


__all__ = [
    "init",
    "load",
    "save",
    "get_active",
    "log_metrics",
    "log_table",
    "log_figure",
    "final_note",
    "set_status",
    "ExpContext",
    "ExpMeta",
    "ExpPaths",
    "__version__",
]
