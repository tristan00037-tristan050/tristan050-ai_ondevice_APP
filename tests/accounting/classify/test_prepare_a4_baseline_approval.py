from __future__ import annotations

import json
import subprocess
from pathlib import Path

import pytest

from scripts.ci.prepare_a4_baseline_approval import (
    BASELINE_SCHEMA,
    MANIFEST_SCHEMA,
    prepare_manifest,
)


def _git(repo: Path, *args: str) -> str:
    completed = subprocess.run(
        ["git", "-C", str(repo), *args],
        check=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    return completed.stdout.strip()


def _commit(repo: Path, message: str, content: str) -> str:
    (repo / "content.txt").write_text(content, encoding="utf-8")
    _git(repo, "add", "content.txt")
    _git(
        repo,
        "-c",
        "user.name=A4 Test",
        "-c",
        "user.email=a4-test@example.invalid",
        "commit",
        "-m",
        message,
    )
    return _git(repo, "rev-parse", "HEAD")


def _repo(tmp_path: Path) -> tuple[Path, str]:
    repo = tmp_path / "repo"
    repo.mkdir()
    _git(repo, "init", "-b", "main")
    return repo, _commit(repo, "base", "base")


def _write_baseline(path: Path, source_head: str) -> None:
    path.write_text(
        json.dumps(
            {
                "entries": [],
                "raw_paths_included": False,
                "raw_values_included": False,
                "schema_version": BASELINE_SCHEMA,
                "source_head": source_head,
            },
            sort_keys=True,
            separators=(",", ":"),
        )
        + "\n",
        encoding="utf-8",
    )


def test_prepare_manifest_accepts_source_on_canonical_history(tmp_path: Path) -> None:
    repo, main_head = _repo(tmp_path)
    _git(repo, "switch", "-c", "feature")
    _commit(repo, "feature", "feature")
    baseline = tmp_path / "baseline.json"
    _write_baseline(baseline, main_head)

    manifest = json.loads(
        prepare_manifest(
            repo=repo,
            baseline_path=baseline,
            source_head=main_head,
            canonical_ref="main",
        )
    )

    assert manifest["schema_version"] == MANIFEST_SCHEMA
    assert manifest["approved_source_head"] == main_head
    assert manifest["entry_count"] == 0


def test_prepare_manifest_rejects_feature_only_source_before_squash(
    tmp_path: Path,
) -> None:
    repo, _ = _repo(tmp_path)
    _git(repo, "switch", "-c", "feature")
    feature_head = _commit(repo, "feature", "feature")
    baseline = tmp_path / "baseline.json"
    _write_baseline(baseline, feature_head)

    with pytest.raises(ValueError, match="git lineage verification failed"):
        prepare_manifest(
            repo=repo,
            baseline_path=baseline,
            source_head=feature_head,
            canonical_ref="main",
        )
