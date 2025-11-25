from __future__ import annotations

"""
Top-level package for expbox.

The public API is intentionally minimal and notebook-friendly:

    import expbox as xb

    ctx = xb.init(...)
    ctx = xb.load(...)
    xb.save(ctx)

Internally, these are backed by `init_exp`, `load_exp`, `save_exp` in
`api.py`, so that we can extend the internal API later without breaking
the top-level namespace.

This module also re-exports the core data structures (`ExpContext`,
`ExpMeta`, `ExpPaths`) for advanced users who want to inspect or extend
the behavior.
"""

from importlib.metadata import PackageNotFoundError, version

from .api import init_exp as init, load_exp as load, save_exp as save
from .core import ExpContext, ExpMeta, ExpPaths

try:
    __version__ = version("expbox")
except PackageNotFoundError:  # pragma: no cover - dev / editable install etc.
    # Fallback for editable installs or non-standard environments.
    __version__ = "0.0.0"

__all__ = [
    "init",
    "load",
    "save",
    "ExpContext",
    "ExpMeta",
    "ExpPaths",
    "__version__",
]
