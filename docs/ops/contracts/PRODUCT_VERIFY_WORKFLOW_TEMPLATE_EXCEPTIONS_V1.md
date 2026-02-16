# PRODUCT VERIFY WORKFLOW TEMPLATE — EXCEPTIONS v1 (SSOT)

Date: 2026-02-16
Status: DECIDED

## Exception list (allowed to NOT have pull_request/merge_group)

- .github/workflows/product-verify-onprem-proof-strict.yml
  - allowed triggers: workflow_dispatch, schedule
  - reason: self-hosted runner availability must not block PR/merge_group

