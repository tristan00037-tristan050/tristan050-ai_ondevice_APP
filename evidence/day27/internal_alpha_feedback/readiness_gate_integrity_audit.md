# Readiness Gate Integrity Audit (Codex P1 — 강화 안건 15)

## metadata
- source_pr: 733
- branch: Internal-Alpha-Feedback
- correction_cycle: Codex P1 (readiness gate measurement integrity)
- verdict: MEASURED_ONLY

## Codex P1 결함 본질

`controlled_beta_readiness_assessment` 의 7개 gate 중 2개
(`false_deadline_rate <= 0.02`, `no_action_fp_rate <= 0.03`)가 literal
`True` 로 hardcoded 되어 있었다. 해당 safety metric 이 regression(임계값
초과)해도 gate 가 무조건 True 를 반환 → **fail-open** — Controlled Beta
readiness 판정이 실제 metric 상태를 반영하지 못했다.

## 정정

`compute_readiness(safety, ...)` 함수로 추출하고, 7개 gate 전부 실제
metric 값에서 비교 산출한다:

| gate | metric source | 산출 |
|---|---|---|
| strict_action_f1 ≥ 0.90 | MAIN_METRICS | 실제 비교 |
| manual_suggestion_precision ≥ 0.80 | reviewer_feedback_result | 실제 비교 |
| deadline_f1 ≥ 0.86 | MAIN_METRICS | 실제 비교 |
| false_deadline_rate ≤ 0.02 | MAIN_SAFETY (PR #732 588f1db2) | **실제 비교 (정정)** |
| no_action_fp_rate ≤ 0.03 | MAIN_SAFETY (PR #732 588f1db2) | **실제 비교 (정정)** |
| auto_apply OFF | instrumentation schema 구조 invariant | 구조 불변 |
| privacy audit pass | privacy guard 실측 (raw_text_leak) | 실제 비교 |

`controlled_beta_ready = all(criteria.values())` — metric regression 시
자동 fail-closed.

## readiness gate measurement integrity 표준

readiness assessment / gate evaluation 의 각 gate 는:

1. **hardcoded literal 금지** — gate 결과는 실제 metric 값에서 산출.
2. **metric source 명시** — 각 gate 에 `metric_value` / `metric_source` /
   `threshold` / `comparator` 를 evidence 에 기록.
3. **fail-open 회귀 sentinel 의무** — metric 이 임계값을 넘는 negative
   test case 를 sentinel 에 포함, gate 가 False 로 fail-closed 됨을 검증.

## fail-open 회귀 sentinel (negative test case)

본 PR sentinel:
- `#13` false_deadline_rate 0.021 (> 0.02) → gate False, ready False
- `#14` no_action_fp_rate 0.031 (> 0.03) → gate False, ready False
- `#15` 정상 metric → gate True 정합
- `#16` controlled_beta_ready == all(criteria)

## 측정값 영향 (정직 보고 — 시나리오 1)

현 metric: false_deadline_rate 0.014 (≤ 0.02), no_action_fp_rate 0.0273
(≤ 0.03) — 두 gate 모두 충족. 정정 전후 criteria_met 5/7,
controlled_beta_ready false — **분포 불변**. P1 은 latent fail-open 결함의
선제 정정이며 측정값 임의 조정이 아니다 (PR #732 P2 패턴 정합).

## 강화 안건 15번 정착

본 audit 은 강화 안건 15번(readiness gate integrity 표준) 정착 사례다.
향후 모든 readiness assessment / gate evaluation PR 은 hardcoded literal
gate 를 금지하고 fail-open 회귀 sentinel 을 의무화한다 (Standard 12-I
안건 정량 기반).
