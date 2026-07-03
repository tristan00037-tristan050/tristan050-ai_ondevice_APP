from __future__ import annotations

from butler_pc_core.learning_core import UnifiedLearningIntakeGate
from butler_pc_core.learning_core.contracts import stable_json_digest
from tests.learning_core.test_integrated_learning_gate import _candidate, _digest


def _chat_payload(value=100):
    return {
        "explicit_business_confirmation": True,
        "manager_or_admin_approved": True,
        "shadow_eval_cases": value,
        "pii_zero": True,
        "false_learning_zero": True,
        "context_digest": _digest("chat"),
    }


def _chat_candidate(payload):
    c = _candidate("chat_context", payload)
    c["learning_source_type"] = "verified_chat_context"
    c["adapter_version"] = "chat_context.v1.2.0"
    c["payload_digest"] = stable_json_digest(payload)
    return c


def test_chat_context_default_disabled():
    verdict = UnifiedLearningIntakeGate.with_default_adapters().evaluate(_chat_candidate(_chat_payload()))
    assert verdict.accepted is False
    assert verdict.drop_reason == "CHAT_CONTEXT_DISABLED"


def test_chat_context_legacy_fixture_accepts_when_enabled():
    verdict = UnifiedLearningIntakeGate.with_default_adapters(enable_chat=True, chat_run_mode="fixture_test").evaluate(
        _chat_candidate(_chat_payload())
    )
    assert verdict.accepted is True


def test_chat_context_drops_non_numeric_shadow_eval_cases_when_enabled():
    verdict = UnifiedLearningIntakeGate.with_default_adapters(enable_chat=True, chat_run_mode="fixture_test").evaluate(
        _chat_candidate(_chat_payload("100"))
    )
    assert verdict.accepted is False
    assert verdict.drop_reason == "SHADOW_EVAL_CASES_TOO_LOW"
