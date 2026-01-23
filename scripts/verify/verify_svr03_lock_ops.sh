#!/usr/bin/env bash
set -euo pipefail

SVR03_LOCK_STALE_DETECTED_OK=0
SVR03_LOCK_CLEARED_OK=0
SVR03_LOCK_CLEAR_BLOCK_OK=0

cleanup() {
  echo "SVR03_LOCK_STALE_DETECTED_OK=${SVR03_LOCK_STALE_DETECTED_OK}"
  echo "SVR03_LOCK_CLEARED_OK=${SVR03_LOCK_CLEARED_OK}"
  echo "SVR03_LOCK_CLEAR_BLOCK_OK=${SVR03_LOCK_CLEAR_BLOCK_OK}"
}
trap cleanup EXIT

DATA_DIR="webcore_appcore_starter_4_17/backend/model_registry/data"
mkdir -p "$DATA_DIR"
LOCK_FILE="${DATA_DIR}/persist_store.lock"

# stale 케이스: 오래된 created_at + 존재하지 않는 pid
python3 - <<'PY'
import json,os,datetime
data_dir="webcore_appcore_starter_4_17/backend/model_registry/data"
lock_file=os.path.join(data_dir,"persist_store.lock")
meta={
  "pid": 999999,
  "host": "verify-host",
  "created_at_utc": (datetime.datetime.now(datetime.timezone.utc)-datetime.timedelta(days=1)).isoformat(),
  "repo_sha": "verify"
}
with open(lock_file,"w",encoding="utf-8") as f:
  json.dump(meta,f)
PY

if LOCK_STALE_AFTER_MS=1 bash webcore_appcore_starter_4_17/scripts/ops/svr03_lock_recover.sh >/tmp/lock_recover_out.txt 2>&1; then
  SVR03_LOCK_STALE_DETECTED_OK=1
  SVR03_LOCK_CLEARED_OK=1
else
  cat /tmp/lock_recover_out.txt || true
  exit 1
fi

# non-stale 케이스: 현재 pid + 현재 시간 (복구 차단되어야 함)
python3 - <<'PY'
import json,os,datetime
data_dir="webcore_appcore_starter_4_17/backend/model_registry/data"
lock_file=os.path.join(data_dir,"persist_store.lock")
meta={
  "pid": os.getpid(),
  "host": "verify-host",
  "created_at_utc": datetime.datetime.now(datetime.timezone.utc).isoformat(),
  "repo_sha": "verify"
}
with open(lock_file,"w",encoding="utf-8") as f:
  json.dump(meta,f)
PY

set +e
LOCK_STALE_AFTER_MS=999999 bash webcore_appcore_starter_4_17/scripts/ops/svr03_lock_recover.sh >/tmp/lock_block_out.txt 2>&1
rc=$?
set -e
if [[ $rc -eq 0 ]]; then
  cat /tmp/lock_block_out.txt || true
  exit 1
fi
SVR03_LOCK_CLEAR_BLOCK_OK=1

exit 0

