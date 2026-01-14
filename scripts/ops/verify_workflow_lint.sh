#!/usr/bin/env bash
set -euo pipefail

TOPLEVEL="$(git rev-parse --show-toplevel 2>/dev/null || true)"
if [[ -z "${TOPLEVEL}" ]]; then
  echo "WORKFLOW_ACTIONLINT_OK=0"
  echo "WORKFLOW_ACTIONLINT_ERROR_COUNT=1"
  echo "WORKFLOW_ACTIONLINT_NOLOC=1"
  echo "WORKFLOW_ACTIONLINT_FAIL_FILE=.github/workflows"
  echo "WORKFLOW_ACTIONLINT_RC=1"
  echo "WORKFLOW_ACTIONLINT_ERROR=NA:0:0 reason_code=NOT_A_GIT_REPO"
  exit 1
fi

cd "${TOPLEVEL}"

echo "WORKFLOW_ACTIONLINT_CHECKOUT_SHA=$(git rev-parse --short HEAD 2>/dev/null || echo unknown)"

ACTIONLINT_BIN="$(command -v actionlint || true)"
if [[ -z "${ACTIONLINT_BIN}" ]]; then
  echo "WORKFLOW_ACTIONLINT_IMPL=missing"
  echo "WORKFLOW_ACTIONLINT_OK=0"
  echo "WORKFLOW_ACTIONLINT_ERROR_COUNT=1"
  echo "WORKFLOW_ACTIONLINT_NOLOC=1"
  echo "WORKFLOW_ACTIONLINT_FAIL_FILE=.github/workflows"
  echo "WORKFLOW_ACTIONLINT_RC=127"
  echo "WORKFLOW_ACTIONLINT_ERROR=.github/workflows:0:0 reason_code=ACTIONLINT_MISSING"
  exit 1
fi

echo "WORKFLOW_ACTIONLINT_IMPL=$("${ACTIONLINT_BIN}" -version 2>/dev/null | head -n 1 || echo actionlint)"

shopt -s nullglob
FILES=(.github/workflows/*.yml .github/workflows/*.yaml)
# Stable ordering (sort) to make outputs deterministic
IFS=$'\n' FILES=($(printf '%s\n' "${FILES[@]}" | sort))
unset IFS
echo "WORKFLOW_ACTIONLINT_WORKFLOWS_COUNT=${#FILES[@]}"
for f in "${FILES[@]}"; do
  echo "WORKFLOW_ACTIONLINT_WORKFLOW_FILE=${f}"
done

if [[ "${#FILES[@]}" -eq 0 ]]; then
  echo "WORKFLOW_ACTIONLINT_OK=0"
  echo "WORKFLOW_ACTIONLINT_ERROR_COUNT=1"
  echo "WORKFLOW_ACTIONLINT_NOLOC=1"
  echo "WORKFLOW_ACTIONLINT_FAIL_FILE=.github/workflows"
  echo "WORKFLOW_ACTIONLINT_RC=2"
  echo "WORKFLOW_ACTIONLINT_ERROR=.github/workflows:0:0 reason_code=NO_WORKFLOW_FILES"
  exit 1
fi

ERROR_COUNT=0
NOLOC_COUNT=0

tmp="$(mktemp)"
trap 'rm -f "${tmp}"' EXIT

for f in "${FILES[@]}"; do
  : > "${tmp}"
  set +e
  "${ACTIONLINT_BIN}" "${f}" >"${tmp}" 2>&1
  rc=$?
  set -e
  if [[ "${rc}" -eq 0 ]]; then
    continue
  fi

  mapfile -t loc_lines < <(grep -E '^[^:]+:[0-9]+:[0-9]+:' "${tmp}" || true)
  if [[ "${#loc_lines[@]}" -gt 0 ]]; then
    for line in "${loc_lines[@]}"; do
      coord="$(echo "${line}" | cut -d':' -f1-3)"
      echo "WORKFLOW_ACTIONLINT_ERROR=${coord} reason_code=ACTIONLINT_ERROR"
      ERROR_COUNT=$((ERROR_COUNT + 1))
    done
  else
    echo "WORKFLOW_ACTIONLINT_NOLOC=1"
    echo "WORKFLOW_ACTIONLINT_FAIL_FILE=${f}"
    echo "WORKFLOW_ACTIONLINT_RC=${rc}"
    echo "WORKFLOW_ACTIONLINT_ERROR=.github/workflows:0:0 reason_code=ACTIONLINT_NOLOC_FAILURE"
    NOLOC_COUNT=$((NOLOC_COUNT + 1))
    ERROR_COUNT=$((ERROR_COUNT + 1))
  fi
done

if [[ "${ERROR_COUNT}" -eq 0 ]]; then
  echo "WORKFLOW_ACTIONLINT_OK=1"
  echo "WORKFLOW_ACTIONLINT_ERROR_COUNT=0"
else
  echo "WORKFLOW_ACTIONLINT_OK=0"
  echo "WORKFLOW_ACTIONLINT_ERROR_COUNT=${ERROR_COUNT}"
  echo "WORKFLOW_ACTIONLINT_NOLOC_COUNT=${NOLOC_COUNT}"
  exit 1
fi
