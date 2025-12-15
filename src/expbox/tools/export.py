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

from ..io import load_meta, load_config, load_index_record  # read-only loaders


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


def flatten_index_record(record: Dict[str, Any]) -> Dict[str, Any]:
    """
    Convert a structured index record into a flat row for CSV/Notion.

    This preserves your current column schema as much as possible.
    """
    row: Dict[str, Any] = {}

    row["exp_id"] = record.get("exp_id")
    row["project"] = record.get("project")
    row["title"] = record.get("title")
    row["purpose"] = record.get("purpose")
    row["status"] = record.get("status")
    row["created_at"] = record.get("created_at")
    row["finished_at"] = record.get("finished_at")

    paths = record.get("paths") or {}
    # keep compatibility with existing export columns:
    # results_path/config_path were absolute before; now use rel paths
    row["results_path"] = paths.get("box_rel") or ""
    cfg_rel = paths.get("config_rel") or ""
    row["config_path"] = (f"{paths.get('box_rel')}/{cfg_rel}" if cfg_rel else "")

    git = record.get("git") or {}
    gstart = (git.get("start") or {})
    glast = (git.get("last") or {})

    row["git_start_commit"] = gstart.get("commit")
    row["git_last_commit"] = glast.get("commit")
    row["git_start_branch"] = gstart.get("branch")
    row["git_last_branch"] = glast.get("branch")
    row["git_start_subject"] = gstart.get("subject")
    row["git_last_subject"] = glast.get("subject")

    # dirty_files: optional (safe may omit it)
    dirty_files = record.get("dirty_files") or {}
    files = dirty_files.get("files")
    if isinstance(files, list):
        row["dirty_files"] = ",".join(files)
    else:
        row["dirty_files"] = ""

    env_auto = record.get("env_auto") or {}
    row["env_platform"] = env_auto.get("platform")
    row["env_gpu"] = str(env_auto.get("gpu"))
    row["env_cuda_visible_devices"] = env_auto.get("cuda_visible_devices")

    row["env_note"] = record.get("env_note")
    row["final_note"] = record.get("final_note")

    cfgd = record.get("config_derived") or {}
    ds = cfgd.get("dataset") or {}
    row["cfg_dataset_name"] = ds.get("name")
    row["cfg_dataset_path"] = ds.get("path")
    row["cfg_dataset_version"] = ds.get("version")

    row["logger_backend"] = record.get("logger_backend")

    return row


def summarize_box(box_root: Path) -> Dict[str, Any]:
    """
    Build a structured summary record for a single experiment box.

    Priority:
    1) If .expbox/index/<exp_id>.json exists, use it.
    2) Otherwise, build a record from meta.json + config snapshot (read-only).
    """
    box_root = box_root.resolve()
    exp_id = box_root.name

    idx = load_index_record(exp_id)
    if isinstance(idx, dict) and idx.get("exp_id") == exp_id:
        return idx

    meta = load_meta(box_root)
    extra = getattr(meta, "extra", None) or {}
    env_auto = extra.get("env_auto") or {}

    git_section: Dict[str, Any] = dict(meta.git or {})
    git_start = dict(git_section.get("start") or {})
    git_last = dict(git_section.get("last") or {})

    cfg = _load_config_snapshot(box_root, meta)
    dataset = cfg.get("dataset") or {} if isinstance(cfg, dict) else {}

    # Build a structured record (full-ish) similar to what api.save_exp writes.
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
            "project_root_rel": ".",
            "box_rel": str(box_root),
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
        "dirty_files": {"files": git_section.get("dirty_files") or []},
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
    records = summarize_boxes(results_root)
    rows = [flatten_index_record(r) for r in records]
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
