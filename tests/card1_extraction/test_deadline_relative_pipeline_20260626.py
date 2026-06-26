from __future__ import annotations

from unittest.mock import patch

from butler_pc_core.card1_extraction import extract_card1, extract_deadlines


def test_deadline_friday_5pm_until_pipeline_wrapper() -> None:
    text = "보고서를 금요일 오후 5시까지 전달해주세요."

    found = extract_deadlines(text)
    assert "금요일 오후 5시까지" in found

    with patch.dict("os.environ", {"SKIP_LLM": "true"}):
        result = extract_card1(text)

    assert result.deadline_raw == "금요일 오후 5시까지"
    assert result.deadline is None


def test_deadline_next_monday_before_meeting_pipeline_wrapper() -> None:
    text = "다음 주 월요일 회의 전까지 최종본을 공유해주세요."

    found = extract_deadlines(text)
    assert "다음 주 월요일 회의 전까지" in found

    with patch.dict("os.environ", {"SKIP_LLM": "true"}):
        result = extract_card1(text)

    assert result.deadline_raw == "다음 주 월요일 회의 전까지"
    assert result.deadline is None


def test_no_deadline_plain_next_monday_notice_pipeline_wrapper() -> None:
    text = "다음 주 월요일 회의가 있습니다. 참석자 명단을 공유드립니다."

    with patch.dict("os.environ", {"SKIP_LLM": "true"}):
        result = extract_card1(text)

    assert result.deadline_raw == ""
    assert result.deadline is None
