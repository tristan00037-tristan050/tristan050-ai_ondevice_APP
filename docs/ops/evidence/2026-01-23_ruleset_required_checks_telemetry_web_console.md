# Ruleset / Branch protection evidence (masked)
Date: 2026-01-23

## 1) main required checks 설정 증거(필수)
Evidence source: GitHub Settings > Branches (Rulesets) OR Branch protection

Observed:
- Branch: main
- Required status checks include:
  - product-verify-telemetry
  - product-verify-web-console

How verified:
- Settings > Rulesets > <ruleset name> > Required status checks에서 위 2개가 체크되어 있음

## 2) merge queue(merge_group)에서도 reported 되는 근거(필수)
Observed:
- Workflows for required checks are configured to run on:
  - pull_request
  - merge_group
  - workflow_dispatch

How verified:
- .github/workflows/product-verify-telemetry.yml 과 product-verify-web-console.yml에 merge_group 트리거가 존재함
- merge queue 실행 시 해당 체크가 Pending으로 남지 않고 결론이 reported 됨을 확인함(링크 또는 run id)

## 3) 민감정보 마스킹 확인
- No secrets, tokens, internal URLs included.

