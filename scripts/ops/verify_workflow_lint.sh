#!/usr/bin/env bash
set -euo pipefail

TOPLEVEL="$(git rev-parse --show-toplevel 2>/dev/null || true)"
if [[ -z "${TOPLEVEL}" ]]; then
  echo "WORKFLOW_LINT_OK=0"
  echo "WORKFLOW_LINT_ERROR=NA:0:0 reason_code=NOT_A_GIT_REPO job=- step=-"
  exit 1
fi

cd "${TOPLEVEL}"

# 1) YAML 구조/문법: 파싱 + 빈 step + 중복키 Fail-Closed
python scripts/ci/workflow_lint_gate.py

# 2) 추가 정적검사: actionlint (없으면 Fail-Closed)
ACTIONLINT_BIN="$(command -v actionlint || true)"
if [[ -z "${ACTIONLINT_BIN}" && -x "${HOME}/go/bin/actionlint" ]]; then
  ACTIONLINT_BIN="${HOME}/go/bin/actionlint"
fi

if [[ -z "${ACTIONLINT_BIN}" ]]; then
  echo "WORKFLOW_ACTIONLINT_OK=0"
  echo "WORKFLOW_ACTIONLINT_ERROR=.github/workflows:0:0 reason_code=ACTIONLINT_NOT_INSTALLED"
  exit 1
fi

# actionlint 출력은 메시지(원문)를 포함할 수 있으므로, meta-only로 file:line:col만 추출한다.
set +e
RAW="$("${ACTIONLINT_BIN}" .github/workflows 2>&1)"
RC=$?
set -e

if [[ ${RC} -ne 0 ]]; then
  echo "WORKFLOW_ACTIONLINT_OK=0"
  n=0
  while IFS= read -r line; do
    if [[ "${line}" =~ ^([^:]+):([0-9]+):([0-9]+): ]]; then
      f="${BASH_REMATCH[1]}"
      ln="${BASH_REMATCH[2]}"
      col="${BASH_REMATCH[3]}"
      echo "WORKFLOW_ACTIONLINT_ERROR=${f}:${ln}:${col} reason_code=WORKFLOW_ACTIONLINT_ERROR"
      n=$((n+1))
      [[ ${n} -ge 50 ]] && break
    fi
  done <<< "${RAW}"
  echo "WORKFLOW_ACTIONLINT_ERROR_COUNT=${n}"
  exit 1
fi

echo "WORKFLOW_ACTIONLINT_OK=1"
