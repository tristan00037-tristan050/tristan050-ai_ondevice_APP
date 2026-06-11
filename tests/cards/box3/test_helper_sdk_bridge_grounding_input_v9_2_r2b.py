from butler_pc_core.cards.box3.helper_sdk_bridge import _draft_text_for_helper4_grounding


def test_helper4_grounding_input_uses_one_factual_claim_per_line():
    draft = """제목: 납품 정보 요약
배경: 납품 일정은 2026년 6월 10일 (목요일)입니다 (근거1).
핵심내용: 납품 책임자는 운영팀 (담당 부서명만 문서에 기재)입니다 (근거2). 납품 장소는 본사 1층 자재 창고입니다 (근거3).
근거: 추가 비용은 [문서에 근거 없음]입니다 (근거4).
확인필요: 담당자와 금액은 [문서에 근거 없음]입니다.
최종문안: 납품 일정은 2026년 6월 10일 (목요일)입니다 (근거1).
"""
    text = _draft_text_for_helper4_grounding(draft)
    lines = [line.strip() for line in text.splitlines() if line.strip()]
    assert "납품 장소: 본사 1층 자재 창고" in lines
    assert not any("확인필요" in line for line in lines)
    assert not any("[문서에 근거 없음]" in line for line in lines)
    assert not any("창고입니다" in line for line in lines)
    assert not any("납품 책임자" in line and "납품 장소" in line for line in lines)


def test_helper4_grounding_input_preserves_wrong_values_for_detection():
    draft = "핵심내용: 납품 장소는 다른 창고입니다 (근거3)."
    text = _draft_text_for_helper4_grounding(draft)
    assert text.strip() == "납품 장소: 다른 창고"
