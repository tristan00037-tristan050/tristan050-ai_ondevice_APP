# Ruleset / Branch protection evidence (masked)
Date: 2026-01-23

## 1) main required checks 설정 증거(필수)
Observed:
- Branch: main
- Required status checks include:
  - product-verify-repo-guards

How verified:
- Settings > Rulesets(or Branch protection) > main rule에서 required checks 목록에 'product-verify-repo-guards'가 포함됨을 확인

## 2) merge queue(merge_group)에서도 reported 되는 근거(필수)
Observed:
- .github/workflows/product-verify-repo-guards.yml 워크플로 트리거에 merge_group 포함

How verified (output-based):
- repository file 확인:
  - .github/workflows/product-verify-repo-guards.yml 에 on: merge_group 포함

## 3) 민감정보 마스킹 확인
- No secrets, tokens, internal URLs included.

