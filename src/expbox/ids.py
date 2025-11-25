from __future__ import annotations

"""
Experiment ID generation utilities.

The experiment ID is used as the directory name under `results_root/`:

    results/
      <exp_id>/
        meta.json
        artifacts/
        figures/
        logs/

This module is intentionally self-contained so that ID policies can be
changed or swapped out later without touching the rest of the codebase.

Typical usage
-------------
    from expbox.ids import generate_exp_id

    exp_id = generate_exp_id(
        style="datetime",
        prefix="baseline",
        suffix=None,
        link_style="kebab",
    )

Design notes
------------
- The default style is a compact datetime stamp: "YYMMDD-HHMM".
- An optional prefix/suffix can be attached.
- `link_style="kebab"` generates `"prefix-241125-1320-suffix"`.
- Implemented to be deterministic and side-effect free; no global state.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Callable, Literal, Optional


IdStyle = Literal["datetime", "date", "seq", "rand"]
LinkStyle = Literal["kebab", "snake"]


@dataclass
class IdGenerator:
    """
    Lightweight pluggable ID generator.

    This is a small wrapper so that callers can inject their own
    experiment ID policy (e.g., for tests or custom workflows)
    without having to reimplement the entire function.

    Parameters
    ----------
    fn:
        Callable that returns a string ID when called with no arguments.
    """

    fn: Callable[[], str]

    def __call__(self) -> str:
        return self.fn()


def _link(a: Optional[str], b: Optional[str], *, style: LinkStyle) -> str:
    """
    Join two ID segments using kebab-case or snake_case.

    Examples
    --------
    >>> _link("pre", "mid", style="kebab")
    'pre-mid'
    >>> _link("pre", None, style="snake")
    'pre'
    """
    if not a:
        return b or ""
    if not b:
        return a

    sep = "-" if style == "kebab" else "_"
    return f"{a}{sep}{b}"


def generate_exp_id(
    *,
    style: IdStyle = "datetime",
    prefix: Optional[str] = None,
    suffix: Optional[str] = None,
    datetime_fmt: str = "%y%m%d-%H%M",
    link_style: LinkStyle = "kebab",
    id_generator: Optional[IdGenerator] = None,
) -> str:
    """
    Generate a new experiment id.

    Parameters
    ----------
    style:
        ID style. The following styles are currently supported:

        - "datetime":
            Use a datetime stamp, e.g. "241125-1320" (YYMMDD-HHMM).
        - "date":
            Use a date stamp, e.g. "241125" (YYMMDD).
        - "seq":
            Reserved for future use (sequential id). Currently falls back
            to datetime.
        - "rand":
            Reserved for future use (random id). Currently falls back
            to datetime.

        TODO:
            Implement proper "seq" and "rand" strategies if needed.
    prefix:
        Optional prefix string to attach before the main id.
    suffix:
        Optional suffix string to attach after the main id.
    datetime_fmt:
        Datetime format string used when style is "datetime" or "date".
    link_style:
        How to join prefix / id / suffix, `"kebab"` or `"snake"`.
    id_generator:
        Optional custom generator object. If provided, this takes
        precedence and we ignore `style` and `datetime_fmt`.

    Returns
    -------
    str
        Newly generated experiment id.
    """
    if id_generator is not None:
        base_id = id_generator()
    else:
        now = datetime.utcnow()
        if style in ("datetime", "date", "seq", "rand"):
            # For now, treat seq/rand as datetime-based as well.
            base_id = now.strftime(datetime_fmt)
        else:  # pragma: no cover - defensive, should not happen in normal use
            raise ValueError(f"Unsupported id style: {style!r}")

    # Attach optional prefix / suffix
    full = base_id
    if prefix:
        full = _link(prefix, full, style=link_style)
    if suffix:
        full = _link(full, suffix, style=link_style)

    return full
