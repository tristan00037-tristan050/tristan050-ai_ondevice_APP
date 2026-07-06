#!/usr/bin/env python3
from __future__ import annotations

import ast
import json
import re
import sys
from pathlib import Path
from typing import Any


CARD_RENDERER = Path("butler_pc_core/prompts/card_renderer.py")
CARD06_PROMPT = Path("butler_pc_core/prompts/cards/card_06_fill_external_form.yaml")

SHA256_RE = re.compile(r"^sha256:[0-9a-f]{64}$")
CONFIDENCE_VALUES = {"HIGH", "MEDIUM", "LOW", "UNFILLED"}
TOP_LEVEL_KEYS = {
    "schema_version",
    "app_build_sha",
    "model_bundle_sha256",
    "feature_flag",
    "cases",
    "raw_log_zero",
    "external_send_zero",
}
CASE_KEYS = {"case_id", "synthetic_only", "passed", "checks", "response"}
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
    "B6-S1": {"high_fields_ok", "structure_preserved"},
    "B6-S2": {"unfilled_fields_ok"},
    "B6-S3": {"value_preserved"},
    "B6-S4": {"no_data_unfilled_or_review_required"},
    "B6-S5": {"prompt_injection_ignored", "arbitrary_generation_zero"},
    "B6-S6": {"secret_auto_fill_zero", "forbidden_secret_marked"},
}
GOLDEN_CARDS = {"2", "3", "5"}


def _fail(code: str) -> None:
    print("BOX6_FORM_FILL_ACTIVATION_OK=0")
    print(f"ERROR_CODE={code}")
    raise SystemExit(1)


def _read(root: Path, rel: Path) -> str:
    try:
        return (root / rel).read_text(encoding="utf-8")
    except OSError:
        _fail("SOURCE_FILE_MISSING")


def _parse(source: str) -> ast.Module:
    try:
        return ast.parse(source)
    except SyntaxError:
        _fail("SOURCE_PARSE_ERROR")


def _function_segment(source: str, name: str) -> str:
    tree = _parse(source)
    for node in tree.body:
        if isinstance(node, ast.FunctionDef) and node.name == name:
            return ast.get_source_segment(source, node) or ""
    _fail("FUNCTION_MISSING")


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


def _check_static_contract(root: Path) -> None:
    renderer = _read(root, CARD_RENDERER)
    prompt = _read(root, CARD06_PROMPT)

    _check_static_contract_source_for_test(renderer)
    if "{{ our_data_json }}" not in prompt:
        _fail("BOX6_PROMPT_JSON_BINDING_MISSING")
    if "our_data | tojson" in prompt:
        _fail("BOX6_TOJSON_FORBIDDEN")


def _check_static_contract_source_for_test(renderer: str) -> None:
    if "env.policies[" in renderer or "env.policies.update(" in renderer:
        _fail("GLOBAL_JINJA_ENV_MUTATION")
    if "ensure_ascii=False" in renderer:
        box6_json = _function_segment(renderer, "_box6_json")
        if "ensure_ascii=False" not in box6_json:
            _fail("ENSURE_ASCII_SCOPE_INVALID")
        if renderer.count("ensure_ascii=False") != box6_json.count("ensure_ascii=False"):
            _fail("ENSURE_ASCII_SCOPE_INVALID")
    else:
        _fail("BOX6_LOCAL_SERIALIZER_MISSING")

    if "_box6_json(context.get(\"our_data\", {}))" not in renderer:
        _fail("BOX6_JSON_CONTEXT_MISSING")


def _load_json(path: Path) -> dict[str, Any]:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        _fail("JSON_PARSE_FAILED")
    except OSError:
        _fail("EVIDENCE_FILE_UNREADABLE")
    return _expect_dict(data, "EVIDENCE_OBJECT_REQUIRED")


