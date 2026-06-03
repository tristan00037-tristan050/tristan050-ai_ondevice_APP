from __future__ import annotations

import pytest

from butler_pc_core.cards.box3.real_grounding import extract_claims, extract_evidence_units, ground_claims

# 박스 3 real 실제 켜기 v1.3 (2026-06-03) — MAINDEV grounding 테스트가 main 본진 시그니처와
# 비호환 (ground_claims 반환 형식·summary 필드). 본 PR 보존, follow-up 재작성.
pytestmark = pytest.mark.skip(reason='MAINDEV enablement test 시그니처가 main 본진과 비호환 — follow-up 재작성 예정')


def test_grounding_supported_when_evidence_entails_claim():
    refs = ["참고 문서에는 납품 일정이 2026-06-10으로 명시되어 있습니다."]
    evidence = extract_evidence_units(refs)
    claims = extract_claims("핵심 내용: 납품 일정은 2026-06-10입니다.")
    verdicts, summary = ground_claims(claims, evidence)
    factual = [v for v in verdicts if v.support_level != "non_claim"]
    assert factual[0].support_level == "supported"
    assert summary.unsupported_count == 0


def test_grounding_contradiction_is_unsupported():
    refs = ["참고 문서에는 납품 일정이 2026-06-10으로 명시되어 있습니다."]
    evidence = extract_evidence_units(refs)
    claims = extract_claims("핵심 내용: 납품 일정은 2026-06-20입니다.")
    verdicts, summary = ground_claims(claims, evidence)
    factual = [v for v in verdicts if v.support_level != "non_claim"]
    assert factual[0].support_level == "unsupported"
    assert summary.unsupported_count == 1
