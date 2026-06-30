#!/usr/bin/env python3
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

ROOTS_TO_SCAN = [
    "schemas/learning",
    "butler_pc_core/learning_core",
    "butler_pc_core/learning_adapters",
    "검증대상_SSOT/integrated_learning_autoflow_v1_2",
]
FORBIDDEN_SCHEMA_KEYS = {
    "integration_mode",
    "raw",
    "raw_text",
    "raw_memo",
    "filename",
    "file_name",
    "file_path",
    "md_content",
    "transaction_text",
    "prompt",
    "response_text",
    "customer_name",
    "account_number_plain",
    "amount_plain",
    "email_plain",
    "phone_plain",
    "local_path",
    "token",
    "password",
    "secret",
    "api_key",
}


def _iter_json_keys(value):
    if isinstance(value, dict):
        for key, child in value.items():
            yield key
            yield from _iter_json_keys(child)
    elif isinstance(value, list):
        for child in value:
            yield from _iter_json_keys(child)


def main() -> int:
    repo = Path(sys.argv[1]) if len(sys.argv) > 1 else Path(".")
    failures: list[str] = []

    schema = repo / "schemas/learning/integrated_learning_candidate_v1.schema.json"
    if not schema.exists():
        failures.append("missing integrated_learning_candidate_v1.schema.json")
    else:
        data = json.loads(schema.read_text(encoding="utf-8"))
        if data.get("additionalProperties") is not False:
            failures.append("schema additionalProperties must be false")
        props = set((data.get("properties") or {}))
        if "integration_mode" in props:
            failures.append("integration_mode must not be a candidate property")
        if data.get("properties", {}).get("auto_apply_to_runtime", {}).get("const") is not False:
            failures.append("auto_apply_to_runtime must be const false")
        if data.get("properties", {}).get("model_training", {}).get("const") is not False:
            failures.append("model_training must be const false")
        if data.get("properties", {}).get("peft_training", {}).get("const") is not False:
            failures.append("peft_training must be const false")

    for root_name in ROOTS_TO_SCAN:
        root = repo / root_name
        if not root.exists():
            continue
        for path in root.rglob("*.json"):
            try:
                data = json.loads(path.read_text(encoding="utf-8"))
            except Exception as exc:
                failures.append(f"{path}: invalid json: {exc}")
                continue
            for key in _iter_json_keys(data):
                if key in FORBIDDEN_SCHEMA_KEYS and key != "raw_text_logged":
                    failures.append(f"{path}: forbidden key {key}")
    text_files = []
    for root_name in ROOTS_TO_SCAN:
        root = repo / root_name
        if root.exists():
            text_files.extend([p for p in root.rglob("*") if p.is_file() and p.suffix in {".py", ".json", ".md"}])
    for path in text_files:
        text = path.read_text(encoding="utf-8")
        if "Co-Authored-By:" in text:
            failures.append(f"{path}: AI footer / Co-Authored-By forbidden")
        # Runtime code may mention integration_mode only to reject it. The field must not
        # appear in candidate JSON/SSOT evidence as a persisted or accepted property.

    if failures:
        for failure in failures:
            print(f"BLOCK: {failure}")
        return 1
    print("INTEGRATED_LEARNING_CONTRACT_OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
