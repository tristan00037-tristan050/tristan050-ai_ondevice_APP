#!/usr/bin/env bash
set -euo pipefail

BFF_SECRET_SCHEMA_V1_OK=0
BFF_SECRET_EMPTY_STRING_BLOCK_OK=0
BFF_SECRET_FORMAT_OK=0

finish() {
  echo "BFF_SECRET_SCHEMA_V1_OK=${BFF_SECRET_SCHEMA_V1_OK}"
  echo "BFF_SECRET_EMPTY_STRING_BLOCK_OK=${BFF_SECRET_EMPTY_STRING_BLOCK_OK}"
  echo "BFF_SECRET_FORMAT_OK=${BFF_SECRET_FORMAT_OK}"
}
trap finish EXIT

# meta-only: 값 출력 금지
REQ_DATABASE_URL="${DATABASE_URL:-}"
REQ_EXPORT_SIGN_SECRET="${EXPORT_SIGN_SECRET:-}"

# trim (whitespace-only는 empty로 취급)
DB_TRIM="$(printf '%s' "$REQ_DATABASE_URL" | sed -E 's/^[[:space:]]+//; s/[[:space:]]+$//')"
SIGN_TRIM="$(printf '%s' "$REQ_EXPORT_SIGN_SECRET" | sed -E 's/^[[:space:]]+//; s/[[:space:]]+$//')"

# 1) 존재/빈 값 차단 (trim 후)
if [ -z "$DB_TRIM" ] || [ -z "$SIGN_TRIM" ]; then
  echo "ERROR_CODE=SECRET_MISSING_OR_EMPTY"
  exit 1
fi
BFF_SECRET_EMPTY_STRING_BLOCK_OK=1
BFF_SECRET_SCHEMA_V1_OK=1

# 2) DATABASE_URL 형식 검사(접두만 금지, authority·경로 필수)
# 허용 최소: postgres(s)://<host>[:port]/<db>
if ! printf '%s' "$DB_TRIM" | grep -Eq '^(postgres|postgresql)://([^/@]+@)?[^/:]+(:[0-9]+)?/.+'; then
  echo "ERROR_CODE=DATABASE_URL_FORMAT_INVALID"
  exit 1
fi

# 3) EXPORT_SIGN_SECRET 길이 검사(trim 후)
if [ "${#SIGN_TRIM}" -lt 16 ]; then
  echo "ERROR_CODE=EXPORT_SIGN_SECRET_TOO_SHORT"
  exit 1
fi

BFF_SECRET_FORMAT_OK=1
exit 0
