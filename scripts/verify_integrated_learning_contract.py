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


def _add_failure(failures: list[str], code: str) -> None:
    if code not in failures:
        failures.append(code)


def main() -> int:
    repo = Path(sys.argv[1]) if len(sys.argv) > 1 else Path(".")
    failures: list[str] = []

    schema = repo / "schemas/learning/integrated_learning_candidate_v1.schema.json"
    if not schema.exists():
        _add_failure(failures, "SCHEMA_MISSING")
    else:
        try:
            data = json.loads(schema.read_text(encoding="utf-8"))
        except Exception:
            _add_failure(failures, "SCHEMA_JSON_INVALID")
        else:
            if data.get("additionalProperties") is not False:
                _add_failure(failures, "SCHEMA_ADDITIONAL_PROPERTIES_INVALID")
            props = set((data.get("properties") or {}))
            if "integration_mode" in props:
                _add_failure(failures, "SCHEMA_INTEGRATION_MODE_FORBIDDEN")
            if data.get("properties", {}).get("auto_apply_to_runtime", {}).get("const") is not False:
                _add_failure(failures, "SCHEMA_AUTO_APPLY_NOT_FALSE")
            if data.get("properties", {}).get("model_training", {}).get("const") is not False:
                _add_failure(failures, "SCHEMA_MODEL_TRAINING_NOT_FALSE")
            if data.get("properties", {}).get("peft_training", {}).get("const") is not False:
                _add_failure(failures, "SCHEMA_PEFT_TRAINING_NOT_FALSE")

    for root_name in ROOTS_TO_SCAN:
        root = repo / root_name
        if not root.exists():
            continue
        for path in root.rglob("*.json"):
            try:
                data = json.loads(path.read_text(encoding="utf-8"))
            except Exception:
                _add_failure(failures, "JSON_PARSE_FAILED")
                continue
            for key in _iter_json_keys(data):
                if key in FORBIDDEN_SCHEMA_KEYS and key != "raw_text_logged":
                    _add_failure(failures, "FORBIDDEN_JSON_KEY")
    text_files = []
    for root_name in ROOTS_TO_SCAN:
        root = repo / root_name
        if root.exists():
            text_files.extend([p for p in root.rglob("*") if p.is_file() and p.suffix in {".py", ".json", ".md"}])
    for path in text_files:
        try:
            text = path.read_text(encoding="utf-8")
        except Exception:
            _add_failure(failures, "TEXT_READ_FAILED")
            continue
        if "Co-Authored-By:" in text:
            _add_failure(failures, "AI_FOOTER_FORBIDDEN")
        # Runtime code may mention integration_mode only to reject it. The field must not
        # appear in candidate JSON/SSOT evidence as a persisted or accepted property.

    if failures:
        print("INTEGRATED_LEARNING_CONTRACT_OK=0")
        for failure in failures:
            print(f"ERROR_CODE={failure}")
        return 1
    print("INTEGRATED_LEARNING_CONTRACT_OK=1")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
