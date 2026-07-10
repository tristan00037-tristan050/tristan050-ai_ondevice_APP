from __future__ import annotations

from butler_pc_core.cards.box3.actual_fail_class import (
    BLOCK_NO_FACTUAL_CLAIMS,
    FAIL_CLASS_SEVERITY,
    is_blocking_actual_fail_class,
)
from butler_pc_core.cards.box3.actual_contracts import Box3ActualRuntimeEnvelope
from butler_pc_core.cards.box3.endpoint_wiring import (
    _contract_only_actual_response,
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
