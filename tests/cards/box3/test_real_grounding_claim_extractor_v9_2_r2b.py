from butler_pc_core.cards.box3.real_grounding import extract_claims


def test_compact_confirm_needed_label_is_metadata():
    draft = "확인필요: 담당자와 금액은 [문서에 근거 없음]입니다."
    claims = extract_claims(draft)
    assert claims
    assert all(not c.is_factual for c in claims)


def test_labeled_content_is_split_into_sentence_claims():
    draft = (
        "핵심내용: 납품 책임자는 운영팀입니다 (근거2). "
        "납품 장소는 본사 1층 자재 창고입니다 (근거3)."
    )
    factual = [c.claim_text_runtime_only for c in extract_claims(draft) if c.is_factual]
    assert any("납품 책임자" in t for t in factual)
    assert any("납품 장소" in t for t in factual)
    assert not any("납품 책임자" in t and "납품 장소" in t for t in factual)


def test_abstain_marker_sentence_is_non_claim():
    draft = "근거: 추가 비용은 [문서에 근거 없음]입니다 (근거4)."
    claims = extract_claims(draft)
    assert claims
    assert all(not c.is_factual for c in claims)


def test_final_confirmation_sentence_is_non_claim():
    draft = "최종문안: 위 내용은 근거 범위에서 확인합니다."
    claims = extract_claims(draft)
    assert claims
    assert all(not c.is_factual for c in claims)
