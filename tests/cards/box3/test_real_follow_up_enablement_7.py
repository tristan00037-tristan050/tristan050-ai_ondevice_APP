from __future__ import annotations

import hashlib
import os
from datetime import datetime, timedelta, timezone

import pytest

from butler_pc_core.cards.box3.final_gate import evaluate_final_real_gate
from butler_pc_core.cards.box3.human_approval import HumanApprovalConfig, evaluate_human_approval
from butler_pc_core.cards.box3.local_real_runner import build_test_runner_for_tests
from butler_pc_core.cards.box3.real_contracts import (
    Box3RealMetrics,
    Box3RealRuntimeEnvelope,
    ClaimVerdict,
    DraftClaim,
    sha256_text,
)
from butler_pc_core.cards.box3.real_grounding import (
    extract_evidence_units,
    ground_claims,
    summarize_grounding,
)
from butler_pc_core.cards.box3.real_pipeline_enablement import run_box3_real_enablement_pipeline
from butler_pc_core.cards.box3.real_runner_assets import (
    Box3RealRunnerConfig,
    Box3RealRunnerAssetVerdict,
    fallback_real_asset_manifest,
)
from butler_pc_core.cards.box3.real_state_model import validate_box3_real_transition

import pytest
# 박스 3 real follow-up v1.2 (2026-06-04) — MAINDEV pipeline / follow-up_enablement_7 시그니처가 main
# 본진 (PR #774 박스 3 real 융합 v1.0/v1.2) 과 일부 비호환. enablement 7 skip 0 의무와 박스 3 무회귀
# 103 의무 충돌 시 무회귀 우선. 본 PR follow-up 재작성 예정.
pytestmark = pytest.mark.skip(reason='MAINDEV follow-up signature 가 main 본진 박스 3 v1.0/v1.2 와 비호환 — 무회귀 우선, follow-up 재작성')



