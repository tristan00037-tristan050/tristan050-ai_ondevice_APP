"""parser.py — 결정론적 패턴 추출 (알고리즘 팀 §6-5).

LLM 없이 작동하는 규칙 기반 추출기.
"""
from __future__ import annotations

import re
from typing import List

from .contracts import SentenceType


# ── 마감일 패턴 ───────────────────────────────────────────────────────────────

DEADLINE_PATTERNS: List[re.Pattern[str]] = [
    re.compile(r"오늘\s*(?:중|안)\s*(?:에|으로|까지)?"),            # 오늘 중
    re.compile(r"내일\s*까지"),                                     # 내일까지
    re.compile(r"모레\s*까지"),                                     # 모레까지
    re.compile(r"이번\s*주\s*(?:안|중|까지)"),                       # 이번 주까지
    re.compile(r"(?:이번\s*주\s*)?(?:월|화|수|목|금|토|일)요일\s*까지"),  # 금요일까지
    re.compile(r"\d{1,2}월\s*\d{1,2}일\s*까지"),                    # N월 N일까지
    re.compile(r"(?:오전|오후)\s*\d{1,2}시\s*까지"),                 # 오전/오후 N시까지
    re.compile(r"회의\s*(?:전|이전)\s*까지?"),                       # 회의 전까지
    re.compile(r"퇴근\s*(?:전|이전)\s*까지?"),                       # 퇴근 전까지
    re.compile(r"다음\s*주\s*(?:월|화|수|목|금|토|일)?요일?\s*까지?"),  # 다음 주 금요일까지
    re.compile(r"\d+\s*일\s*(?:이내|이내로|안에|까지)"),              # N일 이내/까지
    re.compile(r"(?:이번\s*달|다음\s*달)\s*말\s*까지?"),              # 이번/다음 달 말까지
    re.compile(r"\d{4}\s*년\s*\d{1,2}\s*월\s*\d{1,2}\s*일\s*까지?"), # YYYY년 MM월 DD일까지
]

# ── 액션 동사 ─────────────────────────────────────────────────────────────────

ACTION_VERBS: List[str] = [
    "보내",  "전달",  "공유",  "정리",  "작성",  "검토",  "확인",  "제출",
    "업로드", "수정",  "보완",  "회신",  "준비",  "취합",  "송부",  "첨부",
    "완료",  "처리",  "보고",  "발송",  "제공",  "서명",  "날인",  "갱신",
]

# ── 자료 키워드 ───────────────────────────────────────────────────────────────

MATERIAL_WORDS: List[str] = [
    "자료",  "파일",  "문서",  "보고서", "초안",   "견적서", "계약서",
    "회의록", "엑셀",  "표",   "이미지", "영수증",  "서류",  "명세서",
    "청구서", "기안서", "제안서", "계획서", "확인서",  "신청서",
]


# ── 문형 분류 패턴 ────────────────────────────────────────────────────────────

_SENTENCE_TYPE_RES: dict[SentenceType, re.Pattern[str]] = {
    SentenceType.INTERROGATIVE: re.compile(
        r"(?:[가나]요\s*[?？]?|까요\s*[?？]?|합니까\s*[?？]?|인가요\s*[?？]?"
        r"|는지\s*[?？]?|을까요\s*[?？]?|나요\s*[?？]?)"
    ),
    SentenceType.IMPERATIVE: re.compile(
        r"(?:주세요|해주세요|하십시오|주시기\s*바랍니다|부탁드립니다|주시면\s*감사)"
    ),
    SentenceType.PROPOSITIVE: re.compile(
        r"(?:합시다|봅시다|해봅시다|하자(?:\s*고)?|해봐요|면\s*좋겠어요|으면\s*좋겠)"
    ),
    SentenceType.REPORTIVE: re.compile(
        r"(?:보고드립니다|알려드립니다|안내드립니다|공유드립니다|전달드립니다)"
    ),
    SentenceType.CONDITIONAL: re.compile(
        r"(?:다면|한다면|하게\s*되면|경우에는|경우\s*에|시에\s)"
    ),
    SentenceType.NEGATIVE: re.compile(
        r"(?:하지\s*않|지\s*않았|않습니다|안\s*했|못\s*했|없습니다|아닙니다"
        r"|되지\s*않|안\s*됩니다)"
    ),
}

_ACTION_VERB_RE = re.compile("|".join(re.escape(v) for v in ACTION_VERBS))


def extract_deadlines(text: str) -> List[str]:
    """DEADLINE_PATTERNS에 매칭되는 마감 표현 목록 반환 (원문 기준)."""
    found: List[str] = []
    seen: set[str] = set()
    for pattern in DEADLINE_PATTERNS:
        for m in pattern.finditer(text):
            raw = m.group(0).strip()
            if raw and raw not in seen:
                seen.add(raw)
                found.append(raw)
    return found


def extract_actions_candidates(text: str) -> List[str]:
    """ACTION_VERBS가 포함된 문장/절 추출 (최대 200자)."""
    sentences = re.split(r"[.!?。\n]+", text)
    return [
        s.strip()[:200]
        for s in sentences
        if s.strip() and _ACTION_VERB_RE.search(s)
    ]


def extract_materials(text: str) -> List[str]:
    """텍스트에 존재하는 MATERIAL_WORDS 목록 반환 (중복 제거)."""
    seen: set[str] = set()
    result: List[str] = []
    for word in MATERIAL_WORDS:
        if word in text and word not in seen:
            seen.add(word)
            result.append(word)
    return result


def classify_sentence_type(text: str) -> SentenceType:
    """
    텍스트 → SentenceType (8 유형).

    복합형 판정: 2가지 이상 패턴 동시 감지.
    우선순위 (단일): NEGATIVE > CONDITIONAL > INTERROGATIVE > IMPERATIVE
                    > PROPOSITIVE > REPORTIVE > DECLARATIVE (기본값)
    """
    matched = [st for st, pat in _SENTENCE_TYPE_RES.items() if pat.search(text)]
    if len(matched) >= 2:
        return SentenceType.COMPLEX
    return matched[0] if matched else SentenceType.DECLARATIVE