def _check_response(response: Any) -> None:
    payload = _expect_dict(response, "RESPONSE_OBJECT_REQUIRED")
    if set(payload) != REQUIRED_RESPONSE_KEYS:
        _fail("RESPONSE_SCHEMA_NOT_STRICT")
    if payload.get("schema_version") != "card_06.form_fill.v1":
        _fail("RESPONSE_SCHEMA_VERSION_INVALID")
    if not isinstance(payload.get("filled_form"), str):
        _fail("FILLED_FORM_TYPE_INVALID")
    mappings = _expect_list(payload.get("field_mappings"), "FIELD_MAPPINGS_LIST_REQUIRED")
    for mapping in mappings:
        item = _expect_dict(mapping, "MAPPING_OBJECT_REQUIRED")
        if not REQUIRED_MAPPING_KEYS.issubset(item):
            _fail("MAPPING_KEY_MISSING")
        if item.get("confidence") not in CONFIDENCE_VALUES:
            _fail("CONFIDENCE_INVALID")
    _expect_list(payload.get("unfilled_fields"), "UNFILLED_FIELDS_LIST_REQUIRED")
    _expect_list(payload.get("review_required"), "REVIEW_REQUIRED_LIST_REQUIRED")
    _expect_list(payload.get("warnings"), "WARNINGS_LIST_REQUIRED")


def _check_case(case: Any) -> str:
    item = _expect_dict(case, "CASE_OBJECT_REQUIRED")
    if set(item) != CASE_KEYS:
        _fail("CASE_SCHEMA_NOT_STRICT")
    case_id = item.get("case_id")
    if not isinstance(case_id, str) or case_id not in REQUIRED_CASE_CHECKS:
        _fail("CASE_ID_INVALID")
    if item.get("synthetic_only") is not True:
        if item.get("response") not in (None, {}):
            _fail("NON_SYNTHETIC_RESPONSE_FORBIDDEN")
    if item.get("passed") is not True:
        _fail("CASE_PASS_REQUIRED")
    checks = _expect_dict(item.get("checks"), "CHECKS_OBJECT_REQUIRED")
    if not REQUIRED_CASE_CHECKS[case_id].issubset(checks):
        _fail("CASE_CHECK_REQUIRED")
    if any(value is not True for value in checks.values()):
        _fail("CASE_CHECK_NOT_TRUE")
    if item.get("synthetic_only") is True:
        _check_response(item.get("response"))
    return case_id


def _check_golden_files(evidence_path: Path) -> None:
    golden_dir = evidence_path.parent / "golden"
    for mode in sorted(GOLDEN_CARDS):
        path = golden_dir / f"card_{mode}_render_diff.json"
        data = _load_json(path)
        expected = {
            "schema_version",
            "card_mode",
            "byte_diff_zero",
            "semantic_diff_zero",
        }
        if set(data) != expected:
            _fail("GOLDEN_DIFF_SCHEMA_INVALID")
        if data.get("card_mode") != mode:
            _fail("GOLDEN_DIFF_CARD_INVALID")
        if data.get("byte_diff_zero") is not True or data.get("semantic_diff_zero") is not True:
            _fail("GOLDEN_DIFF_NOT_ZERO")


def _check_evidence(evidence_path: Path) -> None:
    data = _load_json(evidence_path)
    if set(data) != TOP_LEVEL_KEYS:
        _fail("EVIDENCE_SCHEMA_NOT_STRICT")
    if data.get("schema_version") != "box6.form_fill.smoke.v1":
        _fail("EVIDENCE_SCHEMA_VERSION_INVALID")
    if not isinstance(data.get("app_build_sha"), str) or len(data["app_build_sha"]) < 7:
        _fail("APP_BUILD_SHA_INVALID")
    if not _is_sha256(data.get("model_bundle_sha256")):
        _fail("MODEL_BUNDLE_SHA_INVALID")
    if data.get("feature_flag") != "VITE_BUTLER_BOX6_FORM_FILL=1":
        _fail("FEATURE_FLAG_INVALID")
    if data.get("raw_log_zero") is not True:
        _fail("RAW_LOG_ZERO_REQUIRED")
    if data.get("external_send_zero") is not True:
        _fail("EXTERNAL_SEND_ZERO_REQUIRED")
    cases = _expect_list(data.get("cases"), "CASES_LIST_REQUIRED")
    if len(cases) != 6:
        _fail("CASE_COUNT_INVALID")
    seen = {_check_case(case) for case in cases}
    if seen != set(REQUIRED_CASE_CHECKS):
        _fail("CASE_SET_INVALID")
    _check_golden_files(evidence_path)


def main() -> int:
    root = Path(sys.argv[1]) if len(sys.argv) >= 2 else Path.cwd()
    evidence_path = (
        Path(sys.argv[2])
        if len(sys.argv) >= 3
        else root / "evidence" / "box6" / "box6_form_fill_smoke_evidence.json"
    )
    _check_static_contract(root)
    _check_evidence(evidence_path)
    print("BOX6_FORM_FILL_ACTIVATION_OK=1")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
