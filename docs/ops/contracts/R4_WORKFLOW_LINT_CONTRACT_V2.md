# R4_WORKFLOW_LINT_CONTRACT_V2
R4(.github/workflows) 변경 PR 최소 합격 기준:
- PASS는 4라인 키로 판정한다:
  - WORKFLOW_LINT_OK=1
  - WORKFLOW_LINT_ERROR_COUNT=0
  - WORKFLOW_ACTIONLINT_OK=1
  - WORKFLOW_ACTIONLINT_ERROR_COUNT=0
- FAIL이면 좌표(<file>:<line>:<col>) 또는 NOLOC 표식이 반드시 있어야 한다.
- FAIL이면 meta-only로 FAIL_FILE/RC/ERROR_COUNT를 반드시 출력한다.
