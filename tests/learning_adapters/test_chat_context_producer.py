from __future__ import annotations

import json
from pathlib import Path

from butler_pc_core.learning_adapters.chat_context_producer import (
    PAYLOAD_KEYS,
    build_chat_context_candidate,
    ingest_verified_chat_context,
)
from butler_pc_core.learning_core.contracts import stable_json_digest
from butler_pc_core.learning_core.runner import LearningIntakeRunner


def _digest(value: str) -> str:
    return "sha256:" + ("%064x" % abs(hash(value)))[-64:]


def _artifact(**overrides):
    data = {
        "explicit_business_confirmation": True,
        "manager_or_admin_approved": True,
        "shadow_eval_cases": 100,
        "pii_zero": True,
        "false_learning_zero": True,
        "context_digest": _digest("context"),
        "expected_effect_digest": _digest("effect"),
        "evidence_digest": _digest("evidence"),
        "source_refs": [{"ref_type": "usage_log", "ref_id_digest": _digest("usage-log")}],
    }
    data.update(overrides)
    return data


def _runner(tmp_path: Path, *, enable_chat: bool) -> LearningIntakeRunner:
    return LearningIntakeRunner.default(tmp_path / "queue.jsonl", enable_chat=enable_chat)


def test_chat_context_verified_ingest_accepts_with_enable_chat(tmp_path):
    result = ingest_verified_chat_context(_artifact(), _runner(tmp_path, enable_chat=True))
    assert result["accepted"] is True
    assert result["queue_appended"] is True
    assert result["record_digest"].startswith("sha256:")


def test_chat_context_default_disabled_drops(tmp_path):
    result = ingest_verified_chat_context(_artifact(), _runner(tmp_path, enable_chat=False))
    assert result["accepted"] is False
    assert result["drop_reason"] == "CHAT_LEARNING_DISABLED"
    assert result["queue_appended"] is False


def test_chat_context_shadow_eval_threshold_and_type_drop(tmp_path):
    low = ingest_verified_chat_context(_artifact(shadow_eval_cases=99), _runner(tmp_path, enable_chat=True))
    assert low["accepted"] is False
    assert low["drop_reason"] == "CHAT_SHADOW_EVAL_INSUFFICIENT"

    stringy = ingest_verified_chat_context(_artifact(shadow_eval_cases="100"), _runner(tmp_path, enable_chat=True))
    assert stringy["accepted"] is False
    assert stringy["drop_reason"] == "SHADOW_EVAL_CASES_INVALID"

    boolish = ingest_verified_chat_context(_artifact(shadow_eval_cases=True), _runner(tmp_path, enable_chat=True))
    assert boolish["accepted"] is False
    assert boolish["drop_reason"] == "SHADOW_EVAL_CASES_INVALID"


def test_chat_context_bool_strings_drop_before_queue(tmp_path):
    for field, code in [
        ("explicit_business_confirmation", "EXPLICIT_BUSINESS_CONFIRMATION_INVALID"),
        ("manager_or_admin_approved", "MANAGER_OR_ADMIN_APPROVED_INVALID"),
        ("pii_zero", "PII_ZERO_INVALID"),
        ("false_learning_zero", "FALSE_LEARNING_ZERO_INVALID"),
    ]:
        result = ingest_verified_chat_context(_artifact(**{field: "true"}), _runner(tmp_path, enable_chat=True))
        assert result["accepted"] is False
        assert result["drop_reason"] == code


def test_chat_context_pii_or_false_learning_false_drops_at_adapter(tmp_path):
    pii = ingest_verified_chat_context(_artifact(pii_zero=False), _runner(tmp_path, enable_chat=True))
    assert pii["accepted"] is False
    assert pii["drop_reason"] == "CHAT_SHADOW_EVAL_FAILED"

    false_learning = ingest_verified_chat_context(_artifact(false_learning_zero=False), _runner(tmp_path, enable_chat=True))
    assert false_learning["accepted"] is False
    assert false_learning["drop_reason"] == "CHAT_SHADOW_EVAL_FAILED"


def test_chat_context_digest_invalid_drops(tmp_path):
    result = ingest_verified_chat_context(_artifact(context_digest="not-a-digest"), _runner(tmp_path, enable_chat=True))
    assert result["accepted"] is False
    assert result["drop_reason"] == "CHAT_CONTEXT_DIGEST_INVALID"


