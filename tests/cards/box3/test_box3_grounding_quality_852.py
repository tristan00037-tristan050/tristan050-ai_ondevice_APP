from __future__ import annotations

from collections import Counter

from butler_pc_core.cards.box3.actual_fail_class import (
    BLOCK_NO_FACTUAL_CLAIMS,
    BLOCKED,
    FAIL_CLASS_SEVERITY,
    NEEDS_REVIEW_OUTPUT_SKELETON_ECHO,
    is_blocking_actual_fail_class,
)
from butler_pc_core.cards.box3.actual_operation_pipeline import (
    _is_output_skeleton_echo,
    _status_from_gate,
)
from butler_pc_core.cards.box3.helper_sdk_bridge import (
    HelperSdkBridge,
    _factual_digests_for_helper4,
    _promoted_verdict,
)
from butler_pc_core.cards.box3.real_contracts import ClaimVerdict, EvidenceUnit, sha256_text

DIGEST_A = "sha256:" + "a" * 64
DIGEST_B = "sha256:" + "b" * 64


class _EvidenceStub:
    def __init__(self, text: str):
        self.evidence_units_runtime = [
            EvidenceUnit(
                evidence_id="e1",
                evidence_digest="sha256:" + "c" * 64,
                source_digest="sha256:" + "d" * 64,
                kind="text",
                text_runtime_only=text,
            )
        ]


# === 작업1: factual 판정 보강 (승격만 허용) ===

def test_furniture_input_factual_claim_count_recovers_above_zero():
    # 가구/조달 재현: SDK 좁은 사전이 non_claim 처리하던 사실 서술이 승격돼 count>0.
    bridge = HelperSdkBridge.from_env()
    eb = bridge.parse_evidence(["사무가구 조달 요약. 계약 금액 3천만 원. 납품처 서울시청."])
    draft = (
        "제목: 조달 요약\n"
        "배경: 대상 기관은 서울시청입니다.\n"
        "핵심내용: 품목은 사무용 책상입니다.\n"
        "최종문안: 문서를 검토합니다."
    )
    gb = bridge.ground_claims(draft, eb)
    assert gb.summary.factual_claim_count >= 1
    assert gb.fail_class != BLOCK_NO_FACTUAL_CLAIMS


def test_promotion_matches_bundled_helper4_value_only_digest():
    draft = "핵심내용: 납품 장소는 본사 1층 자재 창고입니다"
    value_digest = sha256_text("본사 1층 자재 창고")

    assert value_digest in _factual_digests_for_helper4(draft)

    bridge = HelperSdkBridge.from_env()
    evidence = bridge.parse_evidence(["납품 장소는 본사 1층 자재 창고입니다"])
    grounded = bridge.ground_claims(draft, evidence)

    assert grounded.summary.factual_claim_count == 1
    assert grounded.fail_class != BLOCK_NO_FACTUAL_CLAIMS
    assert any(
        verdict.claim_digest == value_digest
        and verdict.support_level == "no_evidence"
        and verdict.reason_code == "NO_MATCHING_EVIDENCE"
        for verdict in grounded.claim_verdicts
    )


def test_promotion_only_lifts_non_claim_to_no_evidence():
    factual = {DIGEST_A}
    v = ClaimVerdict("c1", DIGEST_A, "non_claim", [], 0.0, "NON_FACTUAL")
    out = _promoted_verdict(v, factual)
    assert out.support_level == "no_evidence"
    assert out.reason_code == "NO_MATCHING_EVIDENCE"
    assert out.evidence_digests == []
    assert out.claim_digest == DIGEST_A and out.claim_id == "c1"


def test_promotion_skips_non_claim_not_in_factual_set():
    v = ClaimVerdict("c1", DIGEST_A, "non_claim", [], 0.0, "NON_FACTUAL")
    out = _promoted_verdict(v, set())  # digest 가 factual 집합에 없음
    assert out.support_level == "non_claim"


def test_promotion_never_weakens_or_changes_unsupported_or_supported():
    factual = {DIGEST_A, DIGEST_B}
    unsupported = ClaimVerdict("c1", DIGEST_A, "unsupported", [], 0.5, "EVIDENCE_CONTRADICTS")
    supported = ClaimVerdict("c2", DIGEST_B, "supported", ["sha256:" + "e" * 64], 0.9, "EVIDENCE_ENTAILS")
    assert _promoted_verdict(unsupported, factual) is unsupported  # 불변
    assert _promoted_verdict(supported, factual) is supported


def test_promotion_leaves_existing_no_evidence_untouched():
    factual = {DIGEST_A}
    ne = ClaimVerdict("c1", DIGEST_A, "no_evidence", [], 0.0, "NO_MATCHING_EVIDENCE")
    assert _promoted_verdict(ne, factual) is ne


# === 작업2: 골격 문구 에코 감지 ===

def test_skeleton_echo_detected_when_placeholder_leaks():
    ev = _EvidenceStub("납품처는 서울시청이다.")
    echo = (
        "제목: 주제 정보 요약\n"
        "배경: 근거1 항목명은/는 근거1 복사할 값입니다.\n"
        "최종문안: 위 내용은 근거 범위에서 확인합니다."
    )
    assert _is_output_skeleton_echo(echo, ev) is True


def test_normal_draft_is_not_flagged_as_skeleton_echo():
    ev = _EvidenceStub("납품처는 서울시청이다.")
    normal = "핵심내용: 납품처는 서울시청입니다. (근거1)"
    assert _is_output_skeleton_echo(normal, ev) is False


def test_skeleton_marker_present_in_evidence_is_not_echo():
    # 마커가 실제 근거에도 있으면 에코가 아니다(정상).
    ev = _EvidenceStub("문서 제목은 주제 정보 요약이다.")
    draft = "제목: 주제 정보 요약"
    assert _is_output_skeleton_echo(draft, ev) is False


def test_skeleton_echo_downgrades_hardblock_to_needs_review_delivery():
    assert FAIL_CLASS_SEVERITY[NEEDS_REVIEW_OUTPUT_SKELETON_ECHO] == "needs_review"
    assert is_blocking_actual_fail_class(NEEDS_REVIEW_OUTPUT_SKELETON_ECHO) is False
    status, real_allowed, fail_class, _ = _status_from_gate(
        base_status="ASSET_INVENTORY_PASS",
        helper_fail=None,
        parse_fail=None,
        runner_ok=True,
        runner_fail=None,
        bridge_fail=NEEDS_REVIEW_OUTPUT_SKELETON_ECHO,
        metrics=None,
        fixed_eval_pass=True,
        approval_allowed=True,
        approval_fail=None,
        test_only_runner=False,
    )
    assert status != BLOCKED
    assert fail_class == NEEDS_REVIEW_OUTPUT_SKELETON_ECHO
