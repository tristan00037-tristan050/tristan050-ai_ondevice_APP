# Product-Verify Workflow Template (SSOT)

Status: SEALED

## 목적
- product-verify-* 워크플로의 skip/bypass 재발을 구조적으로 차단한다.

## 필수 규칙(모든 .github/workflows/product-verify-*.yml)
1) on: pull_request 포함
2) on: merge_group 포함
3) on: workflow_dispatch 포함
4) job-level if 금지 (예: jobs.<job>.if:)
5) gate job 존재(최소 1개 job이 다른 job 결과를 fail-closed로 게이트)
