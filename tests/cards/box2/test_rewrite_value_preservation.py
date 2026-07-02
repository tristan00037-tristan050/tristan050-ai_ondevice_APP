from __future__ import annotations

from butler_pc_core.cards.box2.rewrite_service import rewrite_to_company_format


def _assert_expected_values_are_source_backed(foreign_doc: str, *values: str) -> None:
    normalized_doc = " ".join(foreign_doc.split())
    for value in values:
        if value == "[확인 필요]":
            continue
        assert " ".join(value.split()) in normalized_doc, f"expected value is not in source: {value}"


def test_rewrite_preserves_vendor_item_quantity_price_amount_and_schedule() -> None:
    foreign_doc = """
제목: 납품 견적서
발행일: 2026-06-20
담당자: 김담당
거래처: 주식회사 대한상사
품목: AI HUD 라이선스
수량: 3개
단가: 120,000원
금액: 360,000원
납품 일정: 2026-06-10
합의사항: 납품 후 3영업일 이내 검수
""".strip()
    our_format = "제목/발행일/담당자/핵심 내용/합의사항/금액/일정/확인 필요/최종 문안"

    result = rewrite_to_company_format(foreign_doc, our_format)
    doc = result.rewritten_doc

    assert "주식회사 대한상사" in doc
    assert "AI HUD 라이선스" in doc
    assert "3개" in doc
    assert "120,000원" in doc
    assert "360,000원" in doc
    assert "2026-06-10" in doc
    assert "금액/일정: 금액 360,000원 / 일정 2026-06-10" in doc


def test_rewrite_amount_prefers_currency_not_quantity_or_date() -> None:
    foreign_doc = """
품목: 유지보수 서비스
수량: 12개월
단가: 50,000원
합계: 600,000원
납품 일정: 2026-07-01
""".strip()

    result = rewrite_to_company_format(foreign_doc, "금액/일정 포함")
    doc = result.rewritten_doc

    assert "금액 600,000원" in doc
    assert "금액 12" not in doc
    assert "금액 2026" not in doc


def test_rewrite_missing_amount_does_not_invent_value() -> None:
    foreign_doc = """
거래처: 테스트상사
품목: 분석 보고서
수량: 1건
납품 일정: 2026-06-30
""".strip()

    result = rewrite_to_company_format(foreign_doc, "금액/일정 포함")
    doc = result.rewritten_doc

    assert "거래처=테스트상사" in doc
    assert "품목=분석 보고서" in doc
    assert "금액=[확인 필요]" in doc
    assert "존재하지 않는 금액" in doc


def test_rewrite_preserves_inline_slash_separated_key_values() -> None:
    foreign_doc = """
제목: 구매 요청
공급자 주식회사 라온테크 / 상품명 온디바이스 라이선스 / 수량 2식 / 단가 150,000원 / 총액 300,000원 / 납기 2026/07/15
""".strip()

    result = rewrite_to_company_format(foreign_doc, "거래처/품목/수량/단가/금액/일정")
    doc = result.rewritten_doc

    assert "거래처=주식회사 라온테크" in doc
    assert "품목=온디바이스 라이선스" in doc
    assert "수량=2식" in doc
    assert "단가=150,000원" in doc
    assert "금액=300,000원" in doc
    assert "일정=2026/07/15" in doc
    assert "라온테크 / 상품명" not in doc


def test_rewrite_preserves_markdown_table_values() -> None:
    foreign_doc = """
| vendor | product | qty | unit price | total | due |
|---|---|---:|---:|---:|---|
| 주식회사 비전상사 | 데이터 정제 용역 | 5건 | ₩80,000 | ₩400,000 | 2026.07.20 |
""".strip()

    result = rewrite_to_company_format(foreign_doc, "표 원문을 회사 양식으로 전사")
    doc = result.rewritten_doc

    assert "거래처=주식회사 비전상사" in doc
    assert "품목=데이터 정제 용역" in doc
    assert "수량=5건" in doc
    assert "단가=₩80,000" in doc
    assert "금액=₩400,000" in doc
    assert "일정=2026.07.20" in doc


def test_box2_nonstandard_quote_anchor_extracts_item_tail_quantity_and_amount_only() -> None:
    foreign_doc = "견적서 - (주)미래상사 / 클라우드 라이선스 10석 / 연 12,000,000원"
    _assert_expected_values_are_source_backed(foreign_doc, "(주)미래상사", "클라우드 라이선스", "10석", "12,000,000원")

    result = rewrite_to_company_format(foreign_doc, "거래처/품목/수량/단가/금액/일정")
    doc = result.rewritten_doc

    assert "거래처=(주)미래상사" in doc
    assert "품목=클라우드 라이선스" in doc
    assert "수량=10석" in doc
    assert "단가=[확인 필요]" in doc
    assert "금액=12,000,000원" in doc
    assert "단가=12,000,000원" not in doc


def test_box2_slash_separated_trade_detail_extracts_item_quantity_unit_price_and_total() -> None:
    foreign_doc = "거래명세: 라온유통 / 사무용 의자 25EA / 단가 89,000 / 합계 2,225,000원"
    _assert_expected_values_are_source_backed(foreign_doc, "라온유통", "사무용 의자", "25EA", "89,000", "2,225,000원")

    result = rewrite_to_company_format(foreign_doc, "거래처/품목/수량/단가/금액/일정")
    doc = result.rewritten_doc

    assert "거래처=라온유통" in doc
    assert "품목=사무용 의자" in doc
    assert "수량=25EA" in doc
    assert "단가=89,000" in doc
    assert "금액=2,225,000원" in doc
    assert "품목=라온유통" not in doc


