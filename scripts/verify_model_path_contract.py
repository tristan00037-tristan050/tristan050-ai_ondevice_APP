#!/usr/bin/env python3
"""Verify Butler's descriptor-rooted model authority contract."""
from __future__ import annotations

import sys
from pathlib import Path


def _fail(code: str) -> int:
    print("MODEL_AUTHORITY_CONTRACT_OK=0")
    print(f"ERROR_CODE={code}")
    return 1


def _read(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8")
    except OSError as exc:
        raise RuntimeError("SOURCE_FILE_MISSING") from exc


def main() -> int:
    root = Path(sys.argv[1] if len(sys.argv) > 1 else ".").resolve()
    try:
        native = _read(root / "butler-desktop/src-tauri/src/lib.rs")
        sidecar = _read(root / "butler_sidecar.py")
        identity = _read(root / "butler_pc_core/inference/model_identity.py")
        runtime = _read(root / "butler_pc_core/inference/llm_runtime.py")
        loader = _read(root / "butler_pc_core/inference/verified_model_loader.py")
        config = _read(root / "butler-desktop/src-tauri/tauri.conf.json")
    except RuntimeError as exc:
        return _fail(str(exc))

    forbidden_capabilities = (
        "BUTLER_" + "MODEL_PATH",
        "BUTLER_BOX3_" + "V9_Q4_MODEL_PATH",
        "BUTLER_BOX3_" + "BASE_MODEL_PATH",
    )
    if any(
        capability in source
        for capability in forbidden_capabilities
        for source in (native, sidecar, identity)
    ):
        return _fail("LEGACY_MODEL_PATH_CAPABILITY_PRESENT")

    native_required = (
        "ASSET_BOOTSTRAP_FD_ENV",
        "open_asset_root",
        "asset_bootstrap_frame(app, asset_root_fd)?",
        "configure_sidecar_environment",
        ".env_clear()",
    )
    if any(value not in native for value in native_required):
        return _fail("NATIVE_DESCRIPTOR_BOOTSTRAP_MISSING")

    sidecar_required = (
        "_new_authorized_shared_llm",
        'role="free_chat.model"',
        "get_asset_service().acquire(",
        "LlmRuntime(model_handle=handle)",
        "/api/model/status",
    )
    if any(value not in sidecar for value in sidecar_required):
        return _fail("SIDECAR_ASSET_AUTHORITY_MISSING")

    identity_required = (
        "assert_main_not_box3",
        "model_path_conflict_reason",
        "model_path_digest",
        "model_role",
        "model_family",
        "authorized_models",
        "asset_digest",
    )
    if any(value not in identity for value in identity_required):
        return _fail("DIGEST_ROLE_IDENTITY_MISSING")

    if any(
        value not in runtime
        for value in ("NativeReadHandle", "VerifiedLlamaLoader", "load_from_verified_handle")
    ):
        return _fail("VERIFIED_RUNTIME_HANDLE_MISSING")

    descriptor_required = (
        'f"/dev/fd/{owned.fd}"',
        'f"/proc/self/fd/{owned.fd}"',
        '"model_path": descriptor_ref',
    )
    if any(value not in loader for value in descriptor_required):
        return _fail("DESCRIPTOR_CONSUMPTION_BINDING_MISSING")

    if '"externalBin"' in config:
        return _fail("LEGACY_EXTERNAL_LAUNCHER_PRESENT")

    print("MODEL_AUTHORITY_CONTRACT_OK=1")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
