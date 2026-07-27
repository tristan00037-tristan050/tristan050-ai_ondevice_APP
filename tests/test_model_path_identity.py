from __future__ import annotations

import importlib
import sys
from pathlib import Path

import pytest

_REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(_REPO_ROOT))

from butler_pc_core.inference.model_identity import (
    BOX3_MODEL_NAME,
    BOX3_MODEL_PATH_ENV,
    FREE_CHAT_MODEL_NAME,
    MAIN_EQUALS_BOX3,
    MAIN_MODEL_PATH_ENV,
    MAIN_USES_BOX3,
    assert_main_not_box3,
    is_box3_model_path,
    model_path_conflict_reason,
    sidecar_model_status_payload,
)

pytestmark = pytest.mark.no_sidecar_token


def test_model_path_identity_detects_box3_model_forbidden_as_main():
    env = {
        MAIN_MODEL_PATH_ENV: f"/Applications/Butler.app/Contents/Resources/models/box3/{BOX3_MODEL_NAME}",
    }

    assert is_box3_model_path(env[MAIN_MODEL_PATH_ENV])
    assert model_path_conflict_reason(env) == MAIN_USES_BOX3
    with pytest.raises(RuntimeError, match=MAIN_USES_BOX3):
        assert_main_not_box3(env)


def test_model_path_identity_detects_equal_main_and_box3_paths():
    shared = "/tmp/butler/models/shared.gguf"
    env = {
        MAIN_MODEL_PATH_ENV: shared,
        BOX3_MODEL_PATH_ENV: shared,
    }

    assert model_path_conflict_reason(env) == MAIN_EQUALS_BOX3


def test_model_path_status_payload_is_digest_only(tmp_path):
    main = tmp_path / "models" / FREE_CHAT_MODEL_NAME
    box3 = tmp_path / "models" / "box3" / BOX3_MODEL_NAME
    main.parent.mkdir(parents=True)
    box3.parent.mkdir(parents=True)
    main.write_bytes(b"main")
    box3.write_bytes(b"box3")
    env = {
        MAIN_MODEL_PATH_ENV: str(main),
        BOX3_MODEL_PATH_ENV: str(box3),
    }

    payload = sidecar_model_status_payload(status="ready", environ=env)

    assert payload["status"] == "ready"
    assert payload["model_role"] == "free_chat"
    assert payload["model_family"] == "qwen3-4b"
    assert payload["model_path_digest"].startswith("sha256:")
    assert payload["model_path_conflict"] is False
    assert str(tmp_path) not in repr(payload)
    assert payload["box3_model"]["model_role"] == "box3_canonical"
    assert payload["box3_model"]["model_family"] == "butler-1.7b-v9.2-r2b"


def test_sidecar_model_status_ignores_raw_model_path_environment(tmp_path, monkeypatch):
    main = tmp_path / "models" / FREE_CHAT_MODEL_NAME
    box3 = tmp_path / "models" / "box3" / BOX3_MODEL_NAME
    main.parent.mkdir(parents=True)
    box3.parent.mkdir(parents=True)
    main.write_bytes(b"main")
    box3.write_bytes(b"box3")
    monkeypatch.setenv(MAIN_MODEL_PATH_ENV, str(main))
    monkeypatch.setenv(BOX3_MODEL_PATH_ENV, str(box3))

    import butler_sidecar

    sidecar = importlib.reload(butler_sidecar)
    sidecar._SHARED_LLM = None
    from fastapi.testclient import TestClient

    response = TestClient(sidecar.app).get("/api/model/status")
    payload = response.json()

    assert response.status_code == 200
    assert "model_path" not in payload
    assert str(tmp_path) not in response.text
    assert payload["model_role"] == "free_chat"
    assert payload["model_family"] == ""
    assert payload["model_present"] is False
    assert payload["box3_model"]["model_family"] == ""
    assert payload["box3_model"]["model_present"] is False


def test_sidecar_init_shared_llm_does_not_fallback_to_main_model_env(tmp_path, monkeypatch):
    box3 = tmp_path / "models" / "box3" / BOX3_MODEL_NAME
    box3.parent.mkdir(parents=True)
    box3.write_bytes(b"box3")
    monkeypatch.setenv(MAIN_MODEL_PATH_ENV, str(box3))

    import butler_sidecar

    sidecar = importlib.reload(butler_sidecar)
    sidecar._SHARED_LLM = None

    sidecar._init_shared_llm()
    assert sidecar._SHARED_LLM.status == "no_model"
    assert sidecar._SHARED_LLM_ASSET_LEASE is None
