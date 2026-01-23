#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "$ROOT"

DATA_DIR="backend/model_registry/data"
echo "== SVR-03 STORAGE REPORT =="
date -Is
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
ls -lh "$DATA_DIR"/audit_log*.json 2>/dev/null || echo "no audit logs"

