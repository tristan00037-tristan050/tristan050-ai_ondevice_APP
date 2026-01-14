#!/usr/bin/env bash
set -euo pipefail

TOPLEVEL="$(git rev-parse --show-toplevel 2>/dev/null || true)"
if [[ -z "${TOPLEVEL}" ]]; then
  echo "WORKFLOW_LINT_OK=0"
  echo "WORKFLOW_LINT_ERROR=NA:0:0 reason_code=NOT_A_GIT_REPO job=- step=-"
  exit 1
fi

cd "${TOPLEVEL}"

echo "WORKFLOW_ACTIONLINT_IMPL=verify_workflow_lint_sh_noloc_v1"
echo "WORKFLOW_ACTIONLINT_CHECKOUT_SHA=$(git rev-parse --short HEAD 2>/dev/null || echo unknown)"
# 1) YAML 구조/문법: 파싱 + 빈 step + 중복키 Fail-Closed
python scripts/ci/workflow_lint_gate.py

# 2) 추가 정적검사: actionlint (없으면 Fail-Closed)
GOPATH="$(go env GOPATH 2>/dev/null || true)"
ACTIONLINT_BIN="$(command -v actionlint || true)"
if [[ -z "${ACTIONLINT_BIN}" && -x "${HOME}/go/bin/actionlint" ]]; then
  ACTIONLINT_BIN="${HOME}/go/bin/actionlint"
fi

if [[ -z "${ACTIONLINT_BIN:-}" && -n "${GOPATH:-}" && -x "${GOPATH}/bin/actionlint" ]]; then
  ACTIONLINT_BIN="${GOPATH}/bin/actionlint"
fi
if [[ -z "${ACTIONLINT_BIN:-}" && -x "${HOME}/go/bin/actionlint" ]]; then
  ACTIONLINT_BIN="${HOME}/go/bin/actionlint"
fi

if [[ -z "${ACTIONLINT_BIN:-}" ]]; then
  echo "WORKFLOW_ACTIONLINT_OK=0"
  echo "WORKFLOW_ACTIONLINT_ERROR=.github/workflows:0:0 reason_code=ACTIONLINT_NOT_FOUND"
  echo "WORKFLOW_ACTIONLINT_DIAG_PATH=${PATH}"
  echo "WORKFLOW_ACTIONLINT_DIAG_HOME=${HOME}"
  echo "WORKFLOW_ACTIONLINT_DIAG_GOPATH=${GOPATH:-unknown}"
  ls -la "${HOME}/go/bin" 2>/dev/null || true
  if [[ -n "${GOPATH:-}" ]]; then ls -la "${GOPATH}/bin" 2>/dev/null || true; fi
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

  # 핵심 보강: 위치를 못 뽑는 실패(RAW가 file:line:col 형태가 아님)도 meta-only로 1줄 강제 출력
  if [[ ${n} -eq 0 ]]; then
    echo "WORKFLOW_ACTIONLINT_ERROR=.github/workflows:0:0 reason_code=WORKFLOW_ACTIONLINT_ERROR_NOLOC"
    echo "WORKFLOW_ACTIONLINT_RC=${RC}"
    n=1
  fi

  echo "WORKFLOW_ACTIONLINT_ERROR_COUNT=${n}"
  exit 1
fi

echo "WORKFLOW_ACTIONLINT_OK=1"
