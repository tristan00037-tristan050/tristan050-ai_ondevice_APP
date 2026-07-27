"""Model role identity and path-conflict guards for local sidecar startup."""
from __future__ import annotations

import hashlib
import os
from pathlib import Path
from typing import Mapping

MAIN_MODEL_PATH_ENV = "BUTLER_MODEL_PATH"
BOX3_MODEL_PATH_ENV = "BUTLER_BOX3_V9_Q4_MODEL_PATH"
FREE_CHAT_MODEL_NAME = "qwen3-4b-q4_k_m.gguf"
BOX3_MODEL_NAME = "butler-1.7b-v9-2-r2b-q4_k_m.gguf"

FREE_CHAT_MODEL_FAMILY = "qwen3-4b"
BOX3_MODEL_FAMILY = "butler-1.7b-v9.2-r2b"

MAIN_USES_BOX3 = "MODEL_PATH_CONFLICT_MAIN_USES_BOX3"
MAIN_EQUALS_BOX3 = "MODEL_PATH_CONFLICT_MAIN_EQUALS_BOX3"


def _env_value(environ: Mapping[str, str], key: str) -> str:
    return (environ.get(key) or "").strip()


def _normalize_path_text(value: str) -> str:
    return value.replace("\\", "/")


def _sha256_text(value: str) -> str:
    if not value:
        return ""
    return "sha256:" + hashlib.sha256(value.encode("utf-8")).hexdigest()


def is_box3_model_path(value: str) -> bool:
    normalized = _normalize_path_text(value)
    return BOX3_MODEL_NAME in normalized or "models/box3" in normalized


def model_path_conflict_reason(environ: Mapping[str, str] | None = None) -> str | None:
    env = environ or os.environ
    main = _env_value(env, MAIN_MODEL_PATH_ENV)
    box3 = _env_value(env, BOX3_MODEL_PATH_ENV)
    if main and is_box3_model_path(main):
        return MAIN_USES_BOX3
    if main and box3 and main == box3:
        return MAIN_EQUALS_BOX3
    return None


def assert_main_not_box3(environ: Mapping[str, str] | None = None) -> None:
    reason = model_path_conflict_reason(environ)
    if reason is not None:
        raise RuntimeError(reason)


def model_family_for_path(value: str, *, role: str) -> str:
    name = Path(value).name if value else ""
    if name == FREE_CHAT_MODEL_NAME or role == "free_chat":
        return FREE_CHAT_MODEL_FAMILY if name == FREE_CHAT_MODEL_NAME else ""
    if name == BOX3_MODEL_NAME or role == "box3_canonical":
        return BOX3_MODEL_FAMILY if name == BOX3_MODEL_NAME else ""
    return ""


def model_identity(
    *,
    role: str,
    env_key: str,
    environ: Mapping[str, str] | None = None,
) -> dict[str, object]:
    env = environ or os.environ
    value = _env_value(env, env_key)
    return {
        "model_role": role,
        "model_family": model_family_for_path(value, role=role),
        "model_path_digest": _sha256_text(value),
        "model_present": bool(value and Path(value).exists()),
    }


def sidecar_model_status_payload(
    *,
    status: str,
    last_error: str = "",
    environ: Mapping[str, str] | None = None,
    authorized_models: Mapping[str, Mapping[str, object]] | None = None,
) -> dict[str, object]:
    if authorized_models is not None:
        main = authorized_models.get("free_chat", {})
        box3 = authorized_models.get("box3_canonical", {})
        return {
            "status": status,
            "last_error": last_error,
            "model_role": "free_chat",
            "model_family": FREE_CHAT_MODEL_FAMILY
            if main.get("model_present") is True
            else "",
            "model_path_digest": str(main.get("asset_digest") or ""),
            "model_present": main.get("model_present") is True,
            "model_path_conflict": False,
            "model_path_conflict_reason": "",
            "box3_model": {
                "model_role": "box3_canonical",
                "model_family": BOX3_MODEL_FAMILY
                if box3.get("model_present") is True
                else "",
                "model_path_digest": str(box3.get("asset_digest") or ""),
                "model_present": box3.get("model_present") is True,
            },
        }
    env = environ or os.environ
    conflict_reason = model_path_conflict_reason(env)
    public_status = "error" if conflict_reason else status
    public_error = conflict_reason or last_error
    return {
        "status": public_status,
        "last_error": public_error,
        **model_identity(role="free_chat", env_key=MAIN_MODEL_PATH_ENV, environ=env),
        "model_path_conflict": conflict_reason is not None,
        "model_path_conflict_reason": conflict_reason or "",
        "box3_model": model_identity(role="box3_canonical", env_key=BOX3_MODEL_PATH_ENV, environ=env),
    }
