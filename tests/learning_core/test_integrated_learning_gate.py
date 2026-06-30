from __future__ import annotations

import copy
import inspect

from butler_pc_core.learning_core import UnifiedLearningIntakeGate
from butler_pc_core.learning_core.contracts import stable_json_digest


def _digest(value="x"):
    return "sha256:" + ("%064x" % abs(hash(str(value))))[-64:]


def _base_payload():
    return {
        "rule_target": "box5_self_transfer_guard",
        "group_a_fixed_eval_passed": True,
        "expected_current_digest": _digest("matcher-current"),
        "changed_files": [
            "butler_pc_core/company_profile/matcher.py",
            "tests/accounting/test_self_transfer_guard.py",
        ],
        "tests_to_run": ["python3 -m pytest tests/accounting/test_self_transfer_guard.py -q"],
        "runtime_hotpatch": False,
    }


def _candidate(target_kind="box_rule_patch", payload=None):
    payload = _base_payload() if payload is None else payload
    return {
        "schema_version": "integrated_learning_candidate.v1",
        "candidate_id": "ilc-" + "a" * 32,
        "target_kind": target_kind,
        "adapter_version": "box_rule_patch.v1.2.0",
        "learning_source_type": "verified_box_rule_patch",
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
            "verified_at": "2026-06-30T00:00:00Z",
            "evidence_digest": _digest("evidence"),
            "evidence_ref": "digest-only-fixture",
        },
        "source_refs": [{"ref_type": "usage_log", "ref_id_digest": _digest("source")}],
        "payload_digest": stable_json_digest(payload),
        "expected_effect_digest": _digest("expected"),
        "payload": payload,
    }


def test_box_rule_patch_candidate_is_accepted():
    verdict = UnifiedLearningIntakeGate.with_default_adapters().evaluate(_candidate())
    assert verdict.accepted is True
    assert verdict.drop_reason is None


def test_unknown_field_fails_closed():
    candidate = _candidate()
    candidate["unexpected"] = True
    verdict = UnifiedLearningIntakeGate.with_default_adapters().evaluate(candidate)
    assert verdict.accepted is False
    assert "CANDIDATE_UNKNOWN_FIELD" in verdict.drop_reason


def test_integration_mode_spoof_rejected():
    candidate = _candidate()
    candidate["integration_mode"] = "real"
    verdict = UnifiedLearningIntakeGate.with_default_adapters().evaluate(candidate)
    assert verdict.accepted is False
    assert "FORBIDDEN_FIELD" in verdict.drop_reason or "INTEGRATION_MODE" in verdict.drop_reason


def test_raw_field_rejected_anywhere():
    candidate = _candidate()
    candidate["payload"]["raw_memo"] = "사내 자금이동"
    candidate["payload_digest"] = stable_json_digest(candidate["payload"])
    verdict = UnifiedLearningIntakeGate.with_default_adapters().evaluate(candidate)
    assert verdict.accepted is False
    assert "FORBIDDEN_FIELD" in verdict.drop_reason


def test_auto_apply_model_and_peft_forbidden():
    for field in ["auto_apply_to_runtime", "model_training", "peft_training"]:
        candidate = _candidate()
        candidate[field] = True
        verdict = UnifiedLearningIntakeGate.with_default_adapters().evaluate(candidate)
        assert verdict.accepted is False, field


def test_payload_digest_mismatch_rejected():
    candidate = _candidate()
    candidate["payload"]["runtime_hotpatch"] = True
    verdict = UnifiedLearningIntakeGate.with_default_adapters().evaluate(candidate)
    assert verdict.accepted is False
    assert "PAYLOAD_DIGEST_MISMATCH" in verdict.drop_reason


def test_unregistered_target_kind_fails_before_adapter():
    candidate = _candidate()
    candidate["target_kind"] = "not_registered"
    candidate["learning_source_type"] = "verified_box_rule_patch"
    verdict = UnifiedLearningIntakeGate.with_default_adapters().evaluate(candidate)
    assert verdict.accepted is False
    assert "TARGET_KIND_INVALID" in verdict.drop_reason


def test_existing_connect_loop_learning_candidate_gate_real_invariant_preserved():
    # This is a regression lock, not a new integration path. It ensures the
    # existing PR-A/PR-E usage_log gate still requires real validated usage logs.
    from butler_pc_core.connect_loop.learning_candidate_gate import _is_candidate_usage_log

    source = inspect.getsource(_is_candidate_usage_log)
    assert 'integration_mode") == "real"' in source or "integration_mode') == 'real'" in source
    assert "real_validation_done" in source
    assert "raw_text_logged" in source
