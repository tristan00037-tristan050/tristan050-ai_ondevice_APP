from __future__ import annotations

import copy

from butler_pc_core.learning_core import UnifiedLearningIntakeGate
from butler_pc_core.learning_core.contracts import stable_json_digest
from tests.learning_core.test_integrated_learning_gate import _candidate, _digest


def _with_payload(candidate, payload, source_type):
    c = copy.deepcopy(candidate)
    c["payload"] = payload
    c["payload_digest"] = stable_json_digest(payload)
    c["learning_source_type"] = source_type
    return c


def test_policy_rule_denied_or_inactive_drops():
    payload = {"policy_status": "DEPRECATED", "active_policy_digest": _digest("policy"), "deny_to_allow_auto": False}
    candidate = _with_payload(_candidate("policy_rule", {}), payload, "verified_policy_rule")
    candidate["adapter_version"] = "policy_rule.v1.2.0"
    verdict = UnifiedLearningIntakeGate.with_default_adapters().evaluate(candidate)
    assert verdict.accepted is False
    assert verdict.drop_reason == "POLICY_NOT_ACTIVE"


def test_company_format_requires_vault_ref_and_template_digest():
    payload = {"format_ref": "vault://formats/invoice-v1", "template_digest": _digest("template"), "format_status": "ACTIVE"}
    candidate = _with_payload(_candidate("company_format", {}), payload, "verified_company_format")
    candidate["adapter_version"] = "company_format.v1.2.0"
    verdict = UnifiedLearningIntakeGate.with_default_adapters().evaluate(candidate)
    assert verdict.accepted is True


def test_approved_fact_drops_deprecated_or_known_bad():
    payload = {"fact_status": "ACTIVE", "fact_digest": _digest("fact"), "known_bad": True, "deprecated": False, "superseded": False}
    candidate = _with_payload(_candidate("approved_fact", {}), payload, "verified_approved_fact")
    candidate["adapter_version"] = "approved_fact.v1.2.0"
    verdict = UnifiedLearningIntakeGate.with_default_adapters().evaluate(candidate)
    assert verdict.accepted is False
    assert verdict.drop_reason == "FACT_KNOWN_BAD_OR_DEPRECATED"


def test_folder_doc_requires_pruned_traversal_and_chunk_digest():
    payload = {
        "folder_ingest_approved": True,
        "traversal_pruned": True,
        "max_depth": 4,
        "max_files": 100,
        "extension": ".pdf",
        "chunk_digest": _digest("chunk"),
        "previous_manifest_digest": _digest("prev"),
    }
    candidate = _with_payload(_candidate("folder_doc", {}), payload, "verified_folder_doc")
    candidate["adapter_version"] = "folder_doc.v1.2.0"
    verdict = UnifiedLearningIntakeGate.with_default_adapters().evaluate(candidate)
    assert verdict.accepted is True


def test_chat_context_default_disabled():
    payload = {
        "explicit_business_confirmation": True,
        "manager_or_admin_approved": True,
        "shadow_eval_cases": 100,
        "pii_zero": True,
        "false_learning_zero": True,
        "context_digest": _digest("chat"),
    }
    candidate = _with_payload(_candidate("chat_context", {}), payload, "verified_chat_context")
    candidate["adapter_version"] = "chat_context.v1.2.0"
    verdict = UnifiedLearningIntakeGate.with_default_adapters().evaluate(candidate)
    assert verdict.accepted is False
    assert verdict.drop_reason == "CHAT_LEARNING_DISABLED"


def test_chat_context_can_be_enabled_only_with_shadow_eval_and_admin_approval():
    payload = {
        "explicit_business_confirmation": True,
        "manager_or_admin_approved": True,
        "shadow_eval_cases": 100,
        "pii_zero": True,
        "false_learning_zero": True,
        "context_digest": _digest("chat"),
    }
    candidate = _with_payload(_candidate("chat_context", {}), payload, "verified_chat_context")
    candidate["adapter_version"] = "chat_context.v1.2.0"
    verdict = UnifiedLearningIntakeGate.with_default_adapters(enable_chat=True).evaluate(candidate)
    assert verdict.accepted is True
