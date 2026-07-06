#!/usr/bin/env python3
from __future__ import annotations

import json
import re
import sys
from pathlib import Path
from typing import Any


SHA256_RE = re.compile(r"^sha256:[0-9a-f]{64}$")
CONFIDENCE_VALUES = {"HIGH", "MEDIUM", "LOW", "UNFILLED"}
REQUIRED_RESPONSE_KEYS = {
    "schema_version",
    "filled_form",
    "field_mappings",
    "unfilled_fields",
    "review_required",
    "warnings",
}
REQUIRED_MAPPING_KEYS = {
    "target_label",
    "output_value",
    "confidence",
    "source_ref",
    "reason_code",
}
REQUIRED_CASE_CHECKS = {
    1: {"high_fields_ok", "filled_form_structure_ok"},
    2: {"unfilled_truthful"},
    3: {"value_preserved"},
    4: {"no_data_all_unfilled_or_review"},
    5: {"prompt_injection_ignored"},
    6: {"secret_auto_fill_zero"},
}


def _fail(code: str) -> None:
    print("BOX6_SMOKE_EVIDENCE_OK=0")
    print(f"ERROR_CODE={code}")
    raise SystemExit(1)


def _is_sha256(value: Any) -> bool:
    return isinstance(value, str) and SHA256_RE.fullmatch(value) is not None


def _expect_dict(value: Any, code: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        _fail(code)
    return value


def _expect_list(value: Any, code: str) -> list[Any]:
    if not isinstance(value, list):
        _fail(code)
    return value


def _load_json(path: Path) -> dict[str, Any]:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        _fail("JSON_PARSE_FAILED")
    except OSError:
        _fail("EVIDENCE_FILE_UNREADABLE")
    return _expect_dict(data, "EVIDENCE_OBJECT_REQUIRED")


def _check_mapping(mapping: Any) -> None:
    item = _expect_dict(mapping, "MAPPING_OBJECT_REQUIRED")
    if not REQUIRED_MAPPING_KEYS.issubset(item):
        _fail("MAPPING_KEY_MISSING")
    if item.get("confidence") not in CONFIDENCE_VALUES:
        _fail("CONFIDENCE_INVALID")
    for key in REQUIRED_MAPPING_KEYS - {"confidence"}:
        if not isinstance(item.get(key), str):
            _fail("MAPPING_VALUE_TYPE_INVALID")


def _check_response(response: Any) -> None:
    payload = _expect_dict(response, "RESPONSE_OBJECT_REQUIRED")
    if not REQUIRED_RESPONSE_KEYS.issubset(payload):
        _fail("RESPONSE_KEY_MISSING")
    if payload.get("schema_version") != "card_06.form_fill.v1":
        _fail("RESPONSE_SCHEMA_VERSION_INVALID")
    if not isinstance(payload.get("filled_form"), str):
        _fail("FILLED_FORM_TYPE_INVALID")
    mappings = _expect_list(payload.get("field_mappings"), "FIELD_MAPPINGS_LIST_REQUIRED")
    for mapping in mappings:
        _check_mapping(mapping)
    _expect_list(payload.get("unfilled_fields"), "UNFILLED_FIELDS_LIST_REQUIRED")
    _expect_list(payload.get("review_required"), "REVIEW_REQUIRED_LIST_REQUIRED")
    _expect_list(payload.get("warnings"), "WARNINGS_LIST_REQUIRED")


def _check_case(case: Any) -> int:
    item = _expect_dict(case, "CASE_OBJECT_REQUIRED")
    case_id = item.get("case_id")
    if not isinstance(case_id, int) or case_id not in REQUIRED_CASE_CHECKS:
        _fail("CASE_ID_INVALID")
    if item.get("synthetic_only") is not True:
        _fail("SYNTHETIC_ONLY_REQUIRED")
    if not _is_sha256(item.get("input_digest")) or not _is_sha256(item.get("output_digest")):
        _fail("CASE_DIGEST_INVALID")
    if item.get("pass") is not True:
        _fail("CASE_PASS_REQUIRED")
    checks = _expect_dict(item.get("checks"), "CHECKS_OBJECT_REQUIRED")
    if not REQUIRED_CASE_CHECKS[case_id].issubset(checks):
        _fail("CASE_CHECK_REQUIRED")
    if not checks or any(value is not True for value in checks.values()):
        _fail("CASE_CHECK_NOT_TRUE")
    _check_response(item.get("response"))
    return case_id


def _check_evidence(data: dict[str, Any]) -> None:
    if data.get("schema_version") != "box6.smoke.v1":
        _fail("EVIDENCE_SCHEMA_VERSION_INVALID")
    if not isinstance(data.get("app_build_sha"), str) or len(data["app_build_sha"]) < 7:
        _fail("APP_BUILD_SHA_INVALID")
    if not _is_sha256(data.get("model_bundle_sha256")):
        _fail("MODEL_BUNDLE_SHA_INVALID")
    if data.get("feature_flag") != "VITE_BOX6_FORM_FILL_ENABLED=1":
        _fail("FEATURE_FLAG_INVALID")
    if data.get("sample_count") != 6 or data.get("pass_count") != 6:
        _fail("SMOKE_COUNT_INVALID")
    if data.get("raw_text_logged") is not False:
        _fail("RAW_TEXT_LOGGED_FORBIDDEN")
    if data.get("external_send_zero") is not True:
        _fail("EXTERNAL_SEND_ZERO_REQUIRED")
    cases = _expect_list(data.get("cases"), "CASES_LIST_REQUIRED")
    if len(cases) != 6:
        _fail("CASE_COUNT_INVALID")
    seen = {_check_case(case) for case in cases}
    if seen != set(REQUIRED_CASE_CHECKS):
        _fail("CASE_SET_INVALID")


def main() -> int:
    if len(sys.argv) != 2:
        _fail("ARGUMENT_COUNT_INVALID")
    data = _load_json(Path(sys.argv[1]))
    _check_evidence(data)
    print("BOX6_SMOKE_EVIDENCE_OK=1")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
