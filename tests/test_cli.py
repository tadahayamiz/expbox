from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path


PYTHON = sys.executable  # use the same Python running pytest


def run_cli(args, cwd: Path):
    """
    Helper to run: python -m expbox.cli <args>
    Returns CompletedProcess
    """
    cmd = [PYTHON, "-m", "expbox.cli"] + args
    return subprocess.run(
        cmd,
        cwd=cwd,
        capture_output=True,
        text=True,
        check=False,  # we'll assert manually
    )


def test_cli_init_and_load(tmp_path: Path) -> None:
    # 1. init
    result = run_cli(
        [
            "init",
            "--project", "cli-test",
            "--config", json.dumps({"lr": 1e-3}),
            "--results-root", str(tmp_path),
            "--logger", "none",
        ],
        cwd=tmp_path,
    )
    assert result.returncode == 0
    exp_id = result.stdout.strip()
    assert exp_id  # exp_id printed

    # 2. load
    result2 = run_cli(
        [
            "load",
            exp_id,
            "--results-root", str(tmp_path),
            "--logger", "none",
        ],
        cwd=tmp_path,
    )
    assert result2.returncode == 0
    data = json.loads(result2.stdout)
    assert data["exp_id"] == exp_id
    assert data["project"] == "cli-test"
    assert "created_at" in data


def test_cli_save(tmp_path: Path) -> None:
    # init
    result = run_cli(
        [
            "init",
            "--project", "cli-save",
            "--config", json.dumps({"lr": 1e-3}),
            "--results-root", str(tmp_path),
            "--logger", "none",
        ],
        cwd=tmp_path,
    )
    exp_id = result.stdout.strip()

    # save
    result2 = run_cli(
        [
            "save",
            exp_id,
            "--results-root", str(tmp_path),
            "--logger", "none",
            "--status", "done",
            "--final-note", "ok",
        ],
        cwd=tmp_path,
    )
    assert result2.returncode == 0

    # load back to confirm save
    result3 = run_cli(
        [
            "load",
            exp_id,
            "--results-root", str(tmp_path),
            "--logger", "none",
        ],
        cwd=tmp_path,
    )
    meta = json.loads(result3.stdout)
    assert meta["status"] == "done"


def test_cli_export_csv(tmp_path: Path) -> None:
    import time
    # init 2 experiments
    exp_ids = []
    for name in ["expA", "expB"]:
        r = run_cli(
            [
                "init",
                "--project", name,
                "--config", json.dumps({"lr": 1e-3}),
                "--results-root", str(tmp_path),
                "--logger", "none",
            ],
            cwd=tmp_path,
        )
        exp_ids.append(r.stdout.strip())
        time.sleep(2)  # ensure different timestamps

    # export csv
    out_csv = tmp_path / "expbox_export.csv"
    r2 = run_cli(
        [
            "export-csv",
            "--results-root", str(tmp_path),
            "--output", str(out_csv),
        ],
        cwd=tmp_path,
    )
    assert r2.returncode == 0
    assert out_csv.exists()

    # check content (header + at least 2 data rows)
    lines = out_csv.read_text(encoding="utf-8").splitlines()
    assert len(lines) >= 3  # header + 2 records

    header = lines[0].split(",")
    assert "exp_id" in header
    assert "project" in header


def test_cli_save_without_exp_id_uses_active(tmp_path: Path) -> None:
    # init (this writes .expbox/active because CLI init calls xb.init with default set_active=True)
    r_init = run_cli(
        [
            "init",
            "--project", "cli-save-active",
            "--config", json.dumps({"lr": 1e-3}),
            "--results-root", str(tmp_path),
            "--logger", "none",
        ],
        cwd=tmp_path,
    )
    assert r_init.returncode == 0, r_init.stderr
    exp_id = r_init.stdout.strip()
    assert exp_id

    # save WITHOUT exp_id
    r_save = run_cli(
        [
            "save",
            "--results-root", str(tmp_path),
            "--logger", "none",
            "--status", "done",
            "--final-note", "ok",
        ],
        cwd=tmp_path,
    )
    assert r_save.returncode == 0, r_save.stderr
    # default verbose=True → should print summary
    assert "[expbox] saved" in r_save.stdout
    assert exp_id in r_save.stdout

    # load back
    r_load = run_cli(
        [
            "load",
            exp_id,
            "--results-root", str(tmp_path),
            "--logger", "none",
        ],
        cwd=tmp_path,
    )
    meta = json.loads(r_load.stdout)
    assert meta["status"] == "done"
    assert meta["final_note"] == "ok"


def test_cli_save_quiet_suppresses_output(tmp_path: Path) -> None:
    r_init = run_cli(
        [
            "init",
            "--project", "cli-save-quiet",
            "--config", json.dumps({"lr": 1e-3}),
            "--results-root", str(tmp_path),
            "--logger", "none",
        ],
        cwd=tmp_path,
    )
    exp_id = r_init.stdout.strip()
    assert exp_id

    r_save = run_cli(
        [
            "save",
            "--quiet",
            "--results-root", str(tmp_path),
            "--logger", "none",
            "--status", "done",
        ],
        cwd=tmp_path,
    )
    assert r_save.returncode == 0, r_save.stderr
    assert "[expbox] saved" not in r_save.stdout
