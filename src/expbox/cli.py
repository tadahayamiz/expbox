from __future__ import annotations

"""
Command-line interface for expbox.

This module provides a thin CLI layer around the high-level public API in
:mod:`expbox` (top-level) and export helpers in :mod:`expbox.tools`.

Typical usage
-------------

Initialize a new experiment:

    expbox init --project myproj --config configs/baseline.yaml --logger file

Or with an inline JSON config:

    expbox init --project myproj --config '{"lr": 0.001, "epochs": 5}'

Load and inspect an experiment:

    expbox load EXP_ID --results-root results

Mark an experiment as done:

    expbox save EXP_ID --status done --final-note "OK"

Export metadata of all experiments under results_root:

    expbox export-csv --results-root results --output expbox_export.csv

Notes
-----
- The CLI is primarily a convenience for quick experiments and scripting.
  For more complex workflows, using the Python API directly is recommended.
"""

import argparse
import json
from pathlib import Path
from typing import Any, Dict, Optional, List

from . import init as xb_init, load as xb_load, save as xb_save
from .tools import export_csv as tools_export_csv
from .exceptions import ConfigLoadError


# ---------------------------------------------------------------------------
# Common arguments
# ---------------------------------------------------------------------------


def _add_common_init_args(parser: argparse.ArgumentParser) -> None:
    """
    Arguments shared by the `init` subcommand.
    """
    parser.add_argument(
        "--project",
        type=str,
        default="",
        help="Logical project name (defaults to current directory name).",
    )
    parser.add_argument(
        "--title",
        type=str,
        default=None,
        help="Optional human-readable title for this experiment.",
    )
    parser.add_argument(
        "--purpose",
        type=str,
        default=None,
        help="Optional short description of the experiment's purpose.",
    )
    parser.add_argument(
        "--config",
        type=str,
        default=None,
        help=(
            "Path to a JSON/YAML config file, or a JSON string "
            'like \'{"lr": 0.001}\'.'
        ),
    )
    parser.add_argument(
        "--results-root",
        type=str,
        default="results",
        help='Root directory under which experiment boxes are stored (default: "results").',
    )
    parser.add_argument(
        "--exp-id",
        type=str,
        default=None,
        help="Optional explicit experiment id to use (normally auto-generated).",
    )
    parser.add_argument(
        "--logger",
        type=str,
        default="file",
        choices=["none", "file"],
        help='Logger backend to use ("none" or "file").',
    )
    parser.add_argument(
        "--status",
        type=str,
        default="running",
        help='Initial status string (default: "running").',
    )
    parser.add_argument(
        "--env-note",
        type=str,
        default=None,
        help="Optional free-text note about the environment.",
    )


def _add_common_loadsave_args(parser: argparse.ArgumentParser) -> None:
    """
    Arguments shared by `load` / `save` subcommands.
    """
    parser.add_argument(
        "--results-root",
        type=str,
        default="results",
        help='Root directory under which experiment boxes are stored (default: "results").',
    )
    parser.add_argument(
        "--logger",
        type=str,
        default="file",
        choices=["none", "file"],
        help='Logger backend to use ("none" or "file").',
    )


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _parse_config_arg(config_arg: Optional[str]):
    """
    Parse the --config argument.

    Behavior:
    - If config_arg is None/empty: return (None, None)
    - If it is a path to an existing file: return (None, Path)
    - Otherwise, try to parse as JSON and expect a mapping: return (dict, None)
    - If neither works, raise ConfigLoadError.

    Returns
    -------
    (config_obj, config_path)
        Exactly one of them will be non-None if config_arg was provided.
    """
    if not config_arg:
        return None, None  # (config_obj, config_path)

    # 1) Treat as file path if it exists
    p = Path(config_arg)
    if p.exists():
        return None, p

    # 2) Fallback: treat as JSON string
    try:
        obj = json.loads(config_arg)
    except json.JSONDecodeError:
        raise ConfigLoadError(f"Config file does not exist: {config_arg}")

    if not isinstance(obj, dict):
        raise ConfigLoadError("--config JSON must be an object (mapping)")

    return obj, None


# ---------------------------------------------------------------------------
# Subcommands
# ---------------------------------------------------------------------------


