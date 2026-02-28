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

# 금지 "키"만 검사(값 "id":"stack" 등 오탐 방지); payload 필드 값 내 예외 패턴은 별도
deny_key_re='"(exception_message|traceback|stack|stderr_dump|raw_output)"[[:space:]]*:'
deny_payload_re='"(error|stderr|message|error_message)"[[:space:]]*:[[:space:]]*"[^"]*(Traceback|Exception:| at [^"]+:[0-9]+)'

for f in "${files[@]}"; do
  # 1) 금지 "키"만 검사(값 매칭 금지)
  if grep -Eqs "$deny_key_re" "$f"; then
    echo "ERROR_CODE=DENY_KEY_FOUND"
    exit 1
  fi
  # 2) 금지 "패턴"은 payload 키 값에만 제한(오탐 방지)
  if grep -Eqs "$deny_payload_re" "$f"; then
    echo "ERROR_CODE=DENY_PATTERN_FOUND"
    exit 1
  fi
done

EXEC_MODE_PER_LINE_NO_EXCEPTION_TEXT_OK=1
exit 0
