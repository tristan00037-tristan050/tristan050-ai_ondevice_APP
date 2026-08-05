from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "scripts/ci/helper1_assert_start_tree.py"


def _git(repo: Path, *args: str) -> str:
    return subprocess.run(
        ["git", "-C", str(repo), *args], check=True, capture_output=True, text=True
    ).stdout.strip()


def _repository(tmp_path: Path) -> tuple[Path, str, str]:
    repo = tmp_path / "repo"
    repo.mkdir()
    _git(repo, "init", "-q")
    _git(repo, "config", "user.email", "test@example.invalid")
    _git(repo, "config", "user.name", "Test")
    (repo / "tracked.txt").write_text("baseline\n", encoding="utf-8")
    _git(repo, "add", "tracked.txt")
    _git(repo, "commit", "-qm", "baseline")
    return repo, _git(repo, "rev-parse", "HEAD"), _git(repo, "rev-parse", "HEAD^{tree}")


def _run(repo: Path, commit: str, tree: str, output: Path) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [
            sys.executable,
            str(SCRIPT),
            "--repository",
            str(repo),
            "--expected-tree",
            tree,
            "--expected-commit",
            commit,
            "--output",
            str(output),
        ],
        capture_output=True,
        text=True,
    )


def test_start_tree_positive_and_dirty_fail_closed(tmp_path: Path) -> None:
    repo, commit, tree = _repository(tmp_path)
    output = tmp_path / "positive.json"
    completed = _run(repo, commit, tree, output)
    assert completed.returncode == 0
    verdict, error = completed.stdout.splitlines()
    assert verdict.partition("=") == ("HELPER1_START_TREE_OK", "=", "1")
    assert error == "ERROR_CODE=NONE"
    assert json.loads(output.read_text())["verified"] is True
    (repo / "tracked.txt").write_text("changed\n", encoding="utf-8")
    dirty = _run(repo, commit, tree, tmp_path / "dirty.json")
    assert dirty.returncode == 42
    assert "ERROR_CODE=START_TREE_DIRTY" in dirty.stdout


def test_start_tree_wrong_commit_binding_fails(tmp_path: Path) -> None:
    repo, commit, tree = _repository(tmp_path)
    wrong = _run(repo, commit, "f" * 40, tmp_path / "wrong.json")
    assert wrong.returncode == 42
    assert "ERROR_CODE=START_TREE_MISSING" in wrong.stdout
    mismatched_commit = _run(repo, "e" * 40, tree, tmp_path / "missing.json")
    assert mismatched_commit.returncode == 42
    assert "ERROR_CODE=START_TREE_MISSING" in mismatched_commit.stdout
