from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping

from butler_pc_core.connect_loop.dlp_guard import assert_no_raw_or_secret_material

from .candidate_gate import gate_candidate
from .contracts import make_candidate, sha256_text
from .diff_builder import RulePatchDiff, build_pr_candidate_manifest, build_unified_diff, manifest_digest
from .queue import RulePatchQueue


class RuleBaseLearningRunError(ValueError):
    pass


@dataclass(frozen=True)
class RuleBaseLearningRunResult:
    queued_candidate: dict[str, Any]
    queue_entry_digest: str
    rule_patch_diff: RulePatchDiff | None
    pr_candidate_manifest: dict[str, Any] | None
    pr_candidate_manifest_digest: str | None


def build_candidate_from_group_a_report(report: dict[str, Any]) -> dict[str, Any]:
    try:
        assert_no_raw_or_secret_material(report)
    except ValueError as exc:
        raise RuleBaseLearningRunError("RAW_OR_SECRET_MATERIAL_FORBIDDEN") from exc
    if report.get("group_a_verified") is not True:
        raise RuleBaseLearningRunError("GROUP_A_NOT_VERIFIED")
    return make_candidate(
        candidate_id=report.get("candidate_id"),
        approved_rule_token_ref=report["approved_rule_token_ref"],
        approved_rule_token_digest=report["approved_rule_token_digest"],
        group_a_report_digest=report["group_a_report_digest"],
        source_usage_log_ids=list(report.get("source_usage_log_ids", [])),
        expected_effect_digest=report["expected_effect_digest"],
        tests_to_run=list(report.get("tests_to_run", [])),
    )


def run_verified_rule_base_flow(
    *,
    group_a_report: dict[str, Any],
    queue_path: str | Path,
    repo_root: str | Path | None = None,
    replacement_text_by_path: Mapping[str, str] | None = None,
    expected_current_digest_by_path: Mapping[str, str] | None = None,
    base_sha: str | None = None,
    head_sha: str | None = None,
) -> RuleBaseLearningRunResult:
    candidate = build_candidate_from_group_a_report(group_a_report)
    decision = gate_candidate(candidate)
    if not decision.accepted or decision.candidate is None:
        raise RuleBaseLearningRunError(decision.drop_reason or "CANDIDATE_REJECTED")

    queue = RulePatchQueue(queue_path)
    queued = queue.append(decision.candidate)
    queue_digest = sha256_text(json.dumps(queued, ensure_ascii=False, sort_keys=True))

    rule_patch_diff: RulePatchDiff | None = None
    manifest: dict[str, Any] | None = None
    manifest_hash: str | None = None
    if replacement_text_by_path:
        if repo_root is None or base_sha is None or head_sha is None:
            raise RuleBaseLearningRunError("PR_CANDIDATE_SHA_REQUIRED")
        expected_digests = expected_current_digest_by_path or group_a_report.get(
            "expected_current_digest_by_path",
            {},
        )
        rule_patch_diff = build_unified_diff(
            repo_root,
            replacement_text_by_path,
            expected_current_digest_by_path=expected_digests,
        )
        manifest = build_pr_candidate_manifest(
            candidate=queued,
            rule_patch_diff=rule_patch_diff,
            base_sha=base_sha,
            head_sha=head_sha,
        )
        manifest_hash = manifest_digest(manifest)

    return RuleBaseLearningRunResult(
        queued_candidate=queued,
        queue_entry_digest=queue_digest,
        rule_patch_diff=rule_patch_diff,
        pr_candidate_manifest=manifest,
        pr_candidate_manifest_digest=manifest_hash,
    )
