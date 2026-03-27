from __future__ import annotations

from scripts.ai.phase_c_shared import SAFE_POLICY_KEYWORDS_KO, contains_policy_refusal, summarize_latencies_ms


def test_policy_keywords_include_english() -> None:
    for kw in ['Sorry', 'cannot', "can't", 'not allowed', 'comply', 'prohibited', 'not permitted']:
        assert kw in SAFE_POLICY_KEYWORDS_KO


def test_contains_policy_refusal() -> None:
    assert contains_policy_refusal('Sorry, I cannot comply with that request.')
    assert contains_policy_refusal('승인 절차가 필요하여 허용되지 않습니다.')
    assert not contains_policy_refusal('정상 응답입니다.')


def test_latency_summary() -> None:
    summary = summarize_latencies_ms([10.0, 20.0, 30.0])
    assert summary['count'] == 3
    assert summary['max_ms'] == 30.0
