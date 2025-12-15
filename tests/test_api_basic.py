from __future__ import annotations

from pathlib import Path
from datetime import datetime
import os
import json

import expbox as xb


def test_init_creates_structure(tmp_path: Path) -> None:
    os.chdir(tmp_path)

    ctx = xb.init(
        project="testproj",
        config={"lr": 1e-3},
        results_root=tmp_path,
        logger="none",
    )

    # root exists
    assert ctx.paths.root.exists()
    assert ctx.paths.artifacts.exists()
    assert ctx.paths.logs.exists()
    assert ctx.paths.figures.exists()
    assert ctx.paths.notebooks.exists()

    # meta.json exists
    meta_path = ctx.paths.root / "meta.json"
    assert meta_path.exists()

    # config snapshot exists
    cfg_snapshot = ctx.paths.artifacts / "config.yaml"
    assert cfg_snapshot.exists()

    # basic meta fields
    assert ctx.meta.exp_id == ctx.exp_id
    assert ctx.meta.project == "testproj"
    assert ctx.meta.config_path == "artifacts/config.yaml"


def test_load_roundtrip(tmp_path: Path) -> None:
    os.chdir(tmp_path)

    # init
    ctx = xb.init(
        project="roundtripproj",
        config={"lr": 1e-3, "epochs": 10},
        results_root=tmp_path,
        logger="none",
    )

    exp_id = ctx.exp_id

    # modify meta, save
    ctx.meta.final_note = "done"
    xb.save(ctx)

    # load
    ctx2 = xb.load(exp_id=exp_id, results_root=tmp_path)

    assert ctx2.exp_id == exp_id
    assert ctx2.meta.project == "roundtripproj"
    assert ctx2.config["lr"] == 1e-3
    assert ctx2.meta.final_note == "done"


def test_save_sets_finished_at(tmp_path: Path) -> None:
    os.chdir(tmp_path)

    ctx = xb.init(
        project="finishproj",
        config={},
        results_root=tmp_path,
        logger="none",
    )

    assert ctx.meta.finished_at is None
    xb.save(ctx)
    assert ctx.meta.finished_at is not None

    # sanity check: ISO 8601-like
    dt = datetime.fromisoformat(ctx.meta.finished_at)
    assert isinstance(dt, datetime)

    # check that finished_at is updated on subsequent saves
    index_path = tmp_path / ".expbox" / "index" / f"{ctx.exp_id}.json"
    assert index_path.exists()

    # load index record
    data = json.loads(index_path.read_text())
    assert "dirty_files" not in data


def test_active_box_shortcuts(tmp_path: Path) -> None:
    os.chdir(tmp_path)

    ctx = xb.init(
        project="testproj",
        config={"lr": 1e-3},
        results_root=tmp_path,
        logger="none",
    )

    assert xb.exp_id == ctx.exp_id
    assert xb.paths.root == ctx.paths.root
    assert xb.meta.project == "testproj"
    assert xb.config["lr"] == 1e-3

    xb.meta.final_note = "done"
    xb.save()
    assert xb.meta.final_note == "done"


def test_save_verbose_prints_summary(tmp_path: Path, capsys) -> None:
    os.chdir(tmp_path)
    ctx = xb.init(project="vprint", config={}, results_root=tmp_path, logger="none")
    xb.save(ctx)  # default verbose=True
    out = capsys.readouterr().out
    assert "[expbox] saved" in out
    assert ctx.exp_id in out
