#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "$ROOT"

DATA_DIR="backend/model_registry/data"
LOCK_NAME="persist_store"
LOCK_FILE="${DATA_DIR}/${LOCK_NAME}.lock"

ts() { python3 - <<'PY'
from datetime import datetime, timezone
print(datetime.now(timezone.utc).isoformat())
PY
}

echo "== SVR03 LOCK REPORT =="
echo "NOW_UTC=$(ts)"
echo "LOCK_FILE=$LOCK_FILE"

if [[ ! -f "$LOCK_FILE" ]]; then
  echo "status=absent"
  exit 0
fi

echo "status=present"
echo "lock_meta=$(cat "$LOCK_FILE" | tr -d '\n' | head -c 4000)"

