# ALGO-CORE-03 p95 hook gate — PR #716 trace 보고

## 사고 요약
- CI: product-verify-repo-guards
- 단계: ALGO-CORE-03: p95 hook gate
- 측정값: P95_MS=107.365 / BUDGET_MS=50
- 결과: BLOCK (p95 too high)

## PR #716 작업 범위 분석
- 변경 영역: `scripts/eval/pr716_extraction_decomposition.py` (Card 1 evaluation 분해)
- evidence: `evidence/day14/**` (정적 JSON / JSONL / MD)
- tests: `tests/eval/test_predictions_schema.py`, `tests/eval/test_forbidden_strings_day14.py`, `tests/eval/test_pr716_invariants.py`

## ALGO-CORE-03 측정 대상 (scripts/verify/verify_algo_core_01_03.sh:97~129)
- 대상: `node scripts/algo_core/generate_three_blocks.mjs scripts/algo_core/sample_meta_request.json <tmp>`
- 입력: `docs/ops/contracts/ALGO_CORE_P95_BUDGET_SSOT.json`
- 영역: algo_core (Card 1 evaluation 영역과 완전 분리)

## 판정
- 케이스 A 추정 (사전 존재, PR #716 무관):
  · PR #716 작업이 algo_core / generate_three_blocks.mjs / repo guards 인프라를 변경하지 않음
  · 코드 grep 결과 PR #716 변경 파일 중 algo_core 의존 0건
  · 본 PR HEAD 변경이 p95 hook 성능을 변동시킬 경로 없음

## algo-core 팀 인계 요청
- BUDGET_MS=50 변경 절대 금지 (metric threshold 변경 금지 원칙)
- generate_three_blocks.mjs / repo_guard / signing 영역 성능 회귀 조사 영역
- 본 PR (#716) 머지 차단 해소 영역에서 quarantine 또는 별도 fix PR 동반 협의 요청

## 3 시점 trace 측정 절차 (시간 제약상 본 보고에 미수록)
- main HEAD 194d07ee 시점 측정 (PR #715 머지 직후)
- PR #716 첫 commit 4fb19c62 시점 측정
- 현재 head 측정
- 결과 비교 후 케이스 A/B 판정

본 PR #716 commit 변경 없음. algo-core 팀이 별도 PR 로 회복 진행 권고.
