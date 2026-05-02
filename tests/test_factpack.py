"""
Butler Fact Pack — 통합 테스트

품질 기준 검증:
  1. 모든 fact 파일이 스키마 검증을 통과한다
  2. 베타 영업 결정타였던 '4대 보험' 쿼리에 정확히 응답한다
  3. 다양한 자연어 표현으로도 매칭된다 (재현성)
  4. 임계값 미달 쿼리는 None 반환 (false-positive 방지)
  5. 매칭 응답 시간 < 50ms
  6. 모든 fact가 output answer에 출처 정보를 포함하기 위한 메타 보유
"""

from __future__ import annotations

import time
from pathlib import Path

import pytest

from butler_pc_core.factpack import FactPack, FactMatch
from butler_pc_core.factpack.matcher import similarity, Matcher
from butler_pc_core.factpack.normalizer import normalize


# --------------- 픽스처 ---------------


@pytest.fixture(scope="module")
def pack() -> FactPack:
    return FactPack.from_default_facts_dir()


# --------------- 1. 스키마/로딩 ---------------


class TestLoading:
    def test_pack_loads_successfully(self, pack: FactPack) -> None:
        assert pack is not None
        assert len(pack.facts) >= 50, f"50개 이상 fact가 있어야 합니다 (현재 {len(pack.facts)})"

    def test_all_facts_have_required_meta(self, pack: FactPack) -> None:
        """모든 fact에 출처/검증일자 메타가 있어야 한다."""
        for f in pack.facts:
            assert f.source, f"{f.id}: source 누락"
            assert f.verified_at, f"{f.id}: verified_at 누락"
            assert f.answer, f"{f.id}: answer 누락"
            assert len(f.question_patterns) >= 2, f"{f.id}: question_patterns 2개 미만"

    def test_no_duplicate_fact_ids(self, pack: FactPack) -> None:
        ids = [f.id for f in pack.facts]
        assert len(ids) == len(set(ids)), "중복 fact id가 있습니다."

    def test_categories_balanced(self, pack: FactPack) -> None:
        stats = pack.stats()
        cats = stats["categories"]
        assert "korea_insurance" in cats
        assert "korea_tax" in cats
        assert "korea_labor" in cats
        # 각 카테고리 최소 4개 이상
        for cat, count in cats.items():
            assert count >= 4, f"{cat}: 최소 4개 필요, 현재 {count}"


# --------------- 2. 핵심 베타 영업 케이스 ---------------


class TestBetaSalesCriticalCases:
    """대표가 발견한 결함 A 재발 방지 — 한국 4대 보험 정확도 100%."""

    def test_4major_insurance_basic(self, pack: FactPack) -> None:
        m = pack.lookup("한국의 4대 보험은 무엇인가요?")
        assert m is not None, "4대 보험 쿼리에 매칭이 되지 않습니다."
        # 정답 4가지가 모두 포함되어야 함
        assert "국민연금" in m.fact.answer
        assert "건강보험" in m.fact.answer
        assert "고용보험" in m.fact.answer
        assert "산재보험" in m.fact.answer or "산업재해보상보험" in m.fact.answer
        # 잘못된 답변 (이전 베타 결함) 미포함
        assert "국민재해보험" not in m.fact.answer
        assert "국민연금보험료" not in m.fact.answer

    @pytest.mark.parametrize(
        "query",
        [
            "한국의 4대 보험은?",
            "4대보험이 뭔가요?",
            "사대보험 종류 알려줘",
            "한국 4대 보험 무엇",
            "4대 보험 4가지 알려주세요",
        ],
    )
    def test_4major_insurance_paraphrases(self, pack: FactPack, query: str) -> None:
        """다양한 표현 변형에 모두 매칭."""
        m = pack.lookup(query)
        assert m is not None, f"매칭 실패: '{query}'"
        assert m.fact.id == "kr_ins_4major_types_v1"

    def test_min_wage_2026(self, pack: FactPack) -> None:
        m = pack.lookup("2026년 최저시급은 얼마인가요?")
        assert m is not None
        assert "10,320" in m.fact.answer or "10320" in m.fact.answer

    def test_pension_rate(self, pack: FactPack) -> None:
        m = pack.lookup("국민연금 보험료율 알려줘")
        assert m is not None
        assert "9.5" in m.fact.answer

    def test_health_rate(self, pack: FactPack) -> None:
        m = pack.lookup("직장 건강보험 요율이 얼마인가요?")
        assert m is not None
        assert "7.19" in m.fact.answer


# --------------- 3. False-positive 방지 ---------------


