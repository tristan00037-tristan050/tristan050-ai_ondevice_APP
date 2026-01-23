#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "$ROOT"

echo "== SVR-03 SMOKE START =="
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

echo "== 1) verify (must PASS) =="
bash scripts/verify/verify_svr03_model_registry.sh ; echo "EXIT=$?"

echo "== 2) data dir exists =="
DATA_DIR="backend/model_registry/data"
test -d "$DATA_DIR" && ls -lh "$DATA_DIR" || { echo "FAIL: missing $DATA_DIR"; exit 1; }

echo "== 3) audit log exists (or rotated) =="
ls -lh "$DATA_DIR"/audit_log*.json 2>/dev/null || echo "WARN: audit log not found yet (no events recorded)"

echo "== 4) corruption guard sanity (should not crash on normal files) =="
# 읽기 실패가 발생하면 persist_read가 PERSIST_CORRUPTED로 fail-closed 되어야 함
# 여기서는 정상 파일 목록만 확인
for f in "$DATA_DIR"/*.json; do
  [[ -f "$f" ]] || continue
  node -e "JSON.parse(require('fs').readFileSync('$f','utf8'))" >/dev/null
done
echo "OK: json parse sanity"

echo "== SVR-03 SMOKE DONE =="