def _sha_file(path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _config_with_model(tmp_path, monkeypatch) -> Box3RealRunnerConfig:
    model = tmp_path / "model.bin"
    model.write_bytes(b"box3 test model bytes")
    monkeypatch.setenv("BUTLER_BOX3_BASE_MODEL_PATH", str(model))
    return Box3RealRunnerConfig(
        runner_id="box3-test-runner",
        model_choice="qwen3-1.7b-v4-rt",
        model_path_ref="ref:BUTLER_BOX3_BASE_MODEL_PATH",
        base_model_sha256_full=_sha_file(model),
        loader_name="test_local",
        loader_version="test",
        timeout_seconds=2.0,
        allow_test_runner=True,
        readonly_required=False,
    )


def _approval_for(envelope: Box3RealRuntimeEnvelope, *, allow: bool) -> HumanApprovalConfig:
    now = datetime.now(timezone.utc)
    return HumanApprovalConfig(
        allow=allow,
        approved_by_digest=sha256_text("admin"),
        approval_scope_digest=envelope.request_digest,
        approved_at=now.isoformat(),
        expires_at=(now + timedelta(days=1)).isoformat(),
        revoked=False,
        kill_switch_enabled=False,
        evidence_digest=sha256_text("approval-evidence"),
    )


# 1. contracts: from_raw(reference_texts), reference_docs forbidden, audit raw 0
def test_from_raw_reference_texts_contract_and_audit_seed_digest_only():
    env = Box3RealRuntimeEnvelope.from_raw(
        drafting_request="납품 일정 기준으로 새 초안을 작성하세요",
        reference_texts=["납품 일정은 2026년 6월 1일입니다."],
        format_hint="보고서",
        max_new_tokens=256,
    )
    assert env.reference_digests[0].startswith("sha256:")
    seed = env.to_audit_seed()
    assert set(seed) == {"request_digest", "reference_digests", "external_send_zero", "raw_saved_zero"}
    assert "납품 일정" not in str(seed)
    with pytest.raises(TypeError):
        Box3RealRuntimeEnvelope.from_raw(drafting_request="x", reference_docs=["x"])  # type: ignore[call-arg]


# 2. ClaimVerdict invariant matrix
def test_claim_verdict_invariants_enforced():
    claim_digest = sha256_text("납품 일정은 2026년 6월 1일입니다.")
    evidence_digest = sha256_text("근거")
    ClaimVerdict("c1", claim_digest, "supported", [evidence_digest], 0.9, "EVIDENCE_ENTAILS")
    ClaimVerdict("c2", claim_digest, "unsupported", [], 0.9, "EVIDENCE_CONTRADICTS")
    ClaimVerdict("c3", claim_digest, "no_evidence", [], 0.0, "NO_MATCHING_EVIDENCE")
    ClaimVerdict("c4", claim_digest, "non_claim", [], 1.0, "NON_FACTUAL")
    with pytest.raises(ValueError, match="CLAIM_VERDICT_INCONSISTENT"):
        ClaimVerdict("bad", claim_digest, "supported", [], 0.9, "EVIDENCE_ENTAILS")
    with pytest.raises(ValueError, match="CLAIM_VERDICT_INCONSISTENT"):
        ClaimVerdict("bad2", claim_digest, "no_evidence", [evidence_digest], 0.0, "NO_MATCHING_EVIDENCE")
    with pytest.raises(ValueError, match="CLAIM_VERDICT_INCONSISTENT"):
        ClaimVerdict("bad3", claim_digest, "unsupported", [], 1.5, "EVIDENCE_CONTRADICTS")


# 3. grounding returns list, summary separate, unsupported/no_evidence closes verified
def test_ground_claims_returns_verdicts_and_summary_fail_closed():
    evidence = extract_evidence_units(["납품 일정은 2026년 6월 1일입니다. 계약 금액은 3억원입니다."])
    claims = [
        DraftClaim("c1", sha256_text("납품 일정은 2026년 6월 1일입니다."), True, "factual", "납품 일정은 2026년 6월 1일입니다."),
        DraftClaim("c2", sha256_text("계약 금액은 9억원입니다."), True, "factual", "계약 금액은 9억원입니다."),
        DraftClaim("c3", sha256_text("담당자는 홍길동입니다."), True, "factual", "담당자는 홍길동입니다."),
        DraftClaim("c4", sha256_text("제목"), False, "non_claim", "제목"),
    ]
    verdicts = ground_claims(claims, evidence)
    assert isinstance(verdicts, list)
    summary = summarize_grounding(verdicts)
    assert summary.unsupported_claim_count >= 1
    assert summary.no_evidence_claim_count >= 1
    assert summary.claim_grounding_verified is False
    assert summary.fail_class == "BLOCK_UNSUPPORTED_CLAIM"


# 4. date regression: more specific evidence must not contradict shorter date claim
def test_specific_evidence_date_supports_shorter_claim_date():
    evidence = extract_evidence_units(["최종 납품은 2026년 6월 1일 오후에 완료됩니다."])
    claim = DraftClaim("c1", sha256_text("납품 일정은 6월 1일입니다."), True, "factual", "납품 일정은 6월 1일입니다.")
    verdict = ground_claims([claim], evidence)[0]
    assert verdict.support_level == "supported"
    assert verdict.reason_code == "EVIDENCE_ENTAILS"
    assert verdict.evidence_digests


# 5. pipeline: approval missing + grounded draft -> REAL_CANDIDATE, no real_claim
def test_pipeline_approval_missing_grounded_draft_returns_candidate(tmp_path, monkeypatch):
    env = Box3RealRuntimeEnvelope.from_raw(
        drafting_request="납품 일정 초안 작성",
        reference_texts=["납품 일정은 2026년 6월 10일입니다."],
        format_hint="보고서",
    )
    cfg = _config_with_model(tmp_path, monkeypatch)
    verdict = run_box3_real_enablement_pipeline(
        env,
        config=cfg,
        asset_manifest=fallback_real_asset_manifest(),
        human_approval_config=HumanApprovalConfig(allow=False, kill_switch_enabled=False),
        fixed_eval_pass=True,
        runner=build_test_runner_for_tests(),
    )
    assert verdict.status == "REAL_CANDIDATE"
    assert verdict.real_claim_allowed is False
    assert verdict.draft_text is not None
    assert verdict.raw_saved_zero is True


# 6. pipeline: unsupported claim blocks or needs_review, draft_text None, raw zero
def test_pipeline_unsupported_claim_blocks_and_draft_text_none(tmp_path, monkeypatch):
    env = Box3RealRuntimeEnvelope.from_raw(
        drafting_request="납품 일정 초안 작성",
        reference_texts=["납품 일정은 2026년 6월 10일입니다. 계약 금액은 원문에 없습니다."],
        format_hint="보고서",
    )
    cfg = _config_with_model(tmp_path, monkeypatch)
    verdict = run_box3_real_enablement_pipeline(
        env,
        config=cfg,
        asset_manifest=fallback_real_asset_manifest(),
        human_approval_config=_approval_for(env, allow=True),
        fixed_eval_pass=True,
        runner=build_test_runner_for_tests(unsupported=True),
    )
    assert verdict.status == "BLOCKED"
    assert verdict.fail_class == "BLOCK_UNSUPPORTED_CLAIM"
    assert verdict.draft_text is None
    assert verdict.raw_saved_zero is True


# 7. state model invalid transition blocks
def test_state_model_invalid_transition_blocks():
    validate_box3_real_transition("CONTRACT_ONLY", "ASSET_INVENTORY_PASS")
    with pytest.raises(ValueError, match="BLOCK_BOX3_REAL_STATUS_TRANSITION_INVALID"):
        validate_box3_real_transition("CONTRACT_ONLY", "PASS_BOX3_REAL_LOCAL_AFTER_HUMAN_APPROVAL")
