#!/usr/bin/env bash
set -euo pipefail

# Ops script: NO *_OK=1 output. Meta/status only.
# Usage examples:
#   bash .../svr03_audit_query.sh --date 2026-01-23
#   bash .../svr03_audit_query.sh --from 2026-01-20 --to 2026-01-23 --reason_code KEY_REVOKED
#   bash .../svr03_audit_query.sh --key_id k1
#   bash .../svr03_audit_query.sh --artifact_sha256 abc123
#   bash .../svr03_audit_query.sh --request_id req-123

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "$ROOT"

DATA_DIR="backend/model_registry/data"
LIMIT="${LIMIT:-200}"

DATE=""
FROM=""
TO=""
REASON_CODE=""
KEY_ID=""
SHA256=""
REQUEST_ID=""

while [[ $# -gt 0 ]]; do
  case "$1" in
    --date) DATE="${2:-}"; shift 2;;
    --from) FROM="${2:-}"; shift 2;;
    --to) TO="${2:-}"; shift 2;;
    --reason_code) REASON_CODE="${2:-}"; shift 2;;
    --key_id) KEY_ID="${2:-}"; shift 2;;
    --artifact_sha256) SHA256="${2:-}"; shift 2;;
    --request_id) REQUEST_ID="${2:-}"; shift 2;;
    --limit) LIMIT="${2:-200}"; shift 2;;
    *) echo "FAIL: unknown arg $1"; exit 2;;
  esac
done

[[ -d "$DATA_DIR" ]] || { echo "FAIL: missing $DATA_DIR"; exit 1; }

# 대상 파일 선택
FILES=()
if [[ -n "$DATE" ]]; then
  # audit_YYYY-MM-DD.json and audit_YYYY-MM-DD.1.json
  while IFS= read -r f; do FILES+=("$f"); done < <(ls -1 "$DATA_DIR"/audit_"$DATE"*.json 2>/dev/null || true)
elif [[ -n "$FROM" && -n "$TO" ]]; then
  # 범위: 간단히 전체 audit_*.json을 대상으로 하고, 날짜 필터는 jq로 적용
  while IFS= read -r f; do FILES+=("$f"); done < <(ls -1 "$DATA_DIR"/audit_*.json 2>/dev/null || true)
else
  # 기본: 최신 3일 정도만 보고 싶으면 --from/--to 사용 권장. 여기서는 전체 대상으로 둠.
  while IFS= read -r f; do FILES+=("$f"); done < <(ls -1 "$DATA_DIR"/audit_*.json 2>/dev/null || true)
fi

if [[ ${#FILES[@]} -eq 0 ]]; then
  echo "status=no_audit_files"
  exit 0
fi

# jq 필터 구성(없으면 fail-closed)
command -v jq >/dev/null 2>&1 || { echo "FAIL: jq not found (install jq)"; exit 1; }

JQ='.'
# date_range는 ts_ms로 필터
if [[ -n "$FROM" && -n "$TO" ]]; then
  FROM_MS="$(python3 - <<PY
from datetime import datetime, timezone
print(int(datetime.fromisoformat("${FROM}T00:00:00+00:00").timestamp()*1000))
PY
)"
  TO_MS="$(python3 - <<PY
from datetime import datetime, timezone
print(int(datetime.fromisoformat("${TO}T23:59:59+00:00").timestamp()*1000))
PY
)"
  JQ="$JQ | map(select(.ts_ms >= $FROM_MS and .ts_ms <= $TO_MS))"
fi

if [[ -n "$REASON_CODE" ]]; then
  JQ="$JQ | map(select(.reason_code == \"$REASON_CODE\"))"
fi
if [[ -n "$KEY_ID" ]]; then
  JQ="$JQ | map(select(.key_id == \"$KEY_ID\"))"
fi
if [[ -n "$SHA256" ]]; then
  JQ="$JQ | map(select(.sha256 == \"$SHA256\"))"
fi
if [[ -n "$REQUEST_ID" ]]; then
  # request_id가 이벤트에 없다면 빈 결과가 정상
  JQ="$JQ | map(select(.request_id == \"$REQUEST_ID\"))"
fi

echo "== SVR03 AUDIT QUERY =="
echo "files=${#FILES[@]} limit=$LIMIT"
echo "date=$DATE from=$FROM to=$TO reason_code=$REASON_CODE key_id=$KEY_ID sha256=$SHA256 request_id=$REQUEST_ID"

# 여러 파일을 합쳐 필터 후, 상한 적용
jq -c '.[ ]' "${FILES[@]}" 2>/dev/null | jq -s "$JQ | .[:$LIMIT]" | jq -c '.[]' | head -n "$LIMIT"

