"""박스 3 real follow-up v1.2 정정 (2026-06-04) — main 본진(#775 머지본) 실제 시그니처 재작성.

7건 enablement skip 0. 본진 실제 API (from_raw / ClaimVerdict __post_init__ /
ground_claims list + summarize_grounding / 날짜 entailment / pipeline / state model 전이) 로
재작성. 본진 코드 약화 0 (필드 default / property alias / pipeline 본문 정정 추가만).
"""
from __future__ import annotations

import hashlib

import pytest

from butler_pc_core.cards.box3.human_approval import HumanApprovalConfig
from butler_pc_core.cards.box3.local_real_runner import build_test_runner_for_tests
from butler_pc_core.cards.box3.real_contracts import (
    Box3RealRuntimeEnvelope,
    ClaimVerdict,
    sha256_text,
    validate_box3_real_status_transition,
)
from butler_pc_core.cards.box3.real_grounding import (
    extract_claims,
    extract_evidence_units,
    ground_claims,
    summarize_grounding,
)
from butler_pc_core.cards.box3.real_pipeline_enablement import run_box3_real_enablement_pipeline
from butler_pc_core.cards.box3.real_runner_assets import (
    Box3RealRunnerConfig,
    fallback_real_asset_manifest,
)


@pytest.fixture
def cfg(tmp_path, monkeypatch):
    model = tmp_path / "model.gguf"
    model.write_bytes(b"butler-box3-test-model-bytes-7enablement")
    digest = hashlib.sha256(model.read_bytes()).hexdigest()
    monkeypatch.setenv("BUTLER_BOX3_BASE_MODEL_PATH", str(model))
    return Box3RealRunnerConfig(
        runner_id="r1",
        model_choice="qwen3-1.7b-v4-rt",
        model_path_ref="ref:BUTLER_BOX3_BASE_MODEL_PATH",
        base_model_sha256_full=digest,
        allow_test_runner=True,
        readonly_required=False,
    )


def test_from_raw_reference_texts_contract_and_audit_seed_digest_only():
    """본진 from_raw(reference_texts=) only contract + audit seed digest-only."""
    env = Box3RealRuntimeEnvelope.from_raw(
        reference_texts=["참고 문서에는 납품 일정이 2026-06-10로 명시되어 있습니다."],
        drafting_request="납품 일정 보고서 초안.",
    )
    # reference_text_runtime_only 보존 + reference_docs_runtime_only property alias.
    assert env.reference_text_runtime_only == ["참고 문서에는 납품 일정이 2026-06-10로 명시되어 있습니다."]
    assert env.reference_docs_runtime_only == env.reference_text_runtime_only
    # request_digest 정합 (sha256: prefix).
    assert env.request_digest.startswith("sha256:")
    # to_audit_seed digest-only — raw 누출 0.
    seed = env.to_audit_seed()
    assert seed["raw_saved_zero"] is True
    assert seed["external_send_zero"] is True
    assert "납품" not in str(seed)
    assert "drafting_request_runtime" not in seed


def test_claim_verdict_invariants_enforced():
    """본 PR 정정 (Codex 흡수) — ClaimVerdict __post_init__ 불변식 fail-closed."""
    valid = ClaimVerdict(
        claim_id="c1",
        claim_digest=sha256_text("claim"),
        support_level="supported",
        evidence_digests=[sha256_text("e1")],
        confidence=0.9,
        reason_code="EVIDENCE_ENTAILS",
    )
    assert valid.support_level == "supported"

    # support_level ↔ reason_code 비일관 → CLAIM_VERDICT_INCONSISTENT.
    with pytest.raises(ValueError):
        ClaimVerdict(
            claim_id="c2",
            claim_digest=sha256_text("c2"),
            support_level="supported",
            evidence_digests=[sha256_text("e2")],
            confidence=0.9,
            reason_code="NO_MATCHING_EVIDENCE",
        )

    # supported + evidence 비어있음 → 불변식 위반.
    with pytest.raises(ValueError):
        ClaimVerdict(
            claim_id="c3",
            claim_digest=sha256_text("c3"),
            support_level="supported",
            evidence_digests=[],
            confidence=0.9,
            reason_code="EVIDENCE_ENTAILS",
        )

    # confidence out of range.
    with pytest.raises(ValueError):
        ClaimVerdict(
            claim_id="c4",
            claim_digest=sha256_text("c4"),
            support_level="non_claim",
            evidence_digests=[],
            confidence=1.5,
            reason_code="NON_FACTUAL",
        )

    # claim_digest invalid format.
    with pytest.raises(ValueError):
        ClaimVerdict(
            claim_id="c5",
            claim_digest="not-a-digest",
            support_level="non_claim",
            evidence_digests=[],
            confidence=0.5,
            reason_code="NON_FACTUAL",
        )


