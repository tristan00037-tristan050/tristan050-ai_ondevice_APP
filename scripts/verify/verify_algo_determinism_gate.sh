#!/usr/bin/env bash
set -euo pipefail

ALGO_DETERMINISM_VERIFIED_OK=0
ALGO_DETERMINISM_HASH_MATCH_OK=0
ALGO_DETERMINISM_MODE_REPORTED_OK=0

cleanup() {
  echo "ALGO_DETERMINISM_VERIFIED_OK=${ALGO_DETERMINISM_VERIFIED_OK}"
  echo "ALGO_DETERMINISM_HASH_MATCH_OK=${ALGO_DETERMINISM_HASH_MATCH_OK}"
  echo "ALGO_DETERMINISM_MODE_REPORTED_OK=${ALGO_DETERMINISM_MODE_REPORTED_OK}"

  if [[ "${ALGO_DETERMINISM_VERIFIED_OK}" == "1" ]] && \
     [[ "${ALGO_DETERMINISM_HASH_MATCH_OK}" == "1" ]] && \
     [[ "${ALGO_DETERMINISM_MODE_REPORTED_OK}" == "1" ]]; then
    exit 0
  fi
  exit 1
}
trap cleanup EXIT

ROOT="$(git rev-parse --show-toplevel)"
cd "$ROOT"

POLICY="docs/ops/contracts/ALGO_DETERMINISM_POLICY_V1.md"
test -s "$POLICY" || { echo "BLOCK: missing $POLICY"; exit 1; }

MODE="$(grep -nE '^MODE=' "$POLICY" | tail -n 1 | cut -d= -f2 | tr -d '[:space:]')"
SEED="$(grep -nE '^SEED=' "$POLICY" | tail -n 1 | cut -d= -f2 | tr -d '[:space:]')"
test -n "$MODE" || { echo "BLOCK: MODE missing"; exit 1; }
test -n "$SEED" || { echo "BLOCK: SEED missing"; exit 1; }

# TODO: 알고리즘 실행 엔트리가 확정되면 아래 RUN_CMD를 실제 커맨드로 치환.
# 현재는 fail-closed로 "엔트리 미존재"를 BLOCK 처리해, 게이트가 무력화되지 않게 한다.
RUN_ENTRY="scripts/algo/run_determinism_probe.sh"
if [[ ! -x "$RUN_ENTRY" ]]; then
  echo "BLOCK: determinism runner missing ($RUN_ENTRY). Provide in follow-up PR."
  exit 1
fi

# runner는 meta-only 출력만 해야 한다.
# expected output:
#   DETERMINISM_MODE=<MODE>
#   DETERMINISM_SHA256=<hex>
OUT="$("$RUN_ENTRY" "$MODE" "$SEED" 2>&1)" || { echo "BLOCK: runner failed"; echo "$OUT"; exit 1; }

M_LINE="$(echo "$OUT" | grep -m1 -nE '^DETERMINISM_MODE=' || true)"
S_LINE="$(echo "$OUT" | grep -m1 -nE '^DETERMINISM_SHA256=' || true)"
test -n "$M_LINE" || { echo "BLOCK: missing DETERMINISM_MODE"; echo "$OUT"; exit 1; }
test -n "$S_LINE" || { echo "BLOCK: missing DETERMINISM_SHA256"; echo "$OUT"; exit 1; }

M_VAL="$(echo "$OUT" | sed -nE 's/^DETERMINISM_MODE=//p' | head -n 1)"
S_VAL="$(echo "$OUT" | sed -nE 's/^DETERMINISM_SHA256=//p' | head -n 1)"

test "$M_VAL" = "$MODE" || { echo "BLOCK: mode mismatch ($M_VAL != $MODE)"; exit 1; }
echo "$S_VAL" | grep -qE '^[0-9a-f]{64}$' || { echo "BLOCK: bad sha256"; exit 1; }

# D0: 같은 입력을 2회 실행해 해시가 완전 동일해야 한다.
OUT2="$("$RUN_ENTRY" "$MODE" "$SEED" 2>&1)" || { echo "BLOCK: runner failed (2nd)"; echo "$OUT2"; exit 1; }
S2="$(echo "$OUT2" | sed -nE 's/^DETERMINISM_SHA256=//p' | head -n 1)"

test "$S2" = "$S_VAL" || { echo "BLOCK: hash mismatch (non-deterministic)"; exit 1; }

ALGO_DETERMINISM_VERIFIED_OK=1
ALGO_DETERMINISM_MODE_REPORTED_OK=1
ALGO_DETERMINISM_HASH_MATCH_OK=1
exit 0

