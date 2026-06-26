from __future__ import annotations

from butler_pc_core.cards.box2.rewrite_service import rewrite_to_company_format


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
