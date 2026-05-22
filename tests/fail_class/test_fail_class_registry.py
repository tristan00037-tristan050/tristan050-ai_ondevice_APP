from __future__ import annotations

from butler_pc_core.fail_class import FailClass, GROUPS, fail_payload, map_legacy_to_fail_class


def test_36_codes_5_groups():
    # The directive lists 36 unique enum values: 8 + 7 + 11 + 5 + 5.
    assert len(FailClass) == 36
    assert set(GROUPS) == {"core_runtime", "integrity", "policy_security", "io", "lifecycle"}
    assert sum(len(v) for v in GROUPS.values()) == 36
    assert {item for group in GROUPS.values() for item in group} == set(FailClass)


def test_legacy_alias_map():
    assert map_legacy_to_fail_class("input_too_large") == FailClass.INVALID_REQUEST_SCHEMA
    assert map_legacy_to_fail_class("ImportError") == FailClass.INTERNAL_RUNTIME_ERROR
    assert map_legacy_to_fail_class("ParseError") == FailClass.OUTPUT_SCHEMA_INVALID
    assert map_legacy_to_fail_class(RuntimeError("boom")) == FailClass.INTERNAL_RUNTIME_ERROR


def test_sse_response_contains_fail_class():
    payload = fail_payload(FailClass.OUTPUT_SCHEMA_INVALID, "parse failed", error_class="ParseError")
    assert payload["fail_class"] == "OUTPUT_SCHEMA_INVALID"
    assert payload["error_class"] == "ParseError"
    assert payload["message"] == "parse failed"