def test_ground_claims_returns_list_summary_separate_fail_closed():
    """본진 ground_claims → list[ClaimVerdict] (tuple 아님), summary 별도 함수."""
    refs = ["참고 문서에는 납품 일정이 2026-06-10로 명시되어 있습니다."]
    evidence = extract_evidence_units(refs)
    claims = extract_claims("핵심 내용: 납품 일정은 2026-06-10입니다.")
    verdicts = ground_claims(claims, evidence)
    assert isinstance(verdicts, list)
    for v in verdicts:
        assert isinstance(v, ClaimVerdict)
    summary = summarize_grounding(verdicts)
    assert summary is not None
    # ClaimGroundingSummary 본진 필드 — claim_grounding_verified / unsupported_claim_count / fail_class.
    assert hasattr(summary, "claim_grounding_verified")
    assert hasattr(summary, "unsupported_claim_count")
    assert hasattr(summary, "fail_class")


def test_specific_evidence_date_supports_shorter_claim_date():
    """본진 _facts() 날짜 분해 (PR #771 v1.0 정정) — 구체 evidence 날짜가 짧은 claim 날짜 포섭."""
    refs = ["납품 기한은 2026년 6월 1일입니다."]
    evidence = extract_evidence_units(refs)
    claims = extract_claims("핵심 내용: 납품 기한은 6월 1일입니다")
    verdicts = ground_claims(claims, evidence)
    factual = [v for v in verdicts if v.support_level != "non_claim"]
    assert factual, "no factual claim extracted"
    assert any(
        v.support_level == "supported" and v.reason_code == "EVIDENCE_ENTAILS"
        for v in factual
    )


def test_pipeline_approval_missing_grounded_draft_returns_candidate(cfg):
    """grounded draft + approval 미공급 → REAL_CANDIDATE + BLOCK_HUMAN_APPROVAL_MISSING."""
    env = Box3RealRuntimeEnvelope.from_raw(
        reference_texts=["참고 문서에는 납품 일정이 2026-06-10로 명시되어 있습니다."],
        drafting_request="납품 일정 보고서 초안.",
    )
    verdict = run_box3_real_enablement_pipeline(
        env,
        config=cfg,
        asset_manifest=fallback_real_asset_manifest(),
        human_approval_config=HumanApprovalConfig(kill_switch_enabled=False),
        fixed_eval_pass=True,
        runner=build_test_runner_for_tests(),
    )
    assert verdict.status == "REAL_CANDIDATE"
    assert verdict.fail_class == "BLOCK_HUMAN_APPROVAL_MISSING"
    assert verdict.real_claim_allowed is False
    # draft_text 노출 — REAL_CANDIDATE status 본진 정의 (response_draft 허용).
    # 다만 raw_saved_zero / external_send_zero 정합 보존.
    assert verdict.raw_saved_zero is True
    assert verdict.external_send_zero is True


def test_pipeline_unsupported_claim_blocks_and_draft_text_none(cfg):
    """unsupported claim 본진 BLOCKED + draft_text None."""
    def bad_runner(envelope):
        return (
            "제목: 초안\n"
            "배경: 검토 완료.\n"
            "핵심 내용: 납품 일정은 2026-06-20입니다.\n"
            "근거: 참고 문서.\n"
            "확인 필요: 없음.\n"
            "최종 문안: 2026-06-20."
        )
    env = Box3RealRuntimeEnvelope.from_raw(
        reference_texts=["참고 문서에는 납품 일정이 2026-06-10로 명시되어 있습니다."],
        drafting_request="납품 일정 보고서.",
    )
    verdict = run_box3_real_enablement_pipeline(
        env,
        config=cfg,
        asset_manifest=fallback_real_asset_manifest(),
        human_approval_config=HumanApprovalConfig(kill_switch_enabled=False),
        fixed_eval_pass=True,
        runner=bad_runner,
    )
    assert verdict.status == "BLOCKED"
    assert verdict.real_claim_allowed is False
    # BLOCKED → response_draft 분기에 포함 안 됨 → draft_text None.
    assert verdict.draft_text is None
    assert verdict.raw_saved_zero is True


def test_state_model_invalid_transition_blocks():
    """본진 validate_box3_real_status_transition (ALG 흡수) — invalid 전이 BLOCK."""
    # 정합 전이 (CONTRACT_ONLY → ASSET_INVENTORY_PASS) OK.
    validate_box3_real_status_transition("CONTRACT_ONLY", "ASSET_INVENTORY_PASS")
    # invalid 전이 (PASS → REAL_CANDIDATE) BLOCK_BOX3_REAL_STATUS_TRANSITION_INVALID.
    with pytest.raises(ValueError, match="BLOCK_BOX3_REAL_STATUS_TRANSITION_INVALID"):
        validate_box3_real_status_transition(
            "PASS_BOX3_REAL_LOCAL_AFTER_HUMAN_APPROVAL", "REAL_CANDIDATE"
        )
    # invalid 라벨 자체.
    with pytest.raises(ValueError, match="BLOCK_BOX3_REAL_STATUS_TRANSITION_INVALID"):
        validate_box3_real_status_transition("CONTRACT_ONLY", "UNKNOWN_LABEL")