def _cmd_init(args: argparse.Namespace) -> int:
    """
    Initialize a new experiment and print its exp_id.
    """
    config_obj, config_path = _parse_config_arg(args.config)

    # config can be either a dict (in-memory) or a path (JSON/YAML file)
    if config_obj is not None:
        config_for_init = config_obj
    else:
        config_for_init = config_path  # may be None or Path

    ctx = xb_init(
        project=args.project,
        title=args.title,
        purpose=args.purpose,
        config=config_for_init,
        results_root=args.results_root,
        exp_id=args.exp_id,
        logger=args.logger,
        status=args.status,
        env_note=args.env_note,
    )
    print(ctx.meta.exp_id)
    return 0


def _cmd_load(args: argparse.Namespace) -> int:
    """
    Load an experiment and print a JSON summary of its metadata.
    """
    ctx = xb_load(
        args.exp_id,
        results_root=args.results_root,
        logger=args.logger,
        set_active=False,
    )

    summary: Dict[str, Any] = {
        "exp_id": ctx.meta.exp_id,
        "project": ctx.meta.project,
        "title": ctx.meta.title,
        "purpose": ctx.meta.purpose,
        "status": ctx.meta.status,
        "final_note": ctx.meta.final_note,
        "created_at": ctx.meta.created_at,
        "finished_at": ctx.meta.finished_at,
        "results_root": str(Path(args.results_root).resolve()),
        "root": str(ctx.paths.root),
        "logger_backend": ctx.meta.logger_backend,
    }
    print(json.dumps(summary, indent=2, sort_keys=True))
    return 0


def _cmd_save(args: argparse.Namespace) -> int:
    """
    Save (update) an experiment's metadata.

    This is a thin wrapper that reloads the experiment context from disk
    and then delegates to the top-level `expbox.save(ctx, ...)` helper.
    It does *not* rely on any in-process active context.
    """
    # Reload context in a stateless way
    ctx = xb_load(
        args.exp_id,  # None is OK (falls back to active)
        results_root=args.results_root,
        logger=args.logger,
        set_active=False,
    )

    # Update metadata and save
    xb_save(
        ctx,
        status=args.status,
        final_note=args.final_note,
        verbose=(not args.quiet),
    )
    return 0


def _cmd_export_csv(args: argparse.Namespace) -> int:
    """
    Export experiment metadata under results_root to a CSV file.
    """
    fields: Optional[List[str]] = None
    if args.fields:
        # Convert comma-separated fields → list
        fields = [f.strip() for f in args.fields.split(",") if f.strip()]

    out_path = tools_export_csv(
        results_root=args.results_root,
        csv_path=args.output,
        fields=fields,
    )
    print(str(out_path))
    return 0


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------


def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(
        prog="expbox",
        description="Command-line interface for expbox experiment boxes.",
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    # init
    p_init = subparsers.add_parser(
        "init",
        help="Initialize a new experiment box.",
    )
    _add_common_init_args(p_init)
    p_init.set_defaults(func=_cmd_init)

    # load
    p_load = subparsers.add_parser(
        "load",
        help="Load an existing experiment and print a JSON summary.",
    )
    p_load.add_argument(
        "exp_id",
        type=str,
        help="Experiment id to load.",
    )
    _add_common_loadsave_args(p_load)
    p_load.set_defaults(func=_cmd_load)

    # save
    p_save = subparsers.add_parser(
        "save",
        help="Update metadata for an existing experiment.",
    )
    p_save.add_argument(
        "exp_id",
        type=str,
        nargs="?",          
        default=None,       
        help="Experiment id to save/update. If omitted, uses .expbox/active.",
    )
    _add_common_loadsave_args(p_save)
    p_save.add_argument("--status", type=str, default=None, help="Optional new status string to set.")
    p_save.add_argument("--final-note", type=str, default=None, help="Optional final_note string to set.")
    p_save.add_argument(
        "--quiet",
        action="store_true",
        help="Suppress save summary output.",
    )
    p_save.set_defaults(func=_cmd_save)

    # export-csv
    p_export = subparsers.add_parser(
        "export-csv",
        help="Export experiment metadata to a CSV file.",
    )
    p_export.add_argument(
        "--results-root",
        type=str,
        default="results",
        help='Root directory under which experiment boxes are stored (default: "results").',
    )
    p_export.add_argument(
        "--output",
        type=str,
        required=True,
        help="Path to output CSV file.",
    )
    p_export.add_argument(
        "--fields",
        type=str,
        default=None,
        help=(
            "Optional comma-separated list of fields to include in the CSV, "
            'e.g. "exp_id,project,status". If omitted, all fields are included.'
        ),
    )
    p_export.set_defaults(func=_cmd_export_csv)

    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())