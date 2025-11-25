from __future__ import annotations

"""
Command-line interface for expbox.

This module provides a thin CLI layer around the high-level API in
:mod:`expbox.api`. It is intentionally minimal and uses only the
standard library (argparse).

Typical usage
-------------

Initialize a new experiment:

    expbox init --project myproj --config configs/baseline.yaml --logger file

Load and inspect an experiment:

    expbox load exp-241125-1320

Finalize an experiment (mark as done):

    expbox save exp-241125-1320 --status done

Notes
-----
- The CLI is primarily a convenience for quick experiments and scripting.
  For more complex workflows, using the Python API directly is recommended.
"""

import argparse
import json
from pathlib import Path
from typing import Any, Dict, Optional

from .api import init_exp, load_exp, save_exp


def _add_common_init_args(parser: argparse.ArgumentParser) -> None:
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
        help="Short human-readable title for this experiment.",
    )
    parser.add_argument(
        "--purpose",
        type=str,
        default=None,
        help="Short free-text description of the experiment purpose.",
    )
    parser.add_argument(
        "--config",
        type=str,
        default=None,
        help="Path to a JSON or YAML config file.",
    )
    parser.add_argument(
        "--results-root",
        type=str,
        default="results",
        help='Directory under which experiments are stored (default: "results").',
    )
    parser.add_argument(
        "--exp-id",
        type=str,
        default=None,
        help="Explicit experiment ID (otherwise auto-generated).",
    )
    parser.add_argument(
        "--logger",
        type=str,
        default="none",
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


def _cmd_init(args: argparse.Namespace) -> int:
    ctx = init_exp(
        project=args.project,
        title=args.title,
        purpose=args.purpose,
        config=args.config,
        results_root=args.results_root,
        exp_id=args.exp_id,
        logger=args.logger,
        status=args.status,
        env_note=args.env_note,
    )
    print(ctx.meta.exp_id)
    return 0


def _cmd_load(args: argparse.Namespace) -> int:
    ctx = load_exp(
        exp_id=args.exp_id,
        results_root=args.results_root,
        logger=args.logger,
    )

    # Print a minimal JSON summary of meta.
    summary: Dict[str, Any] = {
        "exp_id": ctx.meta.exp_id,
        "project": ctx.meta.project,
        "title": ctx.meta.title,
        "purpose": ctx.meta.purpose,
        "status": ctx.meta.status,
        "created_at": ctx.meta.created_at,
        "finished_at": ctx.meta.finished_at,
        "results_root": str(Path(args.results_root).resolve()),
        "root": str(ctx.paths.root),
        "logger_backend": ctx.meta.logger_backend,
    }
    print(json.dumps(summary, indent=2, ensure_ascii=False))
    return 0


def _cmd_save(args: argparse.Namespace) -> int:
    ctx = load_exp(
        exp_id=args.exp_id,
        results_root=args.results_root,
        logger=args.logger,
    )
    save_exp(
        ctx,
        status=args.status,
        final_note=args.final_note,
        update_git=not args.no_update_git,
    )
    print(f"Saved experiment: {ctx.meta.exp_id}")
    return 0


def main(argv: Optional[list[str]] = None) -> int:
    """
    CLI entry point.

    Parameters
    ----------
    argv:
        Optional list of arguments (excluding the program name). If None,
        :data:`sys.argv[1:]` is used.

    Returns
    -------
    int
        Exit code (0 for success).
    """
    parser = argparse.ArgumentParser(prog="expbox", description="expbox CLI")
    subparsers = parser.add_subparsers(dest="command", required=True)

    # init
    p_init = subparsers.add_parser("init", help="Initialize a new experiment.")
    _add_common_init_args(p_init)
    p_init.set_defaults(func=_cmd_init)

    # load
    p_load = subparsers.add_parser("load", help="Load and summarize an experiment.")
    p_load.add_argument("exp_id", type=str, help="Experiment ID to load.")
    p_load.add_argument(
        "--results-root",
        type=str,
        default="results",
        help='Directory under which experiments are stored (default: "results").',
    )
    p_load.add_argument(
        "--logger",
        type=str,
        default="none",
        choices=["none", "file"],
        help='Logger backend to use when loading ("none" or "file").',
    )
    p_load.set_defaults(func=_cmd_load)

    # save
    p_save = subparsers.add_parser("save", help="Finalize an experiment.")
    p_save.add_argument("exp_id", type=str, help="Experiment ID to save/finalize.")
    p_save.add_argument(
        "--results-root",
        type=str,
        default="results",
        help='Directory under which experiments are stored (default: "results").',
    )
    p_save.add_argument(
        "--logger",
        type=str,
        default="none",
        choices=["none", "file"],
        help='Logger backend to attach while saving ("none" or "file").',
    )
    p_save.add_argument(
        "--status",
        type=str,
        default="done",
        help='New status string (default: "done").',
    )
    p_save.add_argument(
        "--final-note",
        type=str,
        default=None,
        help="Optional final note summarizing the experiment.",
    )
    p_save.add_argument(
        "--no-update-git",
        action="store_true",
        help="Do not refresh Git metadata on save.",
    )
    p_save.set_defaults(func=_cmd_save)

    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
