from __future__ import annotations

import json
from pathlib import Path

from expbox.logger import NullLogger, FileLogger


def test_null_logger_does_nothing(tmp_path: Path) -> None:
    logger = NullLogger()

    # log_metrics should not raise
    logger.log_metrics(step=0, loss=1.0)

    # create a dummy file for artifact logging
    dummy = tmp_path / "dummy.txt"
    dummy.write_text("hello", encoding="utf-8")

    # log_artifact should not raise (but also not actually copy anything)
    logger.log_artifact(dummy)

    # close should not raise
    logger.close()


def test_file_logger_writes_metrics_and_artifacts(tmp_path: Path) -> None:
    logs_dir = tmp_path / "logs"
    artifacts_dir = tmp_path / "artifacts"
    logs_dir.mkdir()
    artifacts_dir.mkdir()

    logger = FileLogger(logs_dir=logs_dir, artifacts_dir=artifacts_dir)

    logger.log_metrics(step=1, loss=0.5)
    logger.log_metrics(step=2, loss=0.3, acc=0.8)

    # artifact
    src = tmp_path / "model.pt"
    src.write_bytes(b"dummy-model")
    logger.log_artifact(src)

    logger.close()

    # metrics.jsonl should exist and contain 2 lines
    metrics_path = logs_dir / "metrics.jsonl"
    assert metrics_path.exists()

    lines = metrics_path.read_text(encoding="utf-8").strip().splitlines()
    assert len(lines) == 2

    rec1 = json.loads(lines[0])
    rec2 = json.loads(lines[1])

    assert rec1["step"] == 1
    assert rec1["loss"] == 0.5
    assert rec2["step"] == 2
    assert rec2["acc"] == 0.8

    # artifact should be copied into artifacts_dir
    copied = artifacts_dir / src.name
    assert copied.exists()
    assert copied.read_bytes() == b"dummy-model"