class TestFalsePositivePrevention:
    """매칭이 안 되는 게 정답인 경우 — 잘못된 답변보다 LLM 폴백이 안전."""

    @pytest.mark.parametrize(
        "query",
        [
            "오늘 점심 뭐 먹지",
            "파이썬 리스트 정렬 방법",
            "비트코인 가격 알려줘",
            "내일 날씨 어때",
            "회의록 작성해줘",
        ],
    )
    def test_unrelated_queries_return_none(self, pack: FactPack, query: str) -> None:
        m = pack.lookup(query)
        assert m is None, f"무관한 쿼리에 매칭이 되었습니다: '{query}' → {m.fact.id if m else None}"

    def test_partial_keyword_match_does_not_falsely_match(self, pack: FactPack) -> None:
        """'보험'만 들어간 쿼리가 4대 보험에 매칭되면 안 된다."""
        m = pack.lookup("자동차 보험 추천해줘")
        # 자동차 보험 관련 fact는 없으므로 None이 정답
        assert m is None or m.fact.id != "kr_ins_4major_types_v1"

    def test_empty_query_returns_none(self, pack: FactPack) -> None:
        assert pack.lookup("") is None
        assert pack.lookup("   ") is None


# --------------- 4. 정규화 모듈 ---------------


class TestNormalizer:
    def test_korean_numeral_unification(self) -> None:
        assert "4대보험" in normalize("사대보험")
        assert "4대보험" in normalize("4대 보험")
        assert "4대보험" in normalize("사 대 보험")

    def test_synonym_unification(self) -> None:
        assert "부가가치세" in normalize("부가세")
        assert "부가가치세" in normalize("VAT")
        assert "종합소득세" in normalize("종소세")

    def test_whitespace_compression(self) -> None:
        assert normalize("4대   보험은   뭐야") == normalize("4대보험은 뭐야")

    def test_question_mark_strip(self) -> None:
        assert normalize("4대 보험?") == normalize("4대 보험")
        assert normalize("4대 보험??!?") == normalize("4대 보험")


# --------------- 5. 유사도 함수 ---------------


class TestSimilarity:
    def test_identical_strings_return_1(self) -> None:
        assert similarity("4대보험", "4대보험") == 1.0

    def test_empty_returns_zero(self) -> None:
        assert similarity("", "") == 0.0
        assert similarity("4대보험", "") == 0.0

    def test_completely_different_low_score(self) -> None:
        score = similarity("파이썬 코드", "법인세율 인상")
        assert score < 0.3

    def test_paraphrase_high_score(self) -> None:
        # 동일 핵심 키워드 보유, 다른 어미: char-trigram 일치율과 토큰 자카드 모두에 의존
        score = similarity(normalize("4대 보험 종류"), normalize("4대보험 무엇"))
        assert score > 0.3, f"패러프레이즈 점수가 너무 낮음: {score}"


# --------------- 6. 성능 ---------------


class TestPerformance:
    def test_lookup_under_50ms(self, pack: FactPack) -> None:
        """매칭 1회 호출은 50ms 이내여야 한다 (LLM 31초 대비)."""
        queries = [
            "한국의 4대 보험은?",
            "2026년 최저시급",
            "법인세율 알려줘",
            "주휴수당 조건",
            "감가상각이란",
        ]
        for q in queries:
            start = time.perf_counter()
            pack.lookup(q)
            elapsed_ms = (time.perf_counter() - start) * 1000
            assert elapsed_ms < 50, f"'{q}': {elapsed_ms:.1f}ms (50ms 초과)"

    def test_lookup_avg_under_20ms(self, pack: FactPack) -> None:
        """평균은 20ms 이내가 목표."""
        queries = ["한국의 4대 보험", "최저임금", "법인세율", "주휴수당", "퇴직금"] * 10
        start = time.perf_counter()
        for q in queries:
            pack.lookup(q)
        avg_ms = (time.perf_counter() - start) * 1000 / len(queries)
        assert avg_ms < 20, f"평균 {avg_ms:.1f}ms (20ms 초과)"


# --------------- 7. 출처/감사로그 메타 ---------------


class TestAuditMeta:
    def test_match_carries_source_meta(self, pack: FactPack) -> None:
        m = pack.lookup("한국의 4대 보험은 무엇인가요?")
        assert m is not None
        assert m.fact.source
        assert m.fact.verified_at
        assert m.score >= Matcher.DEFAULT_THRESHOLD

    def test_expiring_facts_have_dates(self, pack: FactPack) -> None:
        """expires_at이 있는 fact는 모두 verified_at 이후 날짜여야 한다."""
        for f in pack.facts:
            if f.expires_at:
                assert f.expires_at >= f.verified_at, f"{f.id}: expires_at < verified_at"


# --------------- 8. 카테고리별 회귀 ---------------


class TestPerCategoryRegression:
    """각 카테고리에서 대표 쿼리가 매칭되는지 회귀 테스트."""

    @pytest.mark.parametrize(
        "query,expected_category",
        [
            ("한국 4대 보험 종류", "korea_insurance"),
            ("부가가치세율 얼마", "korea_tax"),
            ("법인세율 2026", "korea_tax"),
            ("2026년 최저시급", "korea_labor"),
            ("주휴수당 조건", "korea_labor"),
            ("법인 설립 자본금", "korea_business"),
            ("재무제표 종류", "korea_accounting"),
            ("인감증명서 발급", "korea_general"),
        ],
    )
    def test_category_routing(self, pack: FactPack, query: str, expected_category: str) -> None:
        m = pack.lookup(query)
        assert m is not None, f"매칭 실패: '{query}'"
        assert m.fact.category == expected_category, (
            f"'{query}' → 기대 {expected_category}, 실제 {m.fact.category}"
        )
