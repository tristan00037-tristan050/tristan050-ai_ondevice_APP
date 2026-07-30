"""Digest-only model role identity derived from verified asset authority."""
from __future__ import annotations

from typing import Mapping

FREE_CHAT_MODEL_FAMILY = "qwen3-4b"
BOX3_MODEL_FAMILY = "butler-1.7b-v9.2-r2b"

MAIN_EQUALS_BOX3 = "MODEL_ASSET_CONFLICT_MAIN_EQUALS_BOX3"


def model_path_conflict_reason(
    authorized_models: Mapping[str, Mapping[str, object]] | None = None,
) -> str | None:
    if authorized_models is None:
        return None
    main_digest = str(
        authorized_models.get("free_chat", {}).get("asset_digest") or ""
    )
    box3_digest = str(
        authorized_models.get("box3_canonical", {}).get("asset_digest") or ""
    )
    if main_digest and box3_digest and main_digest == box3_digest:
        return MAIN_EQUALS_BOX3
    return None


def assert_main_not_box3(
    authorized_models: Mapping[str, Mapping[str, object]] | None = None,
) -> None:
    reason = model_path_conflict_reason(authorized_models)
    if reason is not None:
        raise RuntimeError(reason)


def model_identity(
    *,
    role: str,
    authorized_model: Mapping[str, object] | None = None,
) -> dict[str, object]:
    model = authorized_model or {}
    present = model.get("model_present") is True
    family = (
        FREE_CHAT_MODEL_FAMILY
        if role == "free_chat" and present
        else BOX3_MODEL_FAMILY
        if role == "box3_canonical" and present
        else ""
    )
    return {
        "model_role": role,
        "model_family": family,
        "model_path_digest": str(model.get("asset_digest") or ""),
        "model_present": present,
    }


def sidecar_model_status_payload(
    *,
    status: str,
    last_error: str = "",
    authorized_models: Mapping[str, Mapping[str, object]] | None = None,
) -> dict[str, object]:
    models = authorized_models or {}
    main = models.get("free_chat", {})
    box3 = models.get("box3_canonical", {})
    conflict_reason = model_path_conflict_reason(models)
    return {
        "status": "error" if conflict_reason else status,
        "last_error": conflict_reason or last_error,
        **model_identity(role="free_chat", authorized_model=main),
        "model_path_conflict": conflict_reason is not None,
        "model_path_conflict_reason": conflict_reason or "",
        "box3_model": model_identity(
            role="box3_canonical",
            authorized_model=box3,
        ),
    }
