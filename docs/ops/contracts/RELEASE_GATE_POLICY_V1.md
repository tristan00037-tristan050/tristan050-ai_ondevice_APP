# RELEASE_GATE_POLICY_V1

RELEASE_GATE_POLICY_V1_TOKEN=1

- 목적: 릴리즈는 게이트(contracts + autodecision) 통과 없이는 불가.
- 필수 조건:
  1) docs/ops/reports/autodecision_latest.json 존재
  2) autodecision_latest.json의 decision == "ok"
  3) verify_repo_contracts.sh EXIT=0 (워크플로에서 수행되어야 함)
- 금지: 게이트 미실행/결과 없음 상태에서 릴리즈 진행
