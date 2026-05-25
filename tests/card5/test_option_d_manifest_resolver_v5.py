from __future__ import annotations

import json
from pathlib import Path

import pytest

from butler.card5.manifest_resolver import ManifestResolutionError, resolve_option_d_manifest


def write_manifest(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({"schema_version": "test"}), encoding="utf-8")


def test_manifest_resolver_uses_explicit_path(tmp_path: Path):
    manifest = tmp_path / "explicit.json"
    write_manifest(manifest)
    assert resolve_option_d_manifest(tmp_path, explicit_path=str(manifest)) == manifest


def test_manifest_resolver_uses_env_var(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    manifest = tmp_path / "env.json"
    write_manifest(manifest)
    monkeypatch.setenv("BUTLER_CARD5_OPTION_D_MANIFEST", str(manifest))
    assert resolve_option_d_manifest(tmp_path) == manifest


def test_manifest_resolver_uses_evidence_v5_path(tmp_path: Path):
    manifest = tmp_path / "evidence/card5_lora_v3_3/option_d_manifest_v5.json"
    write_manifest(manifest)
    assert resolve_option_d_manifest(tmp_path) == manifest


def test_manifest_resolver_does_not_require_repo_root_manifest(tmp_path: Path):
    manifest = tmp_path / "evidence/card5_lora_v3_3/option_d_manifest_v3.json"
    write_manifest(manifest)
    assert not (tmp_path / "manifest.json").exists()
    assert resolve_option_d_manifest(tmp_path) == manifest


def test_manifest_resolver_error_is_typed_not_filenotfound(tmp_path: Path):
    with pytest.raises(ManifestResolutionError, match="CARD5_OPTION_D_MANIFEST_NOT_FOUND"):
        resolve_option_d_manifest(tmp_path)

