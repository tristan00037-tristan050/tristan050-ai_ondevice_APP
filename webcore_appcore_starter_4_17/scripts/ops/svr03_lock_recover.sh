#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "$ROOT"

LOCK_STALE_AFTER_MS="${LOCK_STALE_AFTER_MS:-600000}" # default 10m
FORCE=0
if [[ "${1:-}" == "--force" ]]; then FORCE=1; fi

DATA_DIR="backend/model_registry/data"
LOCK_NAME="persist_store"
LOCK_FILE="${DATA_DIR}/${LOCK_NAME}.lock"

ts() { python3 - <<'PY'
from datetime import datetime, timezone
print(datetime.now(timezone.utc).isoformat())
PY
}

echo "== SVR03 LOCK RECOVER =="
echo "NOW_UTC=$(ts)"
echo "LOCK_FILE=$LOCK_FILE"
echo "LOCK_STALE_AFTER_MS=$LOCK_STALE_AFTER_MS"
echo "FORCE=$FORCE"

if [[ ! -f "$LOCK_FILE" ]]; then
  echo "status=absent"
  exit 0
fi

META="$(cat "$LOCK_FILE" || true)"
echo "lock_meta=$(echo "$META" | tr -d '\n' | head -c 4000)"

CREATED_MS="$(python3 - <<PY
import json
import datetime
import sys

try:
    with open("$LOCK_FILE", "r", encoding="utf-8") as f:
        meta = json.load(f)
    s = meta.get("created_at_utc")
    if not s:
        print("UNKNOWN")
        sys.exit(0)
    # Handle both Z and +00:00 formats
    s_clean = s.replace("Z", "+00:00")
    if "+" not in s_clean and s_clean.endswith("UTC"):
        s_clean = s_clean.replace("UTC", "+00:00")
    dt = datetime.datetime.fromisoformat(s_clean)
    print(int(dt.timestamp() * 1000))
except Exception:
    print("UNKNOWN")
PY
)"

if [[ "$CREATED_MS" == "UNKNOWN" ]]; then
  echo "BLOCK: ambiguous lock meta (created_at_utc missing/invalid)"
  exit 1
fi

NOW_MS="$(python3 - <<'PY'
from datetime import datetime, timezone
print(int(datetime.now(timezone.utc).timestamp()*1000))
PY
)"
AGE_MS="$((NOW_MS - CREATED_MS))"
echo "age_ms=$AGE_MS"

PID="$(python3 - <<PY
import json
import sys

try:
    with open("$LOCK_FILE", "r", encoding="utf-8") as f:
        meta = json.load(f)
    pid = meta.get("pid")
    print(pid if pid is not None else "UNKNOWN")
except Exception:
    print("UNKNOWN")
PY
)"

if [[ "$PID" == "UNKNOWN" ]]; then
  echo "BLOCK: ambiguous pid"
  exit 1
fi

PID_ALIVE=0
if ps -p "$PID" >/dev/null 2>&1; then PID_ALIVE=1; fi
echo "pid=$PID pid_alive=$PID_ALIVE"

STALE=0
if [[ "$AGE_MS" -gt "$LOCK_STALE_AFTER_MS" && "$PID_ALIVE" -eq 0 ]]; then STALE=1; fi
echo "stale=$STALE"

if [[ "$STALE" -eq 0 && "$FORCE" -eq 0 ]]; then
  echo "BLOCK: non-stale lock (use --force only with explicit incident process)"
  exit 1
fi

  rm -f "$LOCK_FILE"
  echo "cleared=1"

  # FORCE 감사(meta-only): lock 강제 삭제가 실행된 경우만 기록
  if [[ "$FORCE" -eq 1 ]]; then
    cd "$ROOT/webcore_appcore_starter_4_17/backend/model_registry"
    REPO_SHA="${REPO_SHA:-unknown}" node - <<'NODE'
const { appendAuditV2, hashActorId, newEventId, nowUtcIso } = require("./services/audit_append");

const repoSha = process.env.REPO_SHA || "unknown";
appendAuditV2({
  v: 2,
  ts_utc: nowUtcIso(),
  event_id: newEventId("LOCK_FORCE_CLEAR"),
  actor_type: "system",
  actor_id_hash: hashActorId(process.env.USER || "unknown"),
  action: "LOCK_FORCE_CLEAR",
  reason_code: "FORCED_RECOVERY",
  repo_sha: repoSha,
  target: { lock_name: "persist_store" },
  outcome: "ALLOW",
  policy_version: "h3.2",
});
NODE
  fi

