from __future__ import annotations

import importlib
import sys
from pathlib import Path

import pytest

_REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(_REPO_ROOT))

from butler_pc_core.inference.model_identity import (
    MAIN_EQUALS_BOX3,
    assert_main_not_box3,
    model_path_conflict_reason,
    sidecar_model_status_payload,
)

pytestmark = pytest.mark.no_sidecar_token


def _authorized(*, main_digest: str, box3_digest: str) -> dict[str, dict[str, object]]:
    return {
        "free_chat": {
            "asset_digest": main_digest,
            "model_present": True,
        },
        "box3_canonical": {
            "asset_digest": box3_digest,
            "model_present": True,
        },
    }


def test_model_identity_detects_equal_authorized_asset_digests():
    shared = "sha256:" + "a" * 64
    authorized = _authorized(main_digest=shared, box3_digest=shared)

    assert model_path_conflict_reason(authorized) == MAIN_EQUALS_BOX3
    with pytest.raises(RuntimeError, match=MAIN_EQUALS_BOX3):
        assert_main_not_box3(authorized)


def test_model_status_payload_is_digest_only():
    main_digest = "sha256:" + "a" * 64
    box3_digest = "sha256:" + "b" * 64

    payload = sidecar_model_status_payload(
        status="ready",
        authorized_models=_authorized(
            main_digest=main_digest,
            box3_digest=box3_digest,
        ),
    )

    assert payload["status"] == "ready"
    assert payload["model_role"] == "free_chat"
    assert payload["model_family"] == "qwen3-4b"
    assert payload["model_path_digest"] == main_digest
    assert payload["model_path_conflict"] is False
    assert payload["box3_model"]["model_role"] == "box3_canonical"
    assert payload["box3_model"]["model_family"] == "butler-1.7b-v9.2-r2b"
    assert payload["box3_model"]["model_path_digest"] == box3_digest


def test_sidecar_model_status_ignores_raw_model_path_environment(
    tmp_path, monkeypatch
):
    main = tmp_path / "main.gguf"
    box3 = tmp_path / "box3.gguf"
    main.write_bytes(b"main")
    box3.write_bytes(b"box3")
    monkeypatch.setenv("BUTLER_MAIN_MODEL_PATH", str(main))
    monkeypatch.setenv("BUTLER_BOX3_V9_Q4_MODEL_PATH", str(box3))

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


def test_sidecar_init_shared_llm_does_not_fallback_to_raw_path_env(
    tmp_path, monkeypatch
):
    model = tmp_path / "box3.gguf"
    model.write_bytes(b"box3")
    monkeypatch.setenv("BUTLER_MAIN_MODEL_PATH", str(model))

    import butler_sidecar

    sidecar = importlib.reload(butler_sidecar)
    sidecar._SHARED_LLM = None

    sidecar._init_shared_llm()
    assert sidecar._SHARED_LLM.status == "no_model"
