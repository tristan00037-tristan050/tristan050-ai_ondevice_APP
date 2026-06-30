from __future__ import annotations

import copy
from dataclasses import dataclass
from typing import Any

from butler_pc_core.connect_loop.dlp_guard import assert_no_raw_or_secret_material

from .contracts import (
    CANDIDATE_KIND_DETERMINISTIC_RULE_PATCH,
    LEARNING_SOURCE_TYPE,
    RETENTION_CLASS,
    SCHEMA_VERSION,
    TARGET_BOX5_SELF_TRANSFER,
    VerifiedRuleBaseContractError,
    is_sha256,
    validate_candidate_dict,
)


@dataclass(frozen=True)
class GateDecision:
    accepted: bool
    candidate: dict[str, Any] | None
    drop_reason: str | None


def _drop_reason(candidate: dict[str, Any]) -> str | None:
    try:
        validate_candidate_dict(candidate)
    except VerifiedRuleBaseContractError as exc:
        return str(exc).split(":", 1)[0] or "SCHEMA_INVALID"

    if candidate.get("schema_version") != SCHEMA_VERSION:
        return "SCHEMA_VERSION_INVALID"
    if candidate.get("learning_source_type") != LEARNING_SOURCE_TYPE:
        return "LEARNING_SOURCE_TYPE_INVALID"
    if candidate.get("candidate_kind") != CANDIDATE_KIND_DETERMINISTIC_RULE_PATCH:
        return "CANDIDATE_KIND_INVALID"
    if candidate.get("target") != TARGET_BOX5_SELF_TRANSFER:
        return "TARGET_INVALID"
    if candidate.get("policy_decision") != "allow":
        return "POLICY_DECISION_NOT_ALLOW"
    if candidate.get("group_a_verified") is not True:
        return "GROUP_A_NOT_VERIFIED"
    if candidate.get("raw_text_logged") is not False:
        return "RAW_TEXT_LOGGED"
    if candidate.get("external_send_zero") is not True:
        return "EXTERNAL_SEND_NONZERO"
    if candidate.get("model_training") is not False:
        return "MODEL_TRAINING_FORBIDDEN"
    if candidate.get("peft_training") is not False:
        return "PEFT_TRAINING_FORBIDDEN"
    if candidate.get("auto_apply_to_runtime") is not False:
        return "AUTO_APPLY_FORBIDDEN"
    if candidate.get("human_review_required") is not True:
        return "HUMAN_REVIEW_REQUIRED_MISSING"
    if candidate.get("retention_class") != RETENTION_CLASS:
        return "RETENTION_CLASS_INVALID"
    if not is_sha256(candidate.get("approved_rule_token_digest")):
        return "APPROVED_RULE_TOKEN_DIGEST_INVALID"
    if not is_sha256(candidate.get("group_a_report_digest")):
        return "GROUP_A_REPORT_DIGEST_INVALID"

    try:
        assert_no_raw_or_secret_material(candidate)
    except ValueError:
        return "RAW_OR_SECRET_MATERIAL_FORBIDDEN"
    return None


def is_verified_rule_base_candidate(candidate: dict[str, Any]) -> bool:
    return explain_drop_reason(candidate) is None


def explain_drop_reason(candidate: dict[str, Any]) -> str | None:
    if not isinstance(candidate, dict):
        return "CANDIDATE_NOT_OBJECT"
    return _drop_reason(candidate)


def gate_candidate(candidate: dict[str, Any]) -> GateDecision:
    drop = explain_drop_reason(candidate)
    if drop is not None:
        return GateDecision(accepted=False, candidate=None, drop_reason=drop)
    return GateDecision(accepted=True, candidate=copy.deepcopy(candidate), drop_reason=None)
