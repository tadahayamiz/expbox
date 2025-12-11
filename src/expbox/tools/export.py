from __future__ import annotations

"""
Export helpers for expbox experiments.

This module provides *read-only* utilities that summarize experiment
"boxes" (directories under ``results_root/``) into flat records suitable
for:

- CSV export
- Notion / spreadsheet imports
- Lightweight reporting scripts

Design principles
-----------------
- Do not affect experiment lifecycle or modify any files.
- Depend only on the core I/O layer (:mod:`expbox.io`) and standard
  library modules.
- Keep the output schema simple and stable: one record per box, with
  flat key/value fields.
"""

import csv
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional

from ..io import load_meta, load_config  # ExpMeta + config snapshot loader


# ---------------------------------------------------------------------------
# Box discovery
# ---------------------------------------------------------------------------


def iter_boxes(results_root: Path) -> Iterable[Path]:
    """
    Yield experiment box directories under ``results_root`` that contain
    a ``meta.json`` file.

    Parameters
    ----------
    results_root:
        Root directory under which experiment boxes are stored. Each box
        lives in a subdirectory named by its ``exp_id`` and containing
        a ``meta.json`` file.

    Yields
    ------
    Path
        Paths to experiment root directories.
    """
    results_root = results_root.resolve()
    if not results_root.exists():
        return
    for p in sorted(results_root.iterdir()):
        if not p.is_dir():
            continue
        if (p / "meta.json").exists():
            yield p


# ---------------------------------------------------------------------------
# Single-box summarization
# ---------------------------------------------------------------------------


def _load_config_snapshot(box_root: Path, meta: Any) -> Dict[str, Any]:
    """
    Best-effort load of the config snapshot for a given box.

    Returns an empty dict if the snapshot is missing or cannot be loaded.
    """
    # ExpMeta has a config_path attribute; fall back to the default if absent.
    rel = getattr(meta, "config_path", None) or "artifacts/config.yaml"
    cfg_path = box_root / rel
    if not cfg_path.exists():
        return {}
    try:
        # ``load_config`` accepts a Path as ConfigLike.
        return load_config(cfg_path)  # type: ignore[arg-type]
    except Exception:
        return {}


def summarize_box(box_root: Path) -> Dict[str, Any]:
    """
    Build a flat summary record for a single experiment box.

    The record is intended to be used as a single CSV row or as a
    "Notion row" for an experiment database. It flattens information
    from:

    - ``meta.json`` (via :func:`expbox.io.load_meta`)
    - the config snapshot (if available, via ``config_path``)
    - auto-collected environment info (``meta.extra['env_auto']` if present)

    Parameters
    ----------
    box_root:
        Root directory of the experiment (e.g. ``results/<exp_id>``).

    Returns
    -------
    dict
        Flat mapping of field names to values.
    """
    box_root = box_root.resolve()
    meta = load_meta(box_root)

    # ExpMeta has .extra; if that ever changes, we can still fall back gracefully.
    extra = getattr(meta, "extra", None) or {}
    env_auto = extra.get("env_auto") or {}

    git_section: Dict[str, Any] = dict(meta.git or {})
    git_start = git_section.get("start") or {}
    git_last = git_section.get("last") or {}

    cfg = _load_config_snapshot(box_root, meta)
    dataset = cfg.get("dataset") or {} if isinstance(cfg, dict) else {}

    row: Dict[str, Any] = {}

    # Core metadata
    row["exp_id"] = meta.exp_id
    row["project"] = meta.project
    row["title"] = meta.title
    row["purpose"] = meta.purpose
    row["status"] = meta.status
    row["created_at"] = meta.created_at
    row["finished_at"] = meta.finished_at

    # Paths
    row["results_path"] = str(box_root)
    if meta.config_path:
        row["config_path"] = str(box_root / meta.config_path)
    else:
        row["config_path"] = ""

    # Git (best-effort)
    row["git_start_commit"] = git_start.get("commit")
    row["git_last_commit"] = git_last.get("commit")
    row["git_start_branch"] = git_start.get("branch")
    row["git_last_branch"] = git_last.get("branch")

    dirty_start = git_start.get("dirty_files") or git_section.get("dirty_files") or []
    dirty_last = git_last.get("dirty_files") or git_section.get("dirty_files") or []
    if isinstance(dirty_start, list):
        row["dirty_files_start"] = ",".join(dirty_start)
    else:
        row["dirty_files_start"] = str(dirty_start) if dirty_start else ""
    if isinstance(dirty_last, list):
        row["dirty_files_last"] = ",".join(dirty_last)
    else:
        row["dirty_files_last"] = str(dirty_last) if dirty_last else ""

    # Environment (auto + manual)
    row["env_platform"] = env_auto.get("platform")
    row["env_gpu"] = str(env_auto.get("gpu"))
    row["env_cuda_visible_devices"] = env_auto.get("cuda_visible_devices")
    row["env_note"] = meta.env_note

    # Notes
    row["final_note"] = meta.final_note

    # Config-derived (optional / best-effort)
    if isinstance(dataset, dict):
        row["cfg_dataset_name"] = dataset.get("name")
        row["cfg_dataset_path"] = dataset.get("path")
        row["cfg_dataset_version"] = dataset.get("version")
    else:
        row["cfg_dataset_name"] = None
        row["cfg_dataset_path"] = None
        row["cfg_dataset_version"] = None

    return row


