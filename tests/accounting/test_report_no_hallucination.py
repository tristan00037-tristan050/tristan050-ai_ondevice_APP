"""test_report_no_hallucination.py — LLM 보고서 환각 탐지 검증."""
from __future__ import annotations

import json
import re

import pytest

from .conftest import make_synthetic_df, _skip_no_pandas


# 입력 summary에 있는 숫자만 포함한 모범 보고서
_CLEAN_REPORT = """\
## 회계 분류 보고서

총 **100**건 중 **95**건이 분류되었습니다.

| 계정과목 | 건수 |
|------|------|
| 급여 | 10 |
| 통신비 | 5 |
"""

# 입력 summary에 없는 수치(999)를 포함한 환각 보고서
_HALLUCINATED_REPORT = """\
## 회계 분류 보고서

총 **100**건 중 **95**건이 분류되었으며, 추정 연간 비용은 **999**만 원입니다.
"""

_CLEAN_SUMMARY = {
    "total_rows": 100,
    "classified_rows": 95,
    "unclassified_rows": 5,
    "categories": {
        "급여": {"count": 10, "avg_confidence": 0.95},
        "통신비": {"count": 5, "avg_confidence": 0.8},
    },
    "avg_confidence": 0.87,
}


def test_validate_report_clean():
    """summary에 있는 수치만 포함한 보고서 → 환각 없음."""
    from butler_pc_core.accounting.report import validate_report

    suspicious = validate_report(_CLEAN_REPORT, _CLEAN_SUMMARY)
    assert suspicious == [], f"예상치 않은 수치 탐지: {suspicious}"


def test_validate_report_hallucination_detected():
    """summary에 없는 수치 999 포함 보고서 → 환각 탐지."""
    from butler_pc_core.accounting.report import validate_report

    suspicious = validate_report(_HALLUCINATED_REPORT, _CLEAN_SUMMARY)
    assert "999" in suspicious, f"환각 수치 999를 탐지하지 못함: {suspicious}"


def test_generate_report_calls_llm():
    """generate_report가 LLM 콜러블을 호출하는지 검증."""
    from butler_pc_core.accounting.report import generate_report

    called_with: list[tuple[str, str]] = []

    def mock_llm(system: str, user: str) -> str:
        called_with.append((system, user))
        # summary JSON을 user에서 읽어 수치만 포함한 깨끗한 보고서 반환
        return f"## 보고서\n총 {_CLEAN_SUMMARY['total_rows']}건 분류됨."

    report = generate_report(_CLEAN_SUMMARY, mock_llm)

    assert len(called_with) == 1, "LLM이 정확히 1회 호출되어야 함"
    system_prompt, user_content = called_with[0]
    assert "JSON에 없는 수치" in system_prompt, "시스템 프롬프트에 환각 금지 지시 없음"
    assert json.dumps(_CLEAN_SUMMARY, ensure_ascii=False)[:20] in user_content or \
           "json" in user_content.lower(), "user content에 summary JSON 미포함"
    assert "총 100건" in report


def test_generate_report_no_hallucination_in_mock_output():
    """모의 LLM 출력 보고서 환각 검증 통과."""
    from butler_pc_core.accounting.report import generate_report, validate_report

    def clean_llm(system: str, user: str) -> str:
        return _CLEAN_REPORT

    report = generate_report(_CLEAN_SUMMARY, clean_llm)
    suspicious = validate_report(report, _CLEAN_SUMMARY)
    assert suspicious == [], f"환각 탐지 (예상치 않은 수치): {suspicious}"


@_skip_no_pandas
def test_build_summary_structure():
    """build_summary 반환 구조 검증."""
    from butler_pc_core.accounting.classifier import classify_df
    from butler_pc_core.accounting.report import build_summary

    df = make_synthetic_df(50)
    result = classify_df(df)
    summary = build_summary(result)

    assert "total_rows" in summary
    assert "classified_rows" in summary
    assert "unclassified_rows" in summary
    assert "categories" in summary
    assert "avg_confidence" in summary
    assert summary["total_rows"] == 50
    assert summary["classified_rows"] + summary["unclassified_rows"] == 50
    assert isinstance(summary["categories"], dict)
