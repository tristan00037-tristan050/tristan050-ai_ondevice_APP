from __future__ import annotations

import copy

import pytest

from butler_pc_core.learning_adapters.chat_context import ChatContextAdapter
from butler_pc_core.learning_core import UnifiedLearningIntakeGate
from butler_pc_core.learning_core.contracts import (
    ALLOWED_VERIFIED_BY,
    IntegratedLearningError,
    stable_json_digest,
    validate_evidence_ref,
    validate_verified_at,
    validate_verified_by,
)


def _digest(value: str = "x") -> str:
    return "sha256:" + ("%064x" % abs(hash(value)))[-64:]


def _payload() -> dict:
    return {
        "explicit_business_confirmation": True,
        "manager_or_admin_approved": True,
        "shadow_eval_cases": 100,
        "pii_zero": True,
        "false_learning_zero": True,
        "context_digest": _digest("chat-context"),
    }


def _candidate(payload: dict | None = None) -> dict:
    payload = _payload() if payload is None else payload
    return {
        "schema_version": "integrated_learning_candidate.v1",
        "candidate_id": "ilc-" + "a" * 32,
        "target_kind": "chat_context",
        "adapter_version": "chat_context.v1.2.0",
        "learning_source_type": "verified_chat_context",
        "policy_decision": "allow",
        "verified": True,
        "group_a_verified": True,
        "raw_text_logged": False,
        "external_send_zero": True,
        "model_training": False,
        "peft_training": False,
        "human_review_required": True,
        "auto_apply_to_runtime": False,
        "retention_class": "audit_digest_only",
        "verification": {
            "verified_by": "group_a",
            "verified_at": "2026-07-02T00:00:00Z",
            "evidence_digest": _digest("evidence"),
            "evidence_ref": "digest-only-fixture",
        },
        "source_refs": [{"ref_type": "usage_log", "ref_id_digest": _digest("usage")}],
        "payload_digest": stable_json_digest(payload),
        "expected_effect_digest": _digest("expected"),
        "payload": payload,
    }


def _evaluate(candidate: dict, *, enable_chat: bool = True):
    return UnifiedLearningIntakeGate.with_default_adapters(enable_chat=enable_chat).evaluate(candidate)


def _mutated(mutator) -> dict:
    candidate = _candidate()
    mutator(candidate)
    if "payload" in candidate and isinstance(candidate["payload"], dict):
        candidate["payload_digest"] = stable_json_digest(candidate["payload"])
    return candidate


def _drop_reason(mutator, *, enable_chat: bool = True) -> str:
    verdict = _evaluate(_mutated(mutator), enable_chat=enable_chat)
    assert verdict.accepted is False
    assert verdict.candidate is None
    assert verdict.drop_reason is not None
    return verdict.drop_reason


def test_chat_context_default_disabled_is_fail_closed():
    verdict = _evaluate(_candidate(), enable_chat=False)
    assert verdict.accepted is False
    assert verdict.drop_reason == "CHAT_CONTEXT_DISABLED"


def test_valid_chat_context_candidate_accepts_when_explicitly_enabled():
    verdict = _evaluate(_candidate(), enable_chat=True)
    assert verdict.accepted is True
    assert verdict.candidate is not None
    assert verdict.candidate["payload"]["context_digest"] == _digest("chat-context")


@pytest.mark.parametrize(
    ("field", "value", "reason"),
    [
        ("explicit_business_confirmation", False, "BUSINESS_CONFIRMATION_REQUIRED"),
        ("manager_or_admin_approved", False, "MANAGER_APPROVAL_REQUIRED"),
        ("shadow_eval_cases", 99, "SHADOW_EVAL_CASES_TOO_LOW"),
        ("shadow_eval_cases", "100", "SHADOW_EVAL_CASES_TOO_LOW"),
        ("shadow_eval_cases", True, "SHADOW_EVAL_CASES_TOO_LOW"),
        ("pii_zero", False, "PII_NOT_ZERO"),
        ("false_learning_zero", False, "FALSE_LEARNING_NOT_ZERO"),
        ("context_digest", "sha256:not-64", "CONTEXT_DIGEST_INVALID"),
    ],
)
def test_payload_gate_failures_map_to_fixed_drop_enum(field, value, reason):
    assert _drop_reason(lambda c: c["payload"].__setitem__(field, value)) == reason


def test_payload_exact_keys_fail_closed_on_extra_key():
    assert _drop_reason(lambda c: c["payload"].__setitem__("raw_summary", _digest("x"))) == "SCHEMA_KEYS_INVALID"


