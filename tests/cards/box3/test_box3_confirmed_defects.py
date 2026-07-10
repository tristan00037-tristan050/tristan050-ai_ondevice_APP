from __future__ import annotations

from butler_pc_core.cards.box3.actual_fail_class import (
    BLOCK_NO_FACTUAL_CLAIMS,
    FAIL_CLASS_SEVERITY,
    is_blocking_actual_fail_class,
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
