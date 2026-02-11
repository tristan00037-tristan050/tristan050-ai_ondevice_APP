#!/usr/bin/env bash
set -euo pipefail

mkdir -p ai/reports/latest
OUT="ai/reports/latest/metrics.json"

python3 - <<'PY'
import json, datetime
data = {
  "date": datetime.datetime.now(datetime.timezone.utc).isoformat(),
  "task": "minieval_placeholder",
  "quality": {"metric_name": "accuracy_placeholder", "value": 0.0},
  "latency_ms": {"p50": 0, "p95": 0},
  "note": "placeholder metrics; replace with real eval later"
}
with open("ai/reports/latest/metrics.json", "w", encoding="utf-8") as f:
  json.dump(data, f, ensure_ascii=False, indent=2)
print("OK: wrote ai/reports/latest/metrics.json")
PY
