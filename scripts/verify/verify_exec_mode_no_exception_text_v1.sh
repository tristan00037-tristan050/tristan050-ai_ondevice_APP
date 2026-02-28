#!/usr/bin/env bash
set -euo pipefail

EXEC_MODE_PER_LINE_NO_EXCEPTION_TEXT_OK=0
finish() { echo "EXEC_MODE_PER_LINE_NO_EXCEPTION_TEXT_OK=${EXEC_MODE_PER_LINE_NO_EXCEPTION_TEXT_OK}"; }
trap finish EXIT

OUT_ROOT="${OUT_ROOT:-out}"

# out 아래 result.jsonl 전수 검사(없으면 skip; 있으면 예외 텍스트 있으면 fail-closed)
list="$(find "$OUT_ROOT" -type f -name "result.jsonl" 2>/dev/null | sort || true)"
[[ -z "$list" ]] && exit 0
files=()
while IFS= read -r f; do [[ -n "$f" ]] && files+=("$f"); done <<< "$list"

# 금지 키/패턴(최소 세트, 오탐 최소화)
deny_keys='("exception_message"|"traceback"|"stack"|"stderr_dump"|"raw_output")'
deny_patterns='(Traceback|Exception:| at [^"]+:[0-9]+)'

for f in "${files[@]}"; do
  if grep -Eqs "$deny_keys" "$f"; then
    echo "ERROR_CODE=DENY_KEY_FOUND"
    exit 1
  fi
  if grep -Eqs "$deny_patterns" "$f"; then
    echo "ERROR_CODE=DENY_PATTERN_FOUND"
    exit 1
  fi
done

EXEC_MODE_PER_LINE_NO_EXCEPTION_TEXT_OK=1
exit 0