def test_payload_exact_keys_fail_closed_on_missing_key():
    assert _drop_reason(lambda c: c["payload"].pop("context_digest")) == "SCHEMA_KEYS_INVALID"


@pytest.mark.parametrize("verified_by", sorted(ALLOWED_VERIFIED_BY))
def test_verified_by_allowlist(verified_by):
    candidate = _candidate()
    candidate["verification"]["verified_by"] = verified_by
    verdict = _evaluate(candidate)
    assert verdict.accepted is True


@pytest.mark.parametrize("value", ["admin", "manager", "system_contract", "alice", "", " group_a", "group_a "])
def test_verified_by_rejects_legacy_or_non_allowlisted_values(value):
    assert _drop_reason(lambda c: c["verification"].__setitem__("verified_by", value)) == "VERIFIED_BY_INVALID"


def test_verified_by_rejects_non_string():
    assert _drop_reason(lambda c: c["verification"].__setitem__("verified_by", 1)) == "VERIFIED_BY_INVALID"


@pytest.mark.parametrize(
    "value",
    [
        "2026-07-02T00:00:00+09:00",
        "2026-07-02T00:00:00.000Z",
        "2026-07-02T00:00:00",
        "2026-02-31T00:00:00Z",
        "2026-07-02t00:00:00Z",
        " 2026-07-02T00:00:00Z",
        "2026-07-02T00:00:00Z ",
    ],
)
def test_verified_at_rejects_non_rfc3339_utc_or_invalid_dates(value):
    assert _drop_reason(lambda c: c["verification"].__setitem__("verified_at", value)) == "VERIFIED_AT_INVALID"


def test_verified_at_accepts_rfc3339_utc_actual_date():
    candidate = _candidate()
    candidate["verification"]["verified_at"] = "2026-12-31T23:59:59Z"
    verdict = _evaluate(candidate)
    assert verdict.accepted is True


@pytest.mark.parametrize(
    "value",
    [
        "digest-only-fixture",
        _digest("evidence-ref"),
        "vault://butler/evidence/case_20260702",
        "keyring://butler/evidence/case-20260702",
    ],
)
def test_evidence_ref_accepts_digest_or_managed_secret_refs_only(value):
    candidate = _candidate()
    candidate["verification"]["evidence_ref"] = value
    verdict = _evaluate(candidate)
    assert verdict.accepted is True


@pytest.mark.parametrize(
    "value",
    [
        "https://example.com/evidence",
        "http://example.com/evidence",
        "file:///tmp/evidence",
        "s3://bucket/key",
        "gs://bucket/key",
        "/Users/alice/evidence.json",
        "/home/alice/evidence.json",
        r"C:\Users\alice\evidence.json",
        r"\\server\share\evidence.json",
        "../evidence.json",
        "~/evidence.json",
        "vault://butler/evidence/alice@example.com",
        "vault://butler/evidence/has space",
        "vault://butler/evidence/with.dot",
    ],
)
def test_evidence_ref_rejects_raw_paths_urls_user_ids_and_whitespace(value):
    reason = _drop_reason(lambda c: c["verification"].__setitem__("evidence_ref", value))
    assert reason == "EVIDENCE_REF_INVALID"


def test_evidence_ref_drop_never_echoes_raw_input():
    raw_value = "/Users/alice/private/evidence.json"
    candidate = _candidate()
    candidate["verification"]["evidence_ref"] = raw_value
    verdict = _evaluate(candidate)
    assert verdict.accepted is False
    assert verdict.drop_reason == "EVIDENCE_REF_INVALID"
    assert raw_value not in verdict.drop_reason


def test_evidence_digest_rejects_invalid_digest():
    assert _drop_reason(lambda c: c["verification"].__setitem__("evidence_digest", "not-digest")) == "EVIDENCE_DIGEST_INVALID"


def test_verification_exact_keys_reject_extra_key():
    assert _drop_reason(lambda c: c["verification"].__setitem__("verified_by_raw", "group_a")) == "SCHEMA_KEYS_INVALID"


def test_verification_exact_keys_reject_missing_key():
    assert _drop_reason(lambda c: c["verification"].pop("evidence_ref")) == "SCHEMA_KEYS_INVALID"


@pytest.mark.parametrize("ref_type", ["messenger", "peer_chat", "folder", "format", "policy", "email"])
def test_chat_context_source_refs_reject_non_usage_log_or_approval(ref_type):
    assert _drop_reason(lambda c: c["source_refs"].__setitem__(0, {"ref_type": ref_type, "ref_id_digest": _digest(ref_type)})) == "SOURCE_REF_INVALID"


