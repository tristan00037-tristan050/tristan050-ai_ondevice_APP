"""contracts.py — card1_extraction 데이터 계약 (알고리즘 팀 §6)."""
from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import List, Optional


class IntentType(Enum):
    REQUEST   = "request"    # 요청형 — 상대에게 행동 요구
    REPORT    = "report"     # 보고형 — 정보 전달/공유
    QUESTION  = "question"   # 질문형 — 정보 요청
    COMMAND   = "command"    # 지시형 — 상하관계 명령
    SCHEDULE  = "schedule"   # 일정형 — 날짜/일정 중심
    NO_ACTION = "no_action"  # 액션 없음 — 인사/감사 등
    UNKNOWN   = "unknown"    # 미분류


class SentenceType(Enum):
    INTERROGATIVE = "interrogative"  # 의문문 — 나요/까요/합니까
    DECLARATIVE   = "declarative"   # 평서문 — 사실 서술
    IMPERATIVE    = "imperative"    # 명령형 — 주세요/하십시오
    PROPOSITIVE   = "propositive"   # 청유형 — 합시다/하자
    REPORTIVE     = "reportive"     # 보고형 — 보고드립니다/알려드립니다
    CONDITIONAL   = "conditional"   # 조건형 — 다면/한다면/경우
    NEGATIVE      = "negative"      # 부정형 — 않/못/없습니다
    COMPLEX       = "complex"       # 복합형 — 2가지 이상 혼재


@dataclass
class ExtractedAction:
    action_text:     str
    owner:           str           = ""
    due_date:        Optional[str] = None   # ISO 8601 or None
    source_evidence: str           = ""     # 원문 근거 문장 (== evidence)
    confidence:      float         = 0.5

    # 단계 6.5.1 — card1_action_extraction.v1 schema 필드 (알고리즘 팀 §6)
    action_type:     str           = ""     # 보내/검토/정리/공유/제출/...
    deadline_text:   str           = ""     # 원문 마감 표현 (action 단위)
    material_refs:   List[str]     = field(default_factory=list)
    is_negated:      bool          = False  # 부정형(제출하지 마세요) 표시


@dataclass
class Card1Extraction:
    intent:        str
    intent_type:   IntentType

    deadline:      Optional[str]          = None   # ISO 8601 or None
    deadline_raw:  str                    = ""     # 원문 마감 표현
    materials:     List[str]              = field(default_factory=list)
    actions:       List[ExtractedAction]  = field(default_factory=list)
    sentence_type: SentenceType           = SentenceType.DECLARATIVE

    confidence:    float  = 0.5
    needs_review:  bool   = True
    reason_code:   str    = ""   # 신뢰도 판정 사유
