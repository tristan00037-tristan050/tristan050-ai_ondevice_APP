#!/usr/bin/env bash
set -euo pipefail

TASK_QUEUE_IDEMPOTENCY_OK=0
TASK_QUEUE_CONCURRENCY_OK=0
TASK_QUEUE_PARTIAL_WRITE_0_OK=0
TASK_QUEUE_LOCK_NO_TIMEOUT_OK=0
TASK_QUEUE_ASYNC_TASK_FN_OK=0

cleanup() {
  echo "TASK_QUEUE_IDEMPOTENCY_OK=${TASK_QUEUE_IDEMPOTENCY_OK}"
  echo "TASK_QUEUE_CONCURRENCY_OK=${TASK_QUEUE_CONCURRENCY_OK}"
  echo "TASK_QUEUE_PARTIAL_WRITE_0_OK=${TASK_QUEUE_PARTIAL_WRITE_0_OK}"
  echo "TASK_QUEUE_LOCK_NO_TIMEOUT_OK=${TASK_QUEUE_LOCK_NO_TIMEOUT_OK}"
  echo "TASK_QUEUE_ASYNC_TASK_FN_OK=${TASK_QUEUE_ASYNC_TASK_FN_OK}"

  if [[ "$TASK_QUEUE_IDEMPOTENCY_OK" == "1" ]] && \
     [[ "$TASK_QUEUE_CONCURRENCY_OK" == "1" ]] && \
     [[ "$TASK_QUEUE_PARTIAL_WRITE_0_OK" == "1" ]] && \
     [[ "$TASK_QUEUE_LOCK_NO_TIMEOUT_OK" == "1" ]] && \
     [[ "$TASK_QUEUE_ASYNC_TASK_FN_OK" == "1" ]]; then
    exit 0
  fi
  exit 1
}
trap cleanup EXIT

ROOT="$(git rev-parse --show-toplevel)"
cd "$ROOT"

# Policy document check
doc="docs/ops/contracts/TASK_QUEUE_POLICY_V1.md"
[ -f "$doc" ] || { echo "BLOCK: missing $doc"; exit 1; }
grep -q "TASK_QUEUE_POLICY_V1_TOKEN=1" "$doc" || { echo "BLOCK: missing policy token"; exit 1; }

command -v node >/dev/null 2>&1 || { echo "BLOCK: node not found"; exit 1; }

OUT="$(node scripts/agent/task_queue_selftest_v1.cjs 2>&1)" || { echo "BLOCK: task queue selftest failed"; echo "$OUT"; exit 1; }

echo "$OUT" | grep -nE '^TASK_QUEUE_IDEMPOTENCY_OK=1$' >/dev/null || exit 1
TASK_QUEUE_IDEMPOTENCY_OK=1

echo "$OUT" | grep -nE '^TASK_QUEUE_CONCURRENCY_OK=1$' >/dev/null || exit 1
TASK_QUEUE_CONCURRENCY_OK=1

echo "$OUT" | grep -nE '^TASK_QUEUE_PARTIAL_WRITE_0_OK=1$' >/dev/null || exit 1
TASK_QUEUE_PARTIAL_WRITE_0_OK=1

echo "$OUT" | grep -nE '^TASK_QUEUE_LOCK_NO_TIMEOUT_OK=1$' >/dev/null || exit 1
TASK_QUEUE_LOCK_NO_TIMEOUT_OK=1

echo "$OUT" | grep -nE '^TASK_QUEUE_ASYNC_TASK_FN_OK=1$' >/dev/null || exit 1
TASK_QUEUE_ASYNC_TASK_FN_OK=1

exit 0

