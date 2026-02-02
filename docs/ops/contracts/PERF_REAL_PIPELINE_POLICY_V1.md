# PERF Real Pipeline Policy v1 (SSOT)

이 정책은 real pipeline P95 검증을 "1회 통과"에서 "회귀 관리(표본+변동성)"로 승격한다.

## Modes
- merge_group / pull_request: 작은 표본(N)로 빠른 회귀 차단
- schedule: 큰 표본(N)로 분산/드리프트 감시

## Fixed numbers (SSOT)
MERGE_N=9
SCHEDULE_N=50

# 허용되는 표준편차 상한(ms)
MAX_STDDEV_MS=25

# P95 예산(ms) - 기존 예산 SSOT가 있으면 그 값과 일치해야 한다
P95_BUDGET_MS=200

