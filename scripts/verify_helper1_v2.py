#!/usr/bin/env python3
"""Meta-only Helper1 v2 audit.

Static verification can pass independently. Product CODE_PASS remains closed
until the native bookmark bridge, fd-bound Qwen worker, approved model closure,
real-asset E2E, and M3/M4 evidence exist at the audited commit.
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CANONICAL_ROOT = ROOT / "butler_pc_core" / "helper1"
ROUTE = ROOT / "butler_pc_core" / "sidecar" / "routes" / "helper1_search.py"
CONTRACT_ROOT = ROOT / "contracts" / "helper1"

REQUIRED_FILES = (
    CANONICAL_ROOT / "__init__.py",
    CANONICAL_ROOT / "contracts.py",
    CANONICAL_ROOT / "security.py",
    CANONICAL_ROOT / "ingestion.py",
    CANONICAL_ROOT / "index_store.py",
    CANONICAL_ROOT / "retrieval.py",
    CANONICAL_ROOT / "models.py",
    CANONICAL_ROOT / "pipeline.py",
    CANONICAL_ROOT / "release.py",
    CANONICAL_ROOT / "service.py",
    ROUTE,
    CONTRACT_ROOT / "ask-request-v2.schema.json",
    CONTRACT_ROOT / "answer-result-v2.schema.json",
    CONTRACT_ROOT / "index-manifest-v2.schema.json",
    CONTRACT_ROOT / "release-receipt-v2.schema.json",
)
FORBIDDEN = (
    "~/Desktop",
    "/private/tmp",
    "/Volumes/",
    "sys.path.append",
    "sys.path.insert",
    "import memory_helper",
    "pickle.load",
    "allow_pickle=True",
    "contract_only_response",
    "placeholder_answer",
)
REQUIRED_ROUTE_LITERALS = (
    "butler.helper1.ask-request.v2",
    "requested_generation_id",
    "effect_intent",
    "REQUEST_INVALID",
)
REQUIRED_MODEL_LITERALS = (
    "llama_model_load_from_file_ptr",
    "pass_fds=(model_fd,)",
    '"thinking": False',
    '"kv_disposed"',
)
REQUIRED_PIPELINE_LITERALS = (
    "bind_citations",
    "scan_runtime_text",
    "release_display",
    "detect_prompt_injection",
)

PRODUCT_GATES = {
    "NATIVE_BOOKMARK_BRIDGE_OK": (
        ROOT / "butler-desktop" / "src-tauri" / "src" / "helper1_bookmark.rs"
    ),
    "NATIVE_QWEN_WORKER_OK": (
        ROOT / "butler-desktop" / "src-tauri" / "native" / "helper1_llama_worker.cpp"
    ),
    "APPROVED_ASSET_CLOSURE_OK": (
        ROOT / "evidence" / "helper1" / "APPROVED_ASSET_CLOSURE.json"
    ),
    "REAL_ASSET_E2E_OK": (
        ROOT / "evidence" / "helper1" / "REAL_ASSET_E2E_RECEIPT.json"
    ),
    "M3_M4_MEASUREMENT_OK": (
        ROOT / "evidence" / "helper1" / "M3_M4_MEASUREMENT.json"
    ),
    "MACOS_SANDBOX_E2E_OK": (
        ROOT / "evidence" / "helper1" / "MACOS_SANDBOX_E2E_RECEIPT.json"
    ),
}


def emit(key: str, value: int | str) -> None:
    print(f"{key}={value}")


def source_files() -> tuple[Path, ...]:
    files = tuple(sorted(CANONICAL_ROOT.glob("*.py")))
    return files + (ROUTE,)


def static_audit() -> tuple[bool, str]:
    if any(not path.is_file() for path in REQUIRED_FILES):
        return False, "HELPER1_REQUIRED_FILE_MISSING"
    try:
        sources = {path: path.read_text(encoding="utf-8") for path in source_files()}
    except (OSError, UnicodeError):
        return False, "HELPER1_SOURCE_READ_FAILED"
    if any(token in text for text in sources.values() for token in FORBIDDEN):
        return False, "HELPER1_FORBIDDEN_SOURCE_TOKEN"
    route = sources[ROUTE]
    if any(token not in route for token in REQUIRED_ROUTE_LITERALS):
        return False, "HELPER1_REQUEST_CONTRACT_MISSING"
    models = sources[CANONICAL_ROOT / "models.py"]
    if any(token not in models for token in REQUIRED_MODEL_LITERALS):
        return False, "HELPER1_MODEL_CONTRACT_MISSING"
    pipeline = sources[CANONICAL_ROOT / "pipeline.py"]
    if any(token not in pipeline for token in REQUIRED_PIPELINE_LITERALS):
        return False, "HELPER1_PIPELINE_GATE_MISSING"
    service = sources[CANONICAL_ROOT / "service.py"]
    immutable = (
        '"product_release_allowed": False',
        '"runtime_activation_allowed": False',
        '"production_claim_allowed": False',
        '"external_network_allowed": False',
    )
    if any(token not in service for token in immutable):
        return False, "HELPER1_RELEASE_BOUNDARY_MISSING"
    if re.search(r"\b(?:print|logging\.\w+)\s*\(", "\n".join(sources.values())):
        return False, "HELPER1_RAW_LOG_SURFACE_PRESENT"
    try:
        from jsonschema import Draft202012Validator

        for path in sorted(CONTRACT_ROOT.glob("*.schema.json")):
            Draft202012Validator.check_schema(
                json.loads(path.read_text(encoding="utf-8"))
            )
    except (ImportError, OSError, UnicodeError, ValueError):
        return False, "HELPER1_SCHEMA_VERIFY_FAILED"
    return True, "NONE"


def main() -> int:
    parser = argparse.ArgumentParser(add_help=True)
    parser.add_argument("--static-only", action="store_true")
    args = parser.parse_args()
    static_ok, error = static_audit()
    emit("HELPER1_STATIC_VERIFY_OK", int(static_ok))
    if args.static_only:
        emit("ERROR_CODE", error)
        return 0 if static_ok else 1

    gates = {
        key: int(path.is_file())
        for key, path in PRODUCT_GATES.items()
    }
    for key, value in gates.items():
        emit(key, value)
    product_ok = static_ok and all(gates.values())
    emit("PRODUCT_RELEASE_ALLOWED", 0)
    emit("RUNTIME_ACTIVATION_ALLOWED", 0)
    emit("HELPER1_PRODUCTION_CLAIM_ALLOWED", 0)
    emit("CODE_PASS", int(product_ok))
    emit(
        "ERROR_CODE",
        error if not static_ok else ("NONE" if product_ok else "PRODUCT_EVIDENCE_INCOMPLETE"),
    )
    return 0 if product_ok else 1


if __name__ == "__main__":
    sys.exit(main())
