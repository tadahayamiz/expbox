from __future__ import annotations

import json
import subprocess
from pathlib import Path


def run(cmd: list[str], cwd: Path) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        cmd,
        cwd=str(cwd),
        text=True,
        capture_output=True,
        check=True,
    )


def git(args: list[str], cwd: Path) -> str:
    return run(["git", *args], cwd=cwd).stdout.strip()


def run_cli(args: list[str], cwd: Path) -> subprocess.CompletedProcess[str]:
    try:
        # reuse existing helper if available
        from tests.test_cli import run_cli as project_run_cli  # type: ignore

        return project_run_cli(args, cwd=cwd)
    except Exception:
        return subprocess.run(
            ["expbox", *args],
            cwd=str(cwd),
            text=True,
            capture_output=True,
        )


def test_git_commit_subject_is_reflected_in_meta_and_index(tmp_path: Path) -> None:
    """
    Verify that:
      - commit hash and commit subject (message) are captured at init
      - the same values are persisted into the per-exp index on save
    """
    repo = tmp_path / "repo"
    repo.mkdir()

    # --- setup dummy git repo ---
    git(["init", "-q"], cwd=repo)
    git(["config", "user.name", "expbox-test"], cwd=repo)
    git(["config", "user.email", "expbox-test@example.com"], cwd=repo)

    remote_url = "https://github.com/dummy/dummy.git"
    git(["remote", "add", "origin", remote_url], cwd=repo)

    commit_subject = "test: capture commit subject in expbox"
    (repo / "hello.txt").write_text("hello\n", encoding="utf-8")
    git(["add", "hello.txt"], cwd=repo)
    git(["commit", "-qm", commit_subject], cwd=repo)

    head = git(["rev-parse", "HEAD"], cwd=repo)

    # --- expbox init ---
    results_root = repo / "results"
    results_root.mkdir()

    r_init = run_cli(
        [
            "init",
            "--project", "gitstamp",
            "--results-root", str(results_root),
            "--logger", "none",
        ],
        cwd=repo,
    )
    assert r_init.returncode == 0, r_init.stderr
    exp_id = r_init.stdout.strip()
    assert exp_id

    meta_path = results_root / exp_id / "meta.json"
    meta = json.loads(meta_path.read_text(encoding="utf-8"))

    git_meta = meta.get("git") or {}
    start = git_meta.get("start") or {}
    last = git_meta.get("last") or {}

    # --- meta.json assertions ---
    assert start.get("commit") == head
    assert start.get("subject") == commit_subject
    assert last.get("commit") == head
    assert last.get("subject") == commit_subject

    # --- expbox save (writes index) ---
    r_save = run_cli(
        [
            "save",
            exp_id,
            "--results-root", str(results_root),
            "--status", "done",
            "--final-note", "git subject test",
            "--logger", "none",
        ],
        cwd=repo,
    )
    assert r_save.returncode == 0, r_save.stderr

    index_path = repo / ".expbox" / "index" / f"{exp_id}.json"
    assert index_path.exists(), f"index record missing: {index_path}"

    idx = json.loads(index_path.read_text(encoding="utf-8"))
    idx_git = idx.get("git") or {}

    idx_start = idx_git.get("start") or {}
    idx_last = idx_git.get("last") or {}

    # --- index assertions ---
    assert idx_start.get("commit") == head
    assert idx_start.get("subject") == commit_subject
    assert idx_last.get("commit") == head
    assert idx_last.get("subject") == commit_subject