def test_chat_context_source_refs_allow_usage_log_and_approval_only(tmp_path):
    approval = _artifact(source_refs=[{"ref_type": "approval", "ref_id_digest": _digest("approval")}])
    assert ingest_verified_chat_context(approval, _runner(tmp_path, enable_chat=True))["accepted"] is True

    rejected = _artifact(source_refs=[{"ref_type": "folder", "ref_id_digest": _digest("folder")}])
    result = ingest_verified_chat_context(rejected, _runner(tmp_path, enable_chat=True))
    assert result["accepted"] is False
    assert result["drop_reason"] == "SOURCE_REF_TYPE_INVALID"


def test_chat_context_source_refs_malformed_controlled_drop(tmp_path):
    result = ingest_verified_chat_context(_artifact(source_refs={"ref_type": "usage_log"}), _runner(tmp_path, enable_chat=True))
    assert result["accepted"] is False
    assert result["drop_reason"] == "SOURCE_REFS_NOT_SEQUENCE"


def test_chat_context_raw_and_unknown_artifact_fields_drop_without_echo(tmp_path):
    result = ingest_verified_chat_context(_artifact(prompt="do not store"), _runner(tmp_path, enable_chat=True))
    assert result["accepted"] is False
    assert result["drop_reason"] == "FORBIDDEN_FIELD"
    assert "do not store" not in json.dumps(result, ensure_ascii=False)

    unknown = ingest_verified_chat_context(_artifact(custom_flag=True), _runner(tmp_path, enable_chat=True))
    assert unknown["accepted"] is False
    assert unknown["drop_reason"] == "ARTIFACT_UNKNOWN_FIELD"


def test_chat_context_candidate_envelope_is_digest_only_and_exact_payload():
    candidate = build_chat_context_candidate(_artifact())
    assert candidate["schema_version"] == "integrated_learning_candidate.v1"
    assert candidate["target_kind"] == "chat_context"
    assert candidate["learning_source_type"] == "verified_chat_context"
    assert candidate["adapter_version"] == "chat_context_producer.v1.0.0"
    assert set(candidate["payload"]) == PAYLOAD_KEYS
    assert candidate["payload_digest"] == stable_json_digest(candidate["payload"])
    assert candidate["raw_text_logged"] is False
    assert candidate["external_send_zero"] is True
    assert candidate["model_training"] is False
    assert candidate["peft_training"] is False
    assert candidate["human_review_required"] is True
    assert candidate["auto_apply_to_runtime"] is False
    assert "integration_mode" not in candidate
    for ref in candidate["source_refs"]:
        assert ref["ref_type"] in {"usage_log", "approval"}


def test_chat_context_ingest_summary_is_digest_safe(tmp_path):
    result = ingest_verified_chat_context(_artifact(), _runner(tmp_path, enable_chat=True))
    allowed = {"accepted", "drop_reason", "queue_appended", "queue_reason", "candidate_id", "target_kind", "payload_digest", "record_digest"}
    assert set(result) == allowed
    dumped = json.dumps(result, ensure_ascii=False)
    assert "vault://" not in dumped
    assert "keyring://" not in dumped


def test_chat_context_queue_idempotent_duplicate(tmp_path):
    runner = _runner(tmp_path, enable_chat=True)
    first = ingest_verified_chat_context(_artifact(), runner)
    second = ingest_verified_chat_context(_artifact(), runner)
    assert first["accepted"] is True and first["queue_appended"] is True
    assert second["accepted"] is True and second["queue_appended"] is False
    assert second["queue_reason"] == "IDEMPOTENT_DUPLICATE"


def test_chat_context_valid_contract_not_overblocked(tmp_path):
    result = ingest_verified_chat_context(_artifact(shadow_eval_cases=250), _runner(tmp_path, enable_chat=True))
    assert result["accepted"] is True
    assert result["drop_reason"] is None


def test_chat_context_peer_like_source_ref_type_is_blocked(tmp_path):
    artifact = _artifact(source_refs=[{"ref_type": "peer_chat", "ref_id_digest": _digest("peer")}])
    result = ingest_verified_chat_context(artifact, _runner(tmp_path, enable_chat=True))
    assert result["accepted"] is False
    assert result["drop_reason"] == "SOURCE_REF_TYPE_INVALID"
