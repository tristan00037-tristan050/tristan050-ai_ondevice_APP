from __future__ import annotations

import json
import os
import subprocess
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[1]
pytestmark = pytest.mark.no_sidecar_token


def _runtime_env(tmp_path: Path, model_src: Path) -> dict[str, str]:
    env = os.environ.copy()
    env.update(
        {
            "BUTLER_BUNDLE_MODEL_SRC": str(model_src),
            "BUTLER_BUNDLE_MODELS_DIR": str(tmp_path / "models"),
            "BUTLER_BUNDLE_RUNTIME_DIR": str(tmp_path / "python-runtime"),
            "HOME": str(tmp_path / "home"),
        }
    )
    return env


def _run_build_runtime(tmp_path: Path, model_src: Path, **extra_env: str) -> subprocess.CompletedProcess[str]:
    env = _runtime_env(tmp_path, model_src)
    env.update(extra_env)
    return subprocess.run(
        ["bash", "scripts/build_runtime.sh", "--model-only"],
        cwd=ROOT,
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )


def test_tauri_before_build_generates_ignored_runtime_resources() -> None:
    conf = json.loads((ROOT / "butler-desktop/src-tauri/tauri.conf.json").read_text(encoding="utf-8"))

    before_build = conf["build"]["beforeBuildCommand"]
    assert "npm run build" in before_build
    assert "../scripts/build_runtime.sh" in before_build
    assert conf["bundle"]["resources"]["python-runtime"] == "python"
    assert conf["bundle"]["resources"]["models"] == "models"


def test_build_runtime_fails_when_required_model_source_is_missing(tmp_path: Path) -> None:
    missing_model = tmp_path / "missing-qwen3-4b-q4_k_m.gguf"

    proc = _run_build_runtime(tmp_path, missing_model)

    assert proc.returncode == 1
    assert "ERROR: 원본 모델을 찾지 못함" in proc.stdout
    assert "BUTLER_ALLOW_MISSING_BUNDLE_MODEL=1" in proc.stdout
    assert not (tmp_path / "models").exists()


def test_build_runtime_allows_missing_model_only_when_explicitly_requested(tmp_path: Path) -> None:
    missing_model = tmp_path / "missing-qwen3-4b-q4_k_m.gguf"

    proc = _run_build_runtime(tmp_path, missing_model, BUTLER_ALLOW_MISSING_BUNDLE_MODEL="1")

    assert proc.returncode == 0, proc.stdout + proc.stderr
    assert "명시적으로 건너뜁니다" in proc.stdout
    assert (tmp_path / "models").is_dir()


def test_build_runtime_copies_model_from_configured_source(tmp_path: Path) -> None:
    model_src = tmp_path / "source.gguf"
    model_src.write_bytes(b"fake-gguf")

    proc = _run_build_runtime(tmp_path, model_src)

    assert proc.returncode == 0, proc.stdout + proc.stderr
    assert (tmp_path / "models/qwen3-4b-q4_k_m.gguf").read_bytes() == b"fake-gguf"
