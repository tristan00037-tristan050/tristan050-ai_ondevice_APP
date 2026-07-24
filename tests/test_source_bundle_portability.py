from __future__ import annotations

import importlib.util
import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

pytestmark = pytest.mark.no_sidecar_token

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location(
    "verify_source_bundle",
    ROOT / "scripts/release/verify_source_bundle.py",
)
assert SPEC and SPEC.loader
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


@pytest.mark.parametrize(
    "paths",
    [
        ["source/AI온디바이스/README.md", "source/AI온디바이스/README.md"],
        ["source/Readme.md", "source/README.md"],
        ["source/straße.md", "source/STRASSE.md"],
    ],
)
def test_portable_identity_rejects_normalization_and_case_collisions(paths: list[str]) -> None:
    with pytest.raises(MODULE.SourceBundleVerificationError) as caught:
        MODULE._require_portable_unique(paths, "SOURCE_ARCHIVE_PORTABLE_PATH_COLLISION")
    assert str(caught.value) == "SOURCE_ARCHIVE_PORTABLE_PATH_COLLISION"


@pytest.mark.parametrize(
    "path",
    [
        "source/CON.txt",
        "source/COM¹.log",
        "source/CONOUT$.txt",
        "source/report. ",
        "source/report.",
        "source/report:stream.txt",
        "source/question?.md",
        "source/control\u0001.md",
    ],
)
def test_portable_identity_rejects_ntfs_unsafe_components(path: str) -> None:
    with pytest.raises(MODULE.SourceBundleVerificationError, match="PORTABLE_PATH_INVALID"):
        MODULE._safe_relative_path(path)


def _git(repo: Path, *arguments: str, stdin: bytes | None = None) -> str:
    environment = {
        **os.environ,
        "GIT_AUTHOR_NAME": "Fixture",
        "GIT_AUTHOR_EMAIL": "fixture@example.invalid",
        "GIT_COMMITTER_NAME": "Fixture",
        "GIT_COMMITTER_EMAIL": "fixture@example.invalid",
        "GIT_AUTHOR_DATE": "2001-01-01T00:00:00Z",
        "GIT_COMMITTER_DATE": "2001-01-01T00:00:00Z",
    }
    return subprocess.run(
        ["git", *arguments],
        cwd=repo,
        input=stdin,
        check=True,
        capture_output=True,
        env=environment,
    ).stdout.decode("ascii").strip()


def test_builder_rejects_case_collision_from_git_objects_on_case_insensitive_hosts(
    tmp_path: Path,
) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    _git(repo, "init", "-q")
    package = repo / "butler-desktop/package.json"
    package.parent.mkdir()
    package.write_text(json.dumps({"version": "0.9.0"}), encoding="utf-8")
    blob = _git(repo, "hash-object", "-w", "--stdin", stdin=b"same\n")
    baseline_tree = _git(repo, "mktree", stdin=f"100644 blob {blob}\tREADME.md\n".encode())
    baseline = _git(repo, "commit-tree", baseline_tree, stdin=b"baseline\n")
    collision_tree = _git(
        repo,
        "mktree",
        stdin=(
            f"100644 blob {blob}\tREADME.md\n"
            f"100644 blob {blob}\tReadme.md\n"
        ).encode(),
    )
    target = _git(repo, "commit-tree", collision_tree, "-p", baseline, stdin=b"collision\n")

    result = subprocess.run(
        [
            sys.executable,
            str(ROOT / "scripts/release/build_safe_source_archive.py"),
            "--commit",
            target,
            "--scope-baseline",
            baseline,
            "--output",
            str(tmp_path / "source.zip"),
            "--manifest",
            str(tmp_path / "manifest.json"),
        ],
        cwd=repo,
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode != 0
    assert "portable path collision" in result.stderr
