#!/usr/bin/env bash
# collect_data.sh — fail-closed 수집 + verifier 통과 후에만 COLLECT_DATA_OK=1
# 1) SYNTHETIC_COUNT >= 3 사전 BLOCK
# 2) collect_data_impl_v1.py (strict JSONL + non-empty split)
# 3) verify_cross_split_duplicate_v1.py
# 4) 위 단계 모두 통과 시에만 COLLECT_DATA_OK=1 출력
set -euo pipefail

ROOT="$(git rev-parse --show-toplevel 2>/dev/null || true)"
ROOT="${ROOT:-.}"
cd "$ROOT"

PYTHON_BIN="python3"
command -v "$PYTHON_BIN" >/dev/null 2>&1 || PYTHON_BIN="python"
command -v "$PYTHON_BIN" >/dev/null 2>&1 || { echo "ERROR_CODE=PYTHON_UNAVAILABLE"; exit 1; }

SYNTHETIC_COUNT="${SYNTHETIC_COUNT:-3}"
if [ "$SYNTHETIC_COUNT" -lt 3 ]; then
  echo "BLOCK: SYNTHETIC_COUNT must be >= 3 to produce non-empty train/validation/test"
  exit 1
fi

OUT_DIR="${COLLECT_OUT_DIR:-data/collected}"
WIKI_PATH="${COLLECT_WIKI_PATH:-}"
DIALOGUE_PATH="${COLLECT_DIALOGUE_PATH:-}"

RUN_IMPL=0
IMPL_ARGS=("--out-dir" "$OUT_DIR")
[ -n "${WIKI_PATH:-}" ] && [ -f "$WIKI_PATH" ] && { IMPL_ARGS+=(--wiki "$WIKI_PATH"); RUN_IMPL=1; }
[ -n "${DIALOGUE_PATH:-}" ] && [ -f "$DIALOGUE_PATH" ] && { IMPL_ARGS+=(--dialogue "$DIALOGUE_PATH"); RUN_IMPL=1; }

if [ "$RUN_IMPL" -eq 1 ]; then
  echo "[1/3] strict JSONL merge + non-empty split..."
  "$PYTHON_BIN" scripts/ai/collect_data_impl_v1.py "${IMPL_ARGS[@]}"
else
  echo "[1/3] skip merge (no wiki/dialogue paths); using existing OUT_DIR=$OUT_DIR"
fi

echo "[2/3] cross-split duplicate 검증..."
"$PYTHON_BIN" scripts/verify/verify_cross_split_duplicate_v1.py --data-dir "$OUT_DIR"

echo "[3/3] collect + verify 통과."
echo "COLLECT_DATA_OK=1"
