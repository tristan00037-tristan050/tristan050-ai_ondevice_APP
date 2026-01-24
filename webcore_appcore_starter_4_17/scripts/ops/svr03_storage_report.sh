#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "$ROOT"

DATA_DIR="backend/model_registry/data"
echo "== SVR-03 STORAGE REPORT =="
# timestamp (portable: Linux/macOS)
ts() {
  if command -v python3 >/dev/null 2>&1; then
    python3 - <<'PY'
from datetime import datetime, timezone
print(datetime.now(timezone.utc).isoformat())
PY
  else
    date
  fi
}
ts
echo "DIR=$DATA_DIR"

if [[ ! -d "$DATA_DIR" ]]; then
  echo "FAIL: missing $DATA_DIR"
  exit 1
fi

echo "== files =="
ls -lh "$DATA_DIR" || true

echo "== total size =="
du -sh "$DATA_DIR" || true

echo "== largest 10 =="
ls -lhS "$DATA_DIR" | head -n 11 || true

echo "== audit rotate status =="
# Check for daily audit logs
ls -lh "$DATA_DIR"/audit_*-*-*.json "$DATA_DIR"/audit_*-*-*.1.json 2>/dev/null || echo "no audit logs"

echo "== ops counters (24h) =="
cd "$ROOT"
node - <<'NODE'
const { readCounts24h } = require("./packages/common/src/metrics/counters.cjs");

const counts = readCounts24h();
console.log(`LOCK_TIMEOUT_COUNT_24H=${counts.LOCK_TIMEOUT}`);
console.log(`PERSIST_CORRUPTED_COUNT_24H=${counts.PERSIST_CORRUPTED}`);
console.log(`AUDIT_ROTATE_COUNT_24H=${counts.AUDIT_ROTATE}`);
console.log(`AUDIT_RETENTION_DELETES_24H=${counts.AUDIT_RETENTION_DELETE}`);
NODE

