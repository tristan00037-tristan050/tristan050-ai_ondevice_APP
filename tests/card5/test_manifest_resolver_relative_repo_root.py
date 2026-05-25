from pathlib import Path

import pytest

from src.butler.card5.manifest_resolver import (
    ManifestResolutionError,
    resolve_option_d_manifest,
)


def test_manifest_resolver_relative_repo_root_uses_single_root(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)

    repo = tmp_path / "repo"
    manifest = repo / "evidence" / "card5_lora_v3_3" / "option_d_manifest_v5.json"
    manifest.parent.mkdir(parents=True)
    manifest.write_text('{"schema_version":"card5.option_d_manifest.v5"}', encoding="utf-8")

    resolved = resolve_option_d_manifest(repo_root=Path("repo"))

    assert resolved == manifest.resolve()
    assert "repo/repo" not in resolved.as_posix()


def test_manifest_resolver_absolute_repo_root(tmp_path):
    repo = tmp_path / "repo"
    manifest = repo / "evidence" / "card5_lora_v3_3" / "option_d_manifest_v5.json"
    manifest.parent.mkdir(parents=True)
    manifest.write_text('{"schema_version":"card5.option_d_manifest.v5"}', encoding="utf-8")

    resolved = resolve_option_d_manifest(repo_root=repo.resolve())

    assert resolved == manifest.resolve()


def test_manifest_resolver_env_var_relative_path_is_root_relative(tmp_path, monkeypatch):
    repo = tmp_path / "repo"
    manifest = repo / "evidence" / "card5_lora_v3_3" / "option_d_manifest_v5.json"
    manifest.parent.mkdir(parents=True)
    manifest.write_text('{"schema_version":"card5.option_d_manifest.v5"}', encoding="utf-8")

    monkeypatch.setenv(
        "BUTLER_CARD5_OPTION_D_MANIFEST",
        "evidence/card5_lora_v3_3/option_d_manifest_v5.json",
    )

    resolved = resolve_option_d_manifest(repo_root=repo)

    assert resolved == manifest.resolve()


def test_manifest_resolver_explicit_relative_path_is_root_relative(tmp_path):
    repo = tmp_path / "repo"
    manifest = repo / "custom" / "manifest.json"
    manifest.parent.mkdir(parents=True)
    manifest.write_text('{"schema_version":"card5.option_d_manifest.v5"}', encoding="utf-8")

    resolved = resolve_option_d_manifest(
        repo_root=repo,
        explicit_path="custom/manifest.json",
    )

    assert resolved == manifest.resolve()


def test_manifest_resolver_missing_raises_typed_error(tmp_path):
    with pytest.raises(ManifestResolutionError) as exc:
        resolve_option_d_manifest(repo_root=tmp_path / "repo")

    assert "CARD5_OPTION_D_MANIFEST_NOT_FOUND" in str(exc.value)
