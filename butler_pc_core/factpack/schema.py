"""
Butler Fact Pack — Pydantic schemas

원칙:
  - 모든 fact는 (answer, source, verified_at) 3종 메타 필수
  - confidence는 1.0(공식 출처 직접 확인) 만 허용. 추정/유추 금지.
  - keywords_required: 쿼리에 모두 포함되어야 매칭 후보로 진입 (false-positive 차단)
  - keywords_any: 보조 필터. 하나 이상 포함되면 점수 가산.
  - question_patterns: 유사도 비교 대상 예시 쿼리들.

스키마 위반 시 FactPack 로딩 자체가 실패해야 한다 (운영 중 환각 방지).
"""

from __future__ import annotations

from datetime import date
from typing import List, Optional

from pydantic import BaseModel, Field, field_validator


class Fact(BaseModel):
    """단일 검증된 사실 항목."""

    id: str = Field(..., min_length=8, description="고유 ID (예: 'kr_ins_4major_v1')")
    category: str = Field(..., description="카테고리 (예: 'korea_insurance')")
    question_patterns: List[str] = Field(
        ...,
        min_length=2,
        description="유사 쿼리 예시 (최소 2개 — 다양한 표현 커버용)",
    )
    keywords_required: List[str] = Field(
        default_factory=list,
        description="쿼리에 반드시 모두 포함되어야 하는 키워드 (false-positive 차단용)",
    )
    keywords_any: List[str] = Field(
        default_factory=list,
        description="보조 키워드 (하나 이상 포함 시 점수 가산)",
    )
    answer: str = Field(..., min_length=10, description="검증된 답변 본문")
    source: str = Field(..., min_length=3, description="출처 기관 (예: '고용노동부')")
    source_url: Optional[str] = Field(None, description="공식 URL")
    source_doc: Optional[str] = Field(None, description="고시·공고·법령 번호 등")
    verified_at: date = Field(..., description="대표가 출처 직접 확인한 날짜")
    expires_at: Optional[date] = Field(
        None,
        description="유효기간 종료일 (요율·금액 등 변동 가능 사실에 권장)",
    )
    confidence: float = Field(1.0, ge=1.0, le=1.0, description="공식 출처 직접 확인만 허용")

    @field_validator("question_patterns")
    @classmethod
    def _patterns_unique(cls, v: List[str]) -> List[str]:
        if len(set(v)) != len(v):
            raise ValueError("question_patterns에 중복이 있습니다.")
        return v

    @field_validator("answer")
    @classmethod
    def _answer_not_placeholder(cls, v: str) -> str:
        # 검증 미완료를 나타내는 placeholder 마커만 차단.
        # '추정', '대략' 같은 단어는 회계학·법학에서 정상적으로 사용되므로 제외.
        forbidden = ["TODO", "FIXME", "XXX", "확인필요", "값모름", "[미정]", "{{"]
        for token in forbidden:
            if token in v:
                raise ValueError(f"answer에 검증 미완료 마커가 있습니다: {token}")
        return v


class FactPackFile(BaseModel):
    """단일 카테고리 fact JSON 파일의 루트 스키마."""

    version: str = Field(..., pattern=r"^\d+\.\d+(\.\d+)?$")
    category: str
    last_verified: date
    notes: Optional[str] = None
    facts: List[Fact] = Field(..., min_length=1)

    @field_validator("facts")
    @classmethod
    def _fact_ids_unique(cls, v: List[Fact]) -> List[Fact]:
        ids = [f.id for f in v]
        if len(set(ids)) != len(ids):
            raise ValueError("같은 파일 내 fact id 중복")
        return v


class FactMatch(BaseModel):
    """매칭 결과."""

    fact: Fact
    score: float = Field(..., ge=0.0, le=1.0)
    matched_pattern: str
    matched_keywords: List[str] = Field(default_factory=list)


class FactPackAuditEntry(BaseModel):
    """감사 로그 항목 (Butler 통합 정책 준수)."""

    query: str
    source: str  # "factpack" | "llm"
    fact_id: Optional[str] = None
    score: Optional[float] = None
    threshold_used: Optional[float] = None
    timestamp_iso: str
    pack_version: str
