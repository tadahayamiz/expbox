from __future__ import annotations

import json
from pathlib import Path

import pytest

from expbox.io import load_config, snapshot_config
from expbox.exceptions import ConfigLoadError


def test_load_config_from_mapping() -> None:
    cfg = load_config({"lr": 1e-3, "epochs": 10})
    assert cfg["lr"] == 1e-3
    assert cfg["epochs"] == 10


def test_load_config_from_json_file(tmp_path: Path) -> None:
    path = tmp_path / "config.json"
    data = {"lr": 1e-3, "epochs": 5}
    path.write_text(json.dumps(data), encoding="utf-8")

    cfg = load_config(path)
    assert cfg == data


def test_load_config_missing_file(tmp_path: Path) -> None:
    with pytest.raises(ConfigLoadError):
        load_config(tmp_path / "missing.yaml")


def test_snapshot_config_to_json(tmp_path: Path) -> None:
    dest = tmp_path / "snapshot.json"
    cfg = {"lr": 1e-3, "epochs": 10}

    snapshot_config(cfg, dest)
    text = dest.read_text(encoding="utf-8")

    loaded = json.loads(text)
    assert loaded == cfg


def test_snapshot_and_load_yaml_if_available(tmp_path: Path) -> None:
    yaml = pytest.importorskip("yaml")

    dest = tmp_path / "snapshot.yaml"
    cfg = {"lr": 1e-3, "epochs": 10}

    snapshot_config(cfg, dest)
    text = dest.read_text(encoding="utf-8")

    loaded = yaml.safe_load(text)
    assert loaded == cfg

    # Round-trip load_config from YAML file
    cfg2 = load_config(dest)
    assert cfg2 == cfg
