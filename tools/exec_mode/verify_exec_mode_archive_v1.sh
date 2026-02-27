#!/usr/bin/env bash
set -euo pipefail

ENGINE=""
UTC_DATE=""

usage() {
  echo "Usage: $0 --engine <engine> --utc-date <YYYY-MM-DD>"
  exit 2
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --engine) ENGINE="${2:-}"; shift 2;;
    --utc-date) UTC_DATE="${2:-}"; shift 2;;
    *) usage;;
  esac
done

[[ -n "$ENGINE" && -n "$UTC_DATE" ]] || usage

OUTPUT_ROOT="${EXEC_MODE_OUTPUT_ROOT:-docs}"
DIR="$OUTPUT_ROOT/EXEC_MODE_RUNS/${UTC_DATE}"
[[ -d "$DIR" ]] || { echo "BLOCK: archive dir missing: $DIR" >&2; exit 1; }

# 구 형식(<engine>.md) 금지
if [[ -f "$DIR/${ENGINE}.md" ]]; then
  echo "BLOCK: legacy archive filename exists (must not): $DIR/${ENGINE}.md" >&2
  exit 1
fi

# 신 형식 최소 1개 존재
CNT="$(find "$DIR" -maxdepth 1 -type f -name "${ENGINE}__*.md" | wc -l | tr -d ' ')"
if [[ "$CNT" -lt 1 ]]; then
  echo "BLOCK: no per-run archives found: ${DIR}/${ENGINE}__*.md" >&2
  exit 1
fi

# 파일명 규약 검사: __HHMMSSffffff (12 digits)
BAD="$(find "$DIR" -maxdepth 1 -type f -name "${ENGINE}__*.md" \
  | sed -E 's#.*/##' \
  | grep -vE "^${ENGINE}__[0-9]{12}\.md$" || true)"
if [[ -n "$BAD" ]]; then
  echo "BLOCK: invalid archive filename(s):" >&2
  echo "$BAD" >&2
  exit 1
fi

# 내용 규약(필수 키) 최소 확인
ONE="$(find "$DIR" -maxdepth 1 -type f -name "${ENGINE}__*.md" | head -n 1)"
grep -q "EXEC_MODE_RUN_ARCHIVE_V1" "$ONE" || { echo "BLOCK: missing header in $ONE" >&2; exit 1; }
grep -q "utc_date:" "$ONE" || { echo "BLOCK: missing utc_date in $ONE" >&2; exit 1; }
grep -q "engine:" "$ONE" || { echo "BLOCK: missing engine in $ONE" >&2; exit 1; }
grep -q "inputs:" "$ONE" || { echo "BLOCK: missing inputs in $ONE" >&2; exit 1; }
grep -q "outputs:" "$ONE" || { echo "BLOCK: missing outputs in $ONE" >&2; exit 1; }
grep -q "tokens_out_supported:" "$ONE" || { echo "BLOCK: missing tokens_out_supported in $ONE" >&2; exit 1; }

echo "EXEC_MODE_ARCHIVE_V1_OK=1"
