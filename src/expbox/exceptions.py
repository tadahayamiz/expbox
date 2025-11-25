from __future__ import annotations

"""
Custom exceptions used within expbox.

The goal is not to create a large exception hierarchy, but to provide
a few semantically meaningful error types that user code (and tests)
can reliably catch.

Design principles
-----------------
- A single base class: `ExpboxError`.
- Specific subclasses for common failure modes:
  * `MetaNotFoundError`   – missing or unreadable meta.json
  * `ConfigLoadError`     – invalid or unsupported config source
  * `ResultsIOError`      – failures when creating / writing results files

TODO
----
- Consider adding a dedicated error for Git-related failures if/when we
  expose more Git behavior in the public API.
"""


class ExpboxError(Exception):
    """Base class for all expbox-specific exceptions."""


class MetaNotFoundError(ExpboxError):
    """Raised when an experiment's meta.json cannot be found or read."""


class ConfigLoadError(ExpboxError):
    """Raised when a configuration source cannot be loaded as a mapping."""


class ResultsIOError(ExpboxError):
    """Raised when results directories or files cannot be created or written."""
