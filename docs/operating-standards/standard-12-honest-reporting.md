# Standard 12 — Honest Reporting Pattern

Status: active from the next evaluation PR after PR #728
Scope: 모든 평가 PR 의 본문, 완료 보고, evidence summary
Codified by: GitHub PR #728 (Algorithm Branch 영역 변경 없음 — 정착 PR)
CI guard: `scripts/ci/check_standard_12.py`
Sentinel: `tests/standards/test_standard_12_honest_reporting.py`

## Purpose

자문 4차 8 은 "실패를 숨기지 않는 것 = 가장 중요한 성공" 이라고 명시했다.
정직 보고 패턴은 거버넌스 안전망 12차원 신뢰의 기반이다. 측정 결과가
기대에 못 미치더라도 그 사실을 정확히 보고하는 것이, 결과를 좋게 보이도록
조정하는 것보다 우선한다.

이 표준은 expected vs observed 의 명시, negative/zero delta 의 정직 보고,
natural shortage 명시, verdict 경계 준수, latent bug fail-closed, 측정값
임의 조정 금지를 단일 표준으로 정착시킨다.

## Verified source incidents

- PR #715/#716: body/evidence drift — 측정값과 본문 불일치 회귀.
- PR #725: latent bug — MIXED-A 67건이 over-strict 조건으로 전부 A6 분류,
  추정 회복량과 실측 회복량의 괴리가 원인 재평가를 촉발.
- PR #726: AR-2 hybrid merge noop — 기대 동작과 실제 동작의 차이를 정직
  보고 (noop 임을 숨기지 않음).
- PR #727: measurement integrity — false_deadline_rate 산식이 pre-patch
  필드를 사용한 결함을 정직 보고하고 산식만 정정 (값 유지).

## 보고 형식 표준 — expected_vs_observed

모든 평가 PR 의 완료 보고와 evidence summary 는 다음을 명시해야 한다.

- `expected_vs_observed`: 인계 박스/자문이 기대한 값과 실측 값을 나란히 명시
  - `expected`: 인계/자문이 제시한 기대치 (예: deadline_f1 0.86)
  - `observed`: 실제 측정값 (예: deadline_f1 0.8702)
- `delta`: observed − expected. **0 이거나 음수여도 반드시 명시한다.**
- 인계 박스 기대치와 실측이 다르면 그 차이와 원인을 본문에 서술한다.

## delta 정직 보고

| delta | 보고 의무 |
|---|---|
| positive | 개선폭 명시 |
| negative | 회귀/하락폭을 숨기지 않고 명시 + 원인 서술 |
| zero | "유지 (Δ 0)" 로 명시 — 값이 0 이라고 생략 불가 |
| 산식 정정만 | 측정값 불변임을 명시하고 정정 범위(산식)를 한정 서술 |

## natural shortage 명시 의무

AB / sampled 평가에서 declared composition 을 채우지 못한 경우:

- `natural_shortage` 를 true 로 기록하고
- `natural_shortage_note` 에 부족 원인 (unique pool 소진, multi-category
  경합 등) 을 명시한다.
- 인위적 부족(greedy global-seen 등)은 차단하고, multi-category fallback
  후에도 남는 부족만 `AB_COMPOSITION_NATURAL_SHORTAGE` 로 보고한다.

## verdict 경계

| verdict | 의미 | 허용 범위 |
|---|---|---|
| `MEASURED_ONLY` | 측정만 수행, 적용 없음 | 측정/정착 PR |
| `PATCH_CONTINUE` | patch 적용 + 추가 cycle 필요 | patch PR |
| `HOLD` | latent bug / 정합 미달로 보류 | 결함 발견 시 |
| `PROCEED` | **금지** — 별도 최종 재측정 PR 영역 | 평가 PR 본문 출현 금지 |

`PROCEED` 토큰은 평가 PR 본문/보고/evidence 에 출현해서는 안 된다
(forbidden grep 패턴). 정착·측정·patch PR 의 STATUS 는 `MEASURED_ONLY` /
`PATCH_CONTINUE` / `HOLD` 중 하나여야 한다.

## latent bug 패턴 (PR #725 정합)

추정 회복량 대비 실측이 현저히 낮으면 (관측 < 추정 × 0.5) 측정 결과를
그대로 보고하지 말고 원인 재평가를 의무화한다. over-strict 조건, 잘못된
분류 로직, evidence/source mismatch 등 latent bug 를 fail-closed 로
드러낸다. 추정이 빗나간 사실 자체를 정직하게 보고한다.

## measurement integrity 우선 (PR #727 정합)

측정 산식의 결함(예: pre-patch 필드 오용)을 발견하면 결과를 좋게 만들기
위해서가 아니라 측정 정합을 위해 산식을 정정한다. 정정 후 값이 변동/유지
여부와 무관하게, 정정 범위와 `computed_from_*` 근거를 evidence 에 명시한다.

## 측정값 임의 조정 절대 금지

- 측정값을 임의/수동으로 조정하지 않는다.
- 테스트를 통과시키기 위해 threshold 를 낮추지 않는다.
- 회귀/실패를 은폐하지 않는다.
- 이 신호들은 CI guard `check_standard_12.py` 의 확장 forbidden 패턴으로
  차단된다.

## 의무 적용 범위

모든 평가 PR template 에 자동 적용된다. CI guard 는 evidence summary 의
forbidden 10 패턴 + Standard 12 확장 패턴 0건을 검증하고, STATUS 라인
정합과 expected_vs_observed 명시를 검사한다.