def test_box2_space_separated_labels_extract_item_quantity_unit_price_without_amount_hallucination() -> None:
    foreign_doc = "거래상대방: 대한물산  품목 A4용지  수량 50  단가 18000"
    _assert_expected_values_are_source_backed(foreign_doc, "대한물산", "A4용지", "50", "18000")

    result = rewrite_to_company_format(foreign_doc, "거래처/품목/수량/단가/금액/일정")
    doc = result.rewritten_doc

    assert "거래처=대한물산" in doc
    assert "품목=A4용지" in doc
    assert "수량=50" in doc
    assert "단가=18000" in doc
    assert "금액=[확인 필요]" in doc
    assert "금액=18000" not in doc


def test_box2_missing_price_and_amount_stays_check_required() -> None:
    foreign_doc = "거래처: 해오름상사\n품목: 문서 정리 용역\n수량: 1건"
    _assert_expected_values_are_source_backed(foreign_doc, "해오름상사", "문서 정리 용역", "1건")

    result = rewrite_to_company_format(foreign_doc, "거래처/품목/수량/단가/금액")
    doc = result.rewritten_doc

    assert "거래처=해오름상사" in doc
    assert "품목=문서 정리 용역" in doc
    assert "수량=1건" in doc
    assert "단가=[확인 필요]" in doc
    assert "금액=[확인 필요]" in doc


def test_rewrite_preserves_nonstandard_quote_anchor_vendor() -> None:
    foreign_doc = """
견적서 - 주식회사 한빛테크
거래명세: 클라우드 전환 용역 / 수량 4건 / 단가 250,000원 / 총액 1,000,000원 / 납기 2026-08-01
""".strip()

    result = rewrite_to_company_format(foreign_doc, "거래처/품목/수량/단가/금액/일정")
    doc = result.rewritten_doc

    assert "거래처=주식회사 한빛테크" in doc
    assert "품목=클라우드 전환 용역" in doc
    assert "수량=4건" in doc
    assert "단가=250,000원" in doc
    assert "금액=1,000,000원" in doc
    assert "일정=2026-08-01" in doc


def test_rewrite_preserves_trade_counterparty_and_company_sentence() -> None:
    foreign_doc = """
거래상대방: 주식회사 미래상사
주식회사 미래상사에서 보안 라이선스 2식을 단가 150,000원, 총액 300,000원으로 2026년 7월 31일까지 납품
""".strip()

    result = rewrite_to_company_format(foreign_doc, "거래처/품목/수량/단가/금액/일정")
    doc = result.rewritten_doc

    assert "거래처=주식회사 미래상사" in doc
    assert "품목=보안 라이선스" in doc
    assert "수량=2식" in doc
    assert "단가=150,000원" in doc
    assert "금액=300,000원" in doc
    assert "일정=2026년 7월 31일" in doc


def test_rewrite_does_not_treat_trade_detail_item_as_vendor_without_company_hint() -> None:
    foreign_doc = """
거래명세: 유지보수 서비스
수량: 1건
금액: 120,000원
""".strip()

    result = rewrite_to_company_format(foreign_doc, "거래처/품목/수량/금액")
    doc = result.rewritten_doc

    assert "거래처=[확인 필요]" in doc
    assert "품목=유지보수 서비스" in doc
    assert "금액=120,000원" in doc


def test_box2_quantity_unit_price_amount_and_schedule_boundaries_do_not_cross() -> None:
    foreign_doc = "품목 복합 서비스  수량 12개월  단가 50,000원  합계 600,000원  일정 2026-07-01"
    _assert_expected_values_are_source_backed(foreign_doc, "복합 서비스", "12개월", "50,000원", "600,000원", "2026-07-01")

    result = rewrite_to_company_format(foreign_doc, "품목/수량/단가/금액/일정")
    doc = result.rewritten_doc

    assert "품목=복합 서비스" in doc
    assert "수량=12개월" in doc
    assert "단가=50,000원" in doc
    assert "금액=600,000원" in doc
    assert "일정=2026-07-01" in doc
    assert "금액=12개월" not in doc
    assert "일정=50,000원" not in doc


def test_box2_item_label_stops_at_newline_before_note() -> None:
    foreign_doc = "품목: A4용지\n비고: 빠른 납품 요청"

    result = rewrite_to_company_format(foreign_doc, "품목/수량/단가/금액/일정")
    doc = result.rewritten_doc

    assert "품목=A4용지" in doc
    assert "품목=A4용지 비고" not in doc
    assert "빠른 납품 요청" not in doc


def test_box2_quantity_rejects_date_like_value() -> None:
    foreign_doc = "품목: A4용지\n수량 2026-07-01"

    result = rewrite_to_company_format(foreign_doc, "품목/수량/단가/금액/일정")
    doc = result.rewritten_doc

    assert "품목=A4용지" in doc
    assert "수량=[확인 필요]" in doc
    assert "일정=[확인 필요]" in doc
    assert "수량=2026-07-01" not in doc


def test_box2_schedule_accepts_date_like_value() -> None:
    foreign_doc = "품목: A4용지\n납기 2026-07-01"

    result = rewrite_to_company_format(foreign_doc, "품목/수량/단가/금액/일정")
    doc = result.rewritten_doc

    assert "품목=A4용지" in doc
    assert "일정=2026-07-01" in doc


def test_box2_annual_amount_does_not_become_unit_price() -> None:
    foreign_doc = "견적서 - (주)미래상사 / 클라우드 라이선스 10석 / 연 12,000,000원"

    result = rewrite_to_company_format(foreign_doc, "거래처/품목/수량/단가/금액/일정")
    doc = result.rewritten_doc

    assert "수량=10석" in doc
    assert "금액=12,000,000원" in doc
    assert "단가=[확인 필요]" in doc
    assert "단가=12,000,000원" not in doc
