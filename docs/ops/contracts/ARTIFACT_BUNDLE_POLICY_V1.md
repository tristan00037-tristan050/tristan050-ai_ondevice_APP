# ARTIFACT_BUNDLE_POLICY_V1

ARTIFACT_BUNDLE_POLICY_V1_TOKEN=1

- 목적: 운영 산출물(contracts + ai smoke)을 1개 번들로 묶어 최신 상태를 한 번에 확인한다.
- 번들 파일(고정):
  - docs/ops/reports/artifact_bundle_latest.json
  - docs/ops/reports/artifact_bundle_latest.md
- 입력 리포트(고정):
  - docs/ops/reports/repo_contracts_latest.json
  - docs/ops/reports/repo_contracts_latest.md
  - docs/ops/reports/ai_smoke_latest.json
  - docs/ops/reports/ai_smoke_latest.md
- 금지: 원문/덤프/장문(긴 라인) 유입. 번들은 "포인터 + 최소 메타"만 포함한다.
