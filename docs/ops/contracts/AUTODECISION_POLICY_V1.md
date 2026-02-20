# AUTODECISION_POLICY_V1

AUTODECISION_POLICY_V1_TOKEN=1

- 목적: repo_contracts_latest / ai_smoke_latest 결과를 code-only 결론으로 변환한다.
- 출력(고정):
  - docs/ops/reports/autodecision_latest.json
  - docs/ops/reports/autodecision_latest.md
- 결론 규칙:
  - FAIL_KEYS(값이 "1"이 아닌 키)가 1개라도 있으면 decision=block
  - FAIL_KEYS가 0개면 decision=ok
  - 키 이름이 *_SKIPPED로 끝나는 키는 평가 대상에서 제외(상태 키 착시 block 방지)
- reason_code 규칙:
  - reason_code는 "키 이름"만 허용(자연어/장문 금지)
  - 최대 10개만 기록