# ---------------------------------------------------------------------------
# Multi-box summarization
# ---------------------------------------------------------------------------


def summarize_boxes(results_root: str | Path = "results") -> List[Dict[str, Any]]:
    """
    Summarize all experiment boxes under ``results_root`` into flat records.

    Parameters
    ----------
    results_root:
        Directory containing experiment boxes (default: "results").

    Returns
    -------
    list of dict
        Each dict is the output of :func:`summarize_box` for one box.
    """
    root = Path(results_root).resolve()
    return [summarize_box(p) for p in iter_boxes(root)]


# ---------------------------------------------------------------------------
# CSV export
# ---------------------------------------------------------------------------


def export_csv(
    results_root: str | Path = "results",
    csv_path: str | Path = "expbox_experiments.csv",
    fields: Optional[List[str]] = None,
) -> Path:
    """
    Scan all boxes under ``results_root`` and export a flat CSV summary.

    This is a convenience wrapper around :func:`summarize_boxes`. The
    resulting CSV is designed to be easy to import into Notion or other
    tabular tools (one row per experiment).

    Parameters
    ----------
    results_root:
        Directory containing experiment boxes (default: "results").
    csv_path:
        Where to write the CSV file (default: "expbox_experiments.csv").
    fields:
        Optional explicit list of fieldnames (column order). If omitted,
        the union of keys across all records is used, preserving the
        order in which keys first appear.

    Returns
    -------
    Path
        The resolved path to the written CSV file.
    """
    rows = summarize_boxes(results_root)
    csv_path = Path(csv_path).resolve()

    if not rows:
        # If no rows, write just a header if fields are provided; otherwise
        # create an empty file.
        if fields:
            with csv_path.open("w", newline="", encoding="utf-8") as f:
                writer = csv.DictWriter(f, fieldnames=fields)
                writer.writeheader()
        else:
            csv_path.touch()
        return csv_path

    if fields is None:
        # Stable union of keys: order by first appearance.
        keys: List[str] = []
        seen: set[str] = set()
        for row in rows:
            for k in row.keys():
                if k not in seen:
                    seen.add(k)
                    keys.append(k)
        fields = keys

    with csv_path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fields)
        writer.writeheader()
        for row in rows:
            writer.writerow({k: row.get(k, "") for k in fields})

    return csv_path


__all__ = [
    "iter_boxes",
    "summarize_box",
    "summarize_boxes",
    "export_csv",
]