def test_chat_context_source_refs_require_at_least_one_usage_log():
    assert _drop_reason(lambda c: c.__setitem__("source_refs", [{"ref_type": "approval", "ref_id_digest": _digest("approval")}])) == "SOURCE_REF_INVALID"


def test_chat_context_source_refs_allow_approval_only_as_auxiliary_ref():
    candidate = _candidate()
    candidate["source_refs"].append({"ref_type": "approval", "ref_id_digest": _digest("approval")})
    verdict = _evaluate(candidate)
    assert verdict.accepted is True


def test_chat_context_source_ref_digest_invalid():
    assert _drop_reason(lambda c: c["source_refs"][0].__setitem__("ref_id_digest", "sha256:not64")) == "SOURCE_REF_INVALID"


@pytest.mark.parametrize(
    "field",
    [
        "integration_mode",
        "raw_text",
        "prompt_text",
        "speaker",
        "employee_name",
        "timestamp_raw",
        "path",
        "url",
        "message_id",
    ],
)
def test_top_level_raw_or_identity_fields_rejected(field):
    reason = _drop_reason(lambda c: c.__setitem__(field, "blocked"))
    assert "FORBIDDEN_FIELD" in reason or "CANDIDATE_UNKNOWN_FIELD" in reason


def test_fixed_drop_reason_set_for_chat_adapter_direct_verification():
    expected = {
        "CHAT_CONTEXT_DISABLED",
        "BUSINESS_CONFIRMATION_REQUIRED",
        "MANAGER_APPROVAL_REQUIRED",
        "SHADOW_EVAL_CASES_TOO_LOW",
        "PII_NOT_ZERO",
        "FALSE_LEARNING_NOT_ZERO",
        "CONTEXT_DIGEST_INVALID",
        "EVIDENCE_DIGEST_INVALID",
        "VERIFIED_BY_INVALID",
        "VERIFIED_AT_INVALID",
        "EVIDENCE_REF_INVALID",
        "SOURCE_REF_INVALID",
        "SCHEMA_KEYS_INVALID",
    }

    adapter = ChatContextAdapter(enabled=True)
    observed = {
        adapter.verify(_mutated(lambda c: c["payload"].__setitem__("explicit_business_confirmation", False))).drop_reason,
        adapter.verify(_mutated(lambda c: c["payload"].__setitem__("manager_or_admin_approved", False))).drop_reason,
        adapter.verify(_mutated(lambda c: c["payload"].__setitem__("shadow_eval_cases", 1))).drop_reason,
        adapter.verify(_mutated(lambda c: c["payload"].__setitem__("pii_zero", False))).drop_reason,
        adapter.verify(_mutated(lambda c: c["payload"].__setitem__("false_learning_zero", False))).drop_reason,
        adapter.verify(_mutated(lambda c: c["payload"].__setitem__("context_digest", "bad"))).drop_reason,
        adapter.verify(_mutated(lambda c: c["verification"].__setitem__("evidence_digest", "bad"))).drop_reason,
        adapter.verify(_mutated(lambda c: c["verification"].__setitem__("verified_by", "bad"))).drop_reason,
        adapter.verify(_mutated(lambda c: c["verification"].__setitem__("verified_at", "bad"))).drop_reason,
        adapter.verify(_mutated(lambda c: c["verification"].__setitem__("evidence_ref", "bad"))).drop_reason,
        adapter.verify(_mutated(lambda c: c.__setitem__("source_refs", []))).drop_reason,
        adapter.verify(_mutated(lambda c: c["payload"].__setitem__("unexpected", True))).drop_reason,
    }
    disabled = ChatContextAdapter(enabled=False).verify(_candidate()).drop_reason
    observed.add(disabled)

    assert observed == expected


@pytest.mark.parametrize(
    ("validator", "value"),
    [
        (validate_verified_by, " group_a"),
        (validate_verified_at, "2026-07-02T00:00:00+09:00"),
        (validate_evidence_ref, "https://example.com/evidence"),
    ],
)
def test_public_provenance_validators_fail_closed(validator, value):
    with pytest.raises(IntegratedLearningError):
        validator(value)


def test_candidate_object_is_deep_copied_on_accept():
    candidate = _candidate()
    verdict = _evaluate(candidate)
    assert verdict.accepted is True
    candidate["payload"]["context_digest"] = _digest("mutated")
    assert verdict.candidate["payload"]["context_digest"] == _digest("chat-context")
