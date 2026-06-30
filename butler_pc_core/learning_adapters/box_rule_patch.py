from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from butler_pc_core.learning_core.contracts import GateResult, is_sha256

ALLOWED_RULE_TARGETS = frozenset(
    {
        "box5_self_transfer_guard",
        "box1_intent_router_rule",
        "box2_format_rule",
        "box3_grounded_draft_rule",
        "helper1_search_rule",
    }
)

ALLOWED_DIFF_FILES = frozenset(
    {
        "butler_pc_core/company_profile/matcher.py",
        "tests/accounting/test_self_transfer_guard.py",
        "butler_pc_core/accounting/rulebase_learning/rule_tokens.json",
    }
)


@dataclass(frozen=True)
class BoxRulePatchAdapter:
    target_kind: str = "box_rule_patch"

    def verify(self, candidate: dict[str, Any]) -> GateResult:
        payload = candidate.get("payload")
        if not isinstance(payload, dict):
            return GateResult.drop("BOX_RULE_PAYLOAD_MISSING")
        if payload.get("rule_target") not in ALLOWED_RULE_TARGETS:
            return GateResult.drop("BOX_RULE_TARGET_NOT_ALLOWED")
        if payload.get("group_a_fixed_eval_passed") is not True:
            return GateResult.drop("GROUP_A_FIXED_EVAL_NOT_PASSED")
        if payload.get("runtime_hotpatch") is True:
            return GateResult.drop("RUNTIME_HOTPATCH_FORBIDDEN")
        if payload.get("expected_current_digest") is not None and not is_sha256(payload.get("expected_current_digest")):
            return GateResult.drop("EXPECTED_CURRENT_DIGEST_INVALID")
        changed_files = payload.get("changed_files")
        if not isinstance(changed_files, list) or not changed_files:
            return GateResult.drop("CHANGED_FILES_REQUIRED")
        if any(path not in ALLOWED_DIFF_FILES for path in changed_files):
            return GateResult.drop("DIFF_FILE_NOT_ALLOWED")
        tests_to_run = payload.get("tests_to_run")
        if not isinstance(tests_to_run, list) or not tests_to_run:
            return GateResult.drop("TESTS_TO_RUN_REQUIRED")
        if payload.get("proposed_diff_digest") is not None and not is_sha256(payload.get("proposed_diff_digest")):
            return GateResult.drop("PROPOSED_DIFF_DIGEST_INVALID")
        return GateResult.accept(candidate)


def build_pr_candidate_manifest(candidate: dict[str, Any], *, proposed_diff_digest: str) -> dict[str, Any]:
    if not is_sha256(proposed_diff_digest):
        raise ValueError("proposed_diff_digest must be sha256")
    payload = dict(candidate.get("payload") or {})
    return {
        "schema_version": "box_rule_patch_pr_candidate_manifest.v1",
        "candidate_id": candidate["candidate_id"],
        "target_kind": candidate["target_kind"],
        "rule_target": payload.get("rule_target"),
        "changed_files": list(payload.get("changed_files") or []),
        "tests_to_run": list(payload.get("tests_to_run") or []),
        "candidate_digest": candidate["payload_digest"],
        "proposed_diff_digest": proposed_diff_digest,
        "human_review_required": True,
        "auto_apply_to_runtime": False,
    }
