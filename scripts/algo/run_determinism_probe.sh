#!/usr/bin/env bash
set -euo pipefail

MODE="${1:?MODE required}"
SEED="${2:?SEED required}"

# D0 gate: 실제 알고리즘 출력(3블록 JSON)을 생성하고 그 결과를 sha256로 해시한다.
# 입력은 meta-only fixture를 사용한다(원문 금지).
REQ="scripts/algo_core/sample_meta_request.json"
GEN="scripts/algo_core/generate_three_blocks.mjs"

test -s "$REQ" || { echo "BLOCK: missing $REQ"; exit 1; }
test -s "$GEN" || { echo "BLOCK: missing $GEN"; exit 1; }
command -v node >/dev/null 2>&1 || { echo "BLOCK: node missing"; exit 1; }

OUT_JSON="$(mktemp -t determinism_out_XXXXXX.json 2>/dev/null || mktemp /tmp/determinism_out_XXXXXX.json)"
rm -f "$OUT_JSON"

# 실행(메타-only 3블록 생성)
node "$GEN" "$REQ" "$OUT_JSON" >/dev/null

test -s "$OUT_JSON" || { echo "BLOCK: output json missing/empty"; rm -f "$OUT_JSON"; exit 1; }

# meta-only 출력 계약
echo "DETERMINISM_MODE=${MODE}"

# 실제 출력(JSON)의 sha256
sha256sum "$OUT_JSON" | awk '{print "DETERMINISM_SHA256="$1}'

rm -f "$OUT_JSON"
