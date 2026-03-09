#!/usr/bin/env bash
set -euo pipefail

# P23-P0B-02: gen_smoke_fingerprint_v1.sh
# 고정 테스트 입력의 sha256 → input_digest
# 실제 추론 결과의 sha256 → output_digest (real weights 없으면 PLACEHOLDER 유지)
# status: pending_real_weights 유지 (실 weights 없으면 실행 불가)
#
# 사용법:
#   PACK_ID=micro_default bash scripts/ops/gen_smoke_fingerprint_v1.sh
#   PACK_ID=small_default bash scripts/ops/gen_smoke_fingerprint_v1.sh

ROOT="$(git rev-parse --show-toplevel)"
cd "$ROOT"

PACK_ID="${PACK_ID:-}"
[[ -n "$PACK_ID" ]] || { echo "ERROR_CODE=PACK_ID_REQUIRED"; echo "Usage: PACK_ID=<pack_id> $0"; exit 1; }

SMOKE_JSON="packs/${PACK_ID}/smoke_fingerprint.json"
[[ -f "$SMOKE_JSON" ]] || { echo "ERROR_CODE=SMOKE_FINGERPRINT_MISSING"; echo "HIT_PATH=$SMOKE_JSON"; exit 1; }

PYTHON_BIN="python3"
command -v "$PYTHON_BIN" >/dev/null 2>&1 || PYTHON_BIN="python"
command -v "$PYTHON_BIN" >/dev/null 2>&1 || { echo "ERROR_CODE=PYTHON_UNAVAILABLE"; exit 1; }

# 고정 smoke test 입력 문자열 (pack별로 동일한 기준 입력)
SMOKE_INPUT="smoke_test_input_v1:${PACK_ID}:context=hello world"

INPUT_DIGEST="$("$PYTHON_BIN" -c "import hashlib, sys; print(hashlib.sha256(sys.argv[1].encode('utf-8')).hexdigest())" "$SMOKE_INPUT")"

# real weights가 없으면 output_digest는 PLACEHOLDER 유지
# real weights 투입 후 실제 추론 결과로 대체되어야 함
STATUS="pending_real_weights"
OUTPUT_DIGEST="COMPUTED_AT_PACK_BUILD_TIME"

"$PYTHON_BIN" - "$SMOKE_JSON" "$PACK_ID" "$INPUT_DIGEST" "$OUTPUT_DIGEST" "$STATUS" <<'PYEOF'
import json, sys

smoke_path, pack_id, input_digest, output_digest, status = sys.argv[1], sys.argv[2], sys.argv[3], sys.argv[4], sys.argv[5]

with open(smoke_path, 'r', encoding='utf-8') as f:
    doc = json.load(f)

doc["pack_id"] = pack_id
doc["input_digest"] = input_digest
doc["output_digest"] = output_digest
doc["status"] = status
doc["is_deterministic"] = None
doc["fingerprint_version"] = "smoke_v1"
doc["note"] = "real weights 투입 후 scripts/ops/gen_smoke_fingerprint_v1.sh 실행으로 채워짐"

with open(smoke_path, 'w', encoding='utf-8') as f:
    json.dump(doc, f, indent=2, ensure_ascii=False)
    f.write('\n')

print(f"GEN_SMOKE_FINGERPRINT_V1_OK=1")
print(f"PACK={pack_id}")
print(f"INPUT_DIGEST={input_digest}")
print(f"OUTPUT_DIGEST={output_digest}")
print(f"STATUS={status}")
PYEOF

echo "NOTE=output_digest remains PLACEHOLDER until real weights are available"
