"""value_type_detector.py — 필드 레이블 + 값으로 ValueType 감지 (단계 2)."""
from __future__ import annotations

import re

from .contracts import ValueType

# ── 정규식 패턴 ───────────────────────────────────────────────────────────────

EMAIL_RE = re.compile(
    r"[a-zA-Z0-9._%+\-]+@[a-zA-Z0-9.\-]+\.[a-zA-Z]{2,}"
)

PHONE_RE = re.compile(
    r"(\+?82[-.\s]?)?(0\d{1,2})[-.\s]\d{3,4}[-.\s]\d{4}"  # 한국 형식
    r"|(\+\d{1,3}[-.\s])?\d{3,4}[-.\s]\d{3,4}[-.\s]\d{4}"  # 국제 형식
)

MONEY_RE = re.compile(
    r"[\$￦₩€£]\s*[\d,]+"                              # 통화기호 + 숫자
    r"|\d[\d,천백만억]*\s*(원|만원|억원|천만원|백만원|달러|USD|KRW|EUR|JPY)"  # 한국/외화
    r"|[\d,]+\s*(달러|USD|KRW|EUR|JPY)"
)

DATE_RE = re.compile(
    r"\d{4}년\s*\d{1,2}월(\s*\d{1,2}일)?"             # 2026년 6월 1일
    r"|\d{4}[.\-/]\d{1,2}[.\-/]\d{1,2}"               # 2026-06-01
    r"|\d{1,2}월\s*\d{1,2}일"                          # 6월 1일
)

DATE_RANGE_RE = re.compile(
    r"\d{1,3}\s*(개월|개월간|주간|년간|연간|months?|weeks?|years?)"  # 6개월, 12개월 (1-3자리만)
    r"|(?<!\d)\d{1,2}\s*년\b"                             # 3년, 5년 — 앞에 숫자 없어야 함(2026년 제외)
    r"|\d{4}.{0,5}[~–\-]\s*\d{4}"                      # 2026 ~ 2027
)

# ── 레이블 힌트 집합 ──────────────────────────────────────────────────────────

_LABEL_DATE_RANGE = {"기간", "기한", "개월", "주간", "연간", "duration", "period"}
_LABEL_DATE       = {"시작일", "착수일", "종료일", "완료일", "마감일", "날짜", "date"}
_LABEL_MONEY      = {"금액", "예산", "비용", "fee", "budget", "cost", "가격", "견적", "요금"}
_LABEL_PHONE      = {"전화", "phone", "tel", "fax", "hp", "휴대폰", "핸드폰"}
_LABEL_CONTACT    = {"연락처", "이메일", "email", "contact"}
_LABEL_CATEGORY   = {"영역", "분야", "scope", "범위", "역할", "업무", "서비스", "분류", "유형", "종류"}
_LABEL_PERSON     = {"담당자", "수신인", "책임자", "대표자", "person", "담당", "작성자"}
_LABEL_ORG        = {"회사", "기관", "단체", "org", "organization", "업체", "협력사"}


def _label_match(label_lower: str, hint_set: set[str]) -> bool:
    return any(k in label_lower for k in hint_set)


def detect_value_type(label: str, value: str) -> ValueType:
    """
    (레이블, 값) 쌍으로 ValueType 을 감지.
    우선순위: EMAIL > PHONE > MONEY > DATE_RANGE > DATE > CATEGORY > PERSON > ORG > TEXT
    """
    ll = label.lower().strip()
    vs = value.strip()

    # 1. EMAIL — 값에 @ 포함 시 즉시 확정
    if EMAIL_RE.search(vs):
        return ValueType.EMAIL

    # 2. PHONE — 값 패턴 또는 레이블 + 숫자 포함
    if PHONE_RE.search(vs):
        return ValueType.PHONE
    if _label_match(ll, _LABEL_PHONE) and any(c.isdigit() for c in vs):
        return ValueType.PHONE

    # 3. MONEY — 값 패턴 우선, 없으면 레이블 + 숫자
    if MONEY_RE.search(vs):
        return ValueType.MONEY
    if _label_match(ll, _LABEL_MONEY) and any(c.isdigit() for c in vs):
        return ValueType.MONEY

    # 4. DATE_RANGE — "6개월" 같은 기간 표현 (DATE 보다 먼저)
    if DATE_RANGE_RE.search(vs):
        return ValueType.DATE_RANGE
    if _label_match(ll, _LABEL_DATE_RANGE):
        return ValueType.DATE_RANGE

    # 5. DATE — 특정 날짜
    if DATE_RE.search(vs):
        return ValueType.DATE
    if _label_match(ll, _LABEL_DATE) and any(c.isdigit() for c in vs):
        return ValueType.DATE

    # 6. CATEGORY — 영역/분야 레이블
    if _label_match(ll, _LABEL_CATEGORY):
        return ValueType.CATEGORY

    # 7. PERSON
    if _label_match(ll, _LABEL_PERSON):
        return ValueType.PERSON

    # 8. ORG
    if _label_match(ll, _LABEL_ORG):
        return ValueType.ORG

    return ValueType.TEXT
