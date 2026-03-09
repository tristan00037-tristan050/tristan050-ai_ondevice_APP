#!/usr/bin/env bash
set -euo pipefail

# P23-P2-01: run_sustained_perf_test_v1.sh
# 10분 지속 추론 성능 테스트 스크립트.
# real weights 투입 후 실제 측정값으로 SUSTAINED_PERF_GATE_V1.json 업데이트.
#
# 사용법:
#   PACK_ID=micro_default bash scripts/ops/run_sustained_perf_test_v1.sh
#
# 측정 항목:
#   latency_p95_ms     : 시작 시점 vs 10분 후 p95 레이턴시
#   decode_tps         : 10분 지속 시 decode throughput (tokens/sec)
#   thermal_headroom   : 10분 경과 시점의 thermal headroom
#   rss_peak_mb        : 테스트 중 최대 RSS (MB)

ROOT="$(git rev-parse --show-toplevel)"
cd "$ROOT"

PACK_ID="${PACK_ID:-}"
[[ -n "$PACK_ID" ]] || { echo "ERROR_CODE=PACK_ID_REQUIRED"; echo "Usage: PACK_ID=<pack_id> $0"; exit 1; }

GATE_FILE="docs/ops/contracts/SUSTAINED_PERF_GATE_V1.json"
[[ -f "$GATE_FILE" ]] || { echo "ERROR_CODE=SUSTAINED_PERF_GATE_MISSING"; echo "HIT_PATH=$GATE_FILE"; exit 1; }

OUTPUT_DIR="docs/ops/reports"
OUTPUT_FILE="${OUTPUT_DIR}/sustained_perf_latest.json"

PYTHON_BIN="python3"
command -v "$PYTHON_BIN" >/dev/null 2>&1 || PYTHON_BIN="python"
command -v "$PYTHON_BIN" >/dev/null 2>&1 || { echo "ERROR_CODE=PYTHON_UNAVAILABLE"; exit 1; }

# real weights가 없으면 pending_real_weights 상태 유지 후 종료
MANIFEST="packs/${PACK_ID}/manifest.json"
[[ -f "$MANIFEST" ]] || { echo "ERROR_CODE=PACK_MANIFEST_MISSING"; echo "HIT_PATH=$MANIFEST"; exit 1; }

STATUS="$("$PYTHON_BIN" -c "import json; d=json.load(open('$MANIFEST')); print(d.get('logical_model_pack', d).get('status', 'unknown'))")"

if [ "$STATUS" = "pending_real_weights" ]; then
  echo "STATUS=pending_real_weights"
  echo "NOTE=Sustained perf test requires real weights. Skipping measurement."
  "$PYTHON_BIN" - "$OUTPUT_FILE" "$PACK_ID" <<'PYEOF'
import json, sys, datetime

output_path, pack_id = sys.argv[1], sys.argv[2]

result = {
    "schema_version": 1,
    "pack_id": pack_id,
    "generated_at_utc": datetime.datetime.utcnow().isoformat() + "Z",
    "status": "pending_real_weights",
    "test_duration_minutes": 10,
    "latency_p95_start_ms": None,
    "latency_p95_end_ms": None,
    "latency_p95_degradation_pct": None,
    "decode_tps": None,
    "decode_tps_degradation_pct": None,
    "thermal_headroom_sustained": None,
    "rss_peak_mb": None,
    "rss_growth_pct": None,
    "passed": None,
    "note": "real weights 투입 후 재실행 필요"
}

import os
os.makedirs(os.path.dirname(output_path), exist_ok=True) if os.path.dirname(output_path) else None
with open(output_path, 'w', encoding='utf-8') as f:
    json.dump(result, f, indent=2, ensure_ascii=False)
    f.write('\n')

print(f"OUTPUT={output_path}")
PYEOF
  exit 0
fi

echo "NOTE=Real weights detected. Implement actual inference loop here."
echo "STATUS=not_implemented"
exit 1
