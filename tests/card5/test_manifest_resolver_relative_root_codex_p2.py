from __future__ import annotations

import json
from pathlib import Path

import pytest

from butler.card5.manifest_resolver import resolve_option_d_manifest


def _write_manifest(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({"schema_version": "test"}), encoding="utf-8")


def test_relative_repo_root_no_double_join(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    repo_dir = tmp_path / "repo"
    manifest_file = repo_dir / "evidence/card5_lora_v3_3/option_d_manifest_v5.json"
    _write_manifest(manifest_file)

    monkeypatch.chdir(tmp_path)
    result = resolve_option_d_manifest(Path("repo"))

    assert result.exists()
    assert "repo/repo" not in str(result)
    assert result.resolve() == manifest_file.resolve()


def test_absolute_repo_root_still_resolves(tmp_path: Path):
    manifest_file = tmp_path / "evidence/card5_lora_v3_3/option_d_manifest_v5.json"
    _write_manifest(manifest_file)

    result = resolve_option_d_manifest(tmp_path)

    assert result.resolve() == manifest_file.resolve()


def test_nested_relative_repo_root_no_double_join(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    nested_root = tmp_path / "parent" / "repo"
    manifest_file = nested_root / "evidence/card5_lora_v3_3/option_d_manifest_v5.json"
    _write_manifest(manifest_file)

    monkeypatch.chdir(tmp_path)
    result = resolve_option_d_manifest(Path("parent/repo"))

    assert result.exists()
    assert "parent/repo/parent/repo" not in str(result)
    assert result.resolve() == manifest_file.resolve()


def test_relative_root_v3_fallback(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    repo_dir = tmp_path / "repo"
    manifest_file = repo_dir / "evidence/card5_lora_v3_3/option_d_manifest_v3.json"
    _write_manifest(manifest_file)

    monkeypatch.chdir(tmp_path)
    result = resolve_option_d_manifest(Path("repo"))

    assert result.resolve() == manifest_file.resolve()
