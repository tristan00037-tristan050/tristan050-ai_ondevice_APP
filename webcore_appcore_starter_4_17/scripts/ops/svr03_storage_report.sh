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
COUNTER_FILE="$DATA_DIR/ops_counters.json"
node - <<NODE
const fs = require('fs');
const path = require('path');
const counterFile = "${COUNTER_FILE}";
if (!fs.existsSync(counterFile)) {
  console.log('LOCK_TIMEOUT_COUNT_24H=0');
  console.log('PERSIST_CORRUPTED_COUNT_24H=0');
  console.log('AUDIT_ROTATE_COUNT_24H=0');
  console.log('AUDIT_RETENTION_DELETES_24H=0');
  process.exit(0);
}
try {
  const data = JSON.parse(fs.readFileSync(counterFile, 'utf8'));
  const now = Date.now();
  const cutoff = now - 24 * 60 * 60 * 1000;
  const counts = {
    LOCK_TIMEOUT: (data.LOCK_TIMEOUT || []).filter((t) => t >= cutoff).length,
    PERSIST_CORRUPTED: (data.PERSIST_CORRUPTED || []).filter((t) => t >= cutoff).length,
    AUDIT_ROTATE: (data.AUDIT_ROTATE || []).filter((t) => t >= cutoff).length,
    AUDIT_RETENTION_DELETE: (data.AUDIT_RETENTION_DELETE || []).filter((t) => t >= cutoff).length,
  };
  console.log(\`LOCK_TIMEOUT_COUNT_24H=\${counts.LOCK_TIMEOUT}\`);
  console.log(\`PERSIST_CORRUPTED_COUNT_24H=\${counts.PERSIST_CORRUPTED}\`);
  console.log(\`AUDIT_ROTATE_COUNT_24H=\${counts.AUDIT_ROTATE}\`);
  console.log(\`AUDIT_RETENTION_DELETES_24H=\${counts.AUDIT_RETENTION_DELETE}\`);
} catch (e) {
  console.log('LOCK_TIMEOUT_COUNT_24H=0');
  console.log('PERSIST_CORRUPTED_COUNT_24H=0');
  console.log('AUDIT_ROTATE_COUNT_24H=0');
  console.log('AUDIT_RETENTION_DELETES_24H=0');
}
NODE

