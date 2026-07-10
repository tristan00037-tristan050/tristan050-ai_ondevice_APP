from __future__ import annotations

from butler_pc_core.cards.box3.actual_fail_class import (
    BLOCK_NO_FACTUAL_CLAIMS,
    FAIL_CLASS_SEVERITY,
    is_blocking_actual_fail_class,
)
from butler_pc_core.cards.box3.actual_contracts import Box3ActualRuntimeEnvelope
from butler_pc_core.cards.box3.endpoint_wiring import (
    _contract_only_actual_response,
    _derive_terminal_stage,
    normalize_actual_verdict_to_legacy_response,
)


# === BLOCK_NO_FACTUAL_CLAIMS 상수화 + severity 등록 ===
# (helper8 repr fail-closed 는 PR #849 로 일원화 — 본 PR 범위 아님)

def test_block_no_factual_claims_registered_as_block_provisional():
    assert BLOCK_NO_FACTUAL_CLAIMS == "BLOCK_NO_FACTUAL_CLAIMS"
    assert FAIL_CLASS_SEVERITY[BLOCK_NO_FACTUAL_CLAIMS] == "block"
    assert is_blocking_actual_fail_class(BLOCK_NO_FACTUAL_CLAIMS) is True


def test_real_grounding_uses_the_registered_constant_for_zero_factual_claims():
    from butler_pc_core.cards.box3.real_grounding import summarize_grounding

    # 사실 문장 0건이면 BLOCK_NO_FACTUAL_CLAIMS (상수 참조).
    summary = summarize_grounding([])
    assert summary.fail_class == BLOCK_NO_FACTUAL_CLAIMS


def _envelope() -> Box3ActualRuntimeEnvelope:
    return Box3ActualRuntimeEnvelope.from_raw(
        reference_texts=["참고 문서"],
        drafting_request="초안 작성",
    )


def test_endpoint_terminal_stage_prefers_root_failure_over_final_gate():
    response = normalize_actual_verdict_to_legacy_response(
        {
            "status": "BLOCKED",
            "draft_text": None,
            "fail_class": BLOCK_NO_FACTUAL_CLAIMS,
            "real_claim_allowed": False,
            "stage_trace": [
                {"stage": "helper4_grounding", "passed": False, "fail_class": BLOCK_NO_FACTUAL_CLAIMS},
                {"stage": "final_gate", "status": "BLOCKED", "fail_class": BLOCK_NO_FACTUAL_CLAIMS},
            ],
        },
        envelope=_envelope(),
        approval_config_digest=None,
        runner_injected=False,
    )

    assert response["terminal_stage"] == "helper4_grounding"


def test_endpoint_terminal_stage_falls_back_to_final_gate():
    response = normalize_actual_verdict_to_legacy_response(
        {
            "status": "REAL_CANDIDATE",
            "draft_text": "제목: 검토 후보",
            "fail_class": "FIXED_EVAL_PENDING",
            "real_claim_allowed": False,
            "stage_trace": [
                {"stage": "helper4_grounding", "passed": True, "fail_class": None},
                {"stage": "final_gate", "status": "REAL_CANDIDATE", "fail_class": "FIXED_EVAL_PENDING"},
            ],
        },
        envelope=_envelope(),
        approval_config_digest=None,
        runner_injected=False,
    )

    assert response["terminal_stage"] == "final_gate"


def test_contract_only_response_populates_approval_pre_gate_terminal_stage():
    response = _contract_only_actual_response(
        _envelope(),
        fail_class="BLOCK_HUMAN_APPROVAL_MISSING",
        approval_digest=None,
        approval_allowed=False,
        approval_fail_class="BLOCK_HUMAN_APPROVAL_MISSING",
    )

    assert response["terminal_stage"] == "approval_pre_gate"


# === _derive_terminal_stage fallback 조건 정정 (재검토팀 HOLD) ===
# fallback 은 'passed is False' 인 단계만 대상 — entry_fail 단독 조건(too broad) 제거 회귀 방지.

def test_terminal_stage_fallback_returns_passed_false_stage_when_no_fail_class_match():
    # 지시1: top fail_class 와 정확히 일치하는 stage 가 trace 에 하나도 없음
    # 지시2: passed=False 단계가 하나 존재 → 그 단계가 반환된다
    trace = [
        {"stage": "helper7_parse", "passed": True, "fail_class": None},
        {"stage": "helper4_grounding", "passed": False, "fail_class": "SOME_STAGE_FAIL"},
    ]
    assert _derive_terminal_stage(trace, "TOP_LEVEL_FAIL_NO_STAGE_MATCH") == "helper4_grounding"


def test_terminal_stage_fallback_excludes_final_gate_without_passed_false():
    # 지시3: final_gate 가 fail_class 는 갖되 passed 필드가 없는 경우 → final_gate 가 아니라
    # 실제 passed=False 단계가 선택되어야 한다(entry_fail 단독 fallback 이면 final_gate 오선택).
    trace = [
        {"stage": "helper4_grounding", "passed": False, "fail_class": "GROUNDING_FAIL"},
        {"stage": "final_gate", "fail_class": "FINAL_GATE_FAIL"},  # passed 필드 없음
    ]
    result = _derive_terminal_stage(trace, "TOP_LEVEL_FAIL_NO_STAGE_MATCH")
    assert result == "helper4_grounding"
    assert result != "final_gate"


def test_terminal_stage_fallback_excludes_final_gate_with_passed_not_false():
    # 지시3 변형: final_gate 가 fail_class 를 갖고 passed 가 다른 값(True)이어도 fallback 제외.
    trace = [
        {"stage": "helper4_grounding", "passed": False, "fail_class": "GROUNDING_FAIL"},
        {"stage": "final_gate", "passed": True, "fail_class": "FINAL_GATE_FAIL"},
    ]
    assert _derive_terminal_stage(trace, "TOP_LEVEL_FAIL_NO_STAGE_MATCH") == "helper4_grounding"
