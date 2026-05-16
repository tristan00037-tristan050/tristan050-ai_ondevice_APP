# Standard 12 — Honest Reporting Pattern Specification

## metadata
- dataset_id: card1_evalset_v1_1_500
- source_pr: 728
- codification_type: operating_standard
- verdict: MEASURED_ONLY
- generated_at: 2026-05-16

## 정착 목적

자문 4차 8: "실패를 숨기지 않는 것 = 가장 중요한 성공". 정직 보고 패턴은
거버넌스 안전망 12차원 신뢰의 기반. 측정 결과가 기대에 못 미쳐도 그 사실을
정확히 보고하는 것이 결과를 좋게 보이도록 조정하는 것보다 우선.

## 보고 형식 표준 — expected_vs_observed

모든 평가 PR 완료 보고/evidence summary 는 expected_vs_observed 명시:
- expected: 인계/자문 기대치
- observed: 실측값
- delta: observed − expected (0 / 음수도 명시 의무)
인계 박스 기대치와 실측 차이 시 원인 서술.

## delta 정직 보고

| delta | 보고 의무 |
|---|---|
| positive | 개선폭 명시 |
| negative | 회귀/하락폭 은폐 금지 + 원인 서술 |
| zero | "유지 (Δ 0)" 명시 — 생략 불가 |
| 산식 정정만 | 측정값 불변 명시 + 정정 범위 한정 |

## natural shortage 명시 의무

natural_shortage=true 시 natural_shortage_note 에 부족 원인 명시. 인위적
부족(greedy global-seen)은 차단. multi-category fallback 후 잔여 부족만
AB_COMPOSITION_NATURAL_SHORTAGE 보고.

## verdict 경계

MEASURED_ONLY / PATCH_CONTINUE / HOLD 만 허용. 금지 verdict 토큰은 평가 PR
본문/보고/evidence 출현 금지 (forbidden grep 패턴). 금지 verdict 는 별도
최종 재측정 PR 영역이며, 해당 토큰은 본 표준 문서에 직접 표기하지 않는다.

## latent bug 패턴 (PR #725 정합)

관측 < 추정 × 0.5 시 측정 결과를 그대로 보고하지 말고 원인 재평가 의무.
over-strict 조건 / 잘못된 분류 로직 / evidence-source mismatch 등 latent
bug 를 fail-closed 로 노출. 추정이 빗나간 사실 자체를 정직 보고.

## measurement integrity 우선 (PR #727 정합)

측정 산식 결함(pre-patch 필드 오용 등) 발견 시 결과 미화가 아니라 측정
정합을 위해 산식 정정. 정정 후 값 변동/유지 무관, 정정 범위 + computed_from_*
근거를 evidence 명시.

## 측정값 임의 조정 절대 금지

측정값 임의/수동 조정 금지, 통과를 위한 threshold 하향 금지, 회귀/실패
은폐 금지. CI guard check_standard_12.py 확장 forbidden 패턴으로 차단.

## 산출물 정합

- 정착 문서: docs/operating-standards/standard-12-honest-reporting.md
- CI guard: scripts/ci/check_standard_12.py
- sentinel: tests/standards/test_standard_12_honest_reporting.py (5건)
- PR template: .github/PULL_REQUEST_TEMPLATE/eval_pr.md

## verdict: MEASURED_ONLY (정착 PR — 알고리즘 변경 없음)
