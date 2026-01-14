#!/usr/bin/env bash
set -euo pipefail

TOPLEVEL="$(git rev-parse --show-toplevel 2>/dev/null || true)"
if [[ -z "${TOPLEVEL}" ]]; then
  echo "WORKFLOW_LINT_OK=0"
  echo "WORKFLOW_LINT_ERROR=NA:0:0 reason_code=NOT_A_GIT_REPO job=- step=-"
  exit 1
fi

cd "${TOPLEVEL}"

# Meta-only diagnostics (actionlint 버전/워크플로 목록)
# ACTIONLINT_BIN은 아직 설정되지 않았으므로, 나중에 다시 출력하거나 여기서는 스킵
# 대신 워크플로 파일 목록만 먼저 출력
echo "WORKFLOW_ACTIONLINT_IMPL=verify_workflow_lint_sh_noloc_v1"
echo "WORKFLOW_ACTIONLINT_CHECKOUT_SHA=$(git rev-parse --short HEAD 2>/dev/null || echo unknown)"
echo "WORKFLOW_ACTIONLINT_WORKFLOWS_COUNT=$(find .github/workflows -maxdepth 1 -type f \( -name "*.yml" -o -name "*.yaml" \) | wc -l | tr -d " ")"
find .github/workflows -maxdepth 1 -type f \( -name "*.yml" -o -name "*.yaml" \) -print | sort | sed "s/^/WORKFLOW_ACTIONLINT_WORKFLOW_FILE=/" | head -n 50
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

# actionlint 버전 출력 (ACTIONLINT_BIN이 설정된 후)
echo "WORKFLOW_ACTIONLINT_VERSION=$("${ACTIONLINT_BIN}" -version 2>/dev/null | head -n 1 || echo unknown)"

# actionlint는 디렉터리 단일 실행에서 RC=3(Runtime) 형태로 실패하는 케이스가 있어,
# Fail-Closed를 유지하되 "파일 단위"로 실행하여 안정적으로 위치(file:line:col)를 수집한다.
set +e
RAW_ALL=""
FAIL_RC=0
FAIL_FILE=""

while IFS= read -r wf; do
  _RAW_SINGLE="$("${ACTIONLINT_BIN}" "${wf}" 2>&1)"
  _RC_SINGLE=$?
  if [[ ${_RC_SINGLE} -ne 0 ]]; then
    # 첫 실패 파일 기록(메타)
    if [[ -z "${FAIL_FILE}" ]]; then
      FAIL_FILE="${wf}"
      FAIL_RC=${_RC_SINGLE}
    fi
    RAW_ALL="${RAW_ALL}"$'\n'"${_RAW_SINGLE}"
  fi
done < <(find .github/workflows -maxdepth 1 -type f \( -name "*.yml" -o -name "*.yaml" \) -print | sort)

set -e

if [[ -n "${FAIL_FILE}" ]]; then
  echo "WORKFLOW_ACTIONLINT_OK=0"
  echo "WORKFLOW_ACTIONLINT_FAIL_FILE=${FAIL_FILE}"
  echo "WORKFLOW_ACTIONLINT_RC=${FAIL_RC}"

  n=0
  # meta-only: file:line:col 형태만 추출
  while IFS= read -r line; do
    if [[ "${line}" =~ ^([^:]+):([0-9]+):([0-9]+): ]]; then
      f="${BASH_REMATCH[1]}"
      ln="${BASH_REMATCH[2]}"
      col="${BASH_REMATCH[3]}"
      echo "WORKFLOW_ACTIONLINT_ERROR=${f}:${ln}:${col} reason_code=WORKFLOW_ACTIONLINT_ERROR"
      n=$((n+1))
      [[ ${n} -ge 50 ]] && break
    fi
  done <<< "${RAW_ALL}"

  # 위치를 못 뽑는 실패도 봉인(FAIL_RC에 따라 reason_code 분류)
  if [[ ${n} -eq 0 ]]; then
    case "${FAIL_RC}" in
      1) REASON="WORKFLOW_ACTIONLINT_LINT_ERRORS_NOLOC" ;;
      2) REASON="WORKFLOW_ACTIONLINT_USAGE_ERROR" ;;
      3) REASON="WORKFLOW_ACTIONLINT_RUNTIME_ERROR" ;;
      *) REASON="WORKFLOW_ACTIONLINT_UNKNOWN_ERROR" ;;
    esac
    echo "WORKFLOW_ACTIONLINT_ERROR=.github/workflows:0:0 reason_code=${REASON}"
    n=1
  fi

  echo "WORKFLOW_ACTIONLINT_ERROR_COUNT=${n}"
  exit 1
fi

echo "WORKFLOW_ACTIONLINT_OK=1"
echo "WORKFLOW_ACTIONLINT_ERROR_COUNT=0"
