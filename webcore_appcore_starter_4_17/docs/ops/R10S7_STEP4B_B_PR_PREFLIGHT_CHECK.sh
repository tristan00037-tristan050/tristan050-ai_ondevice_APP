#!/usr/bin/env bash
# S7 Step4-B B PR 생성 전 "입력 고정/베이스라인 고정" 10초 체크 (정본)
# PR 올리기 전에 한 번만 실행

set -euo pipefail

# === Guard: must not run on main (Step4-B B is input-fixed improvement PR) ===
BRANCH="$(git rev-parse --abbrev-ref HEAD 2>/dev/null || true)"
[ -n "${BRANCH}" ] || { echo "FAIL: cannot detect current branch"; exit 1; }
if [ "${BRANCH}" = "main" ]; then
  echo "FAIL: do not run on main; switch to an improvement branch for Step4-B B"
  exit 1
fi

ROOT="$(git rev-parse --show-toplevel)"
cd "$ROOT"

git fetch origin main --depth=1
CHANGED="$(git diff --name-only origin/main...HEAD)"
echo "$CHANGED" | sed -n "1,200p"

# 입력 고정 위반이면 즉시 FAIL
echo "$CHANGED" | rg -n "^webcore_appcore_starter_4_17/docs/ops/r10-s7-retriever-(goldenset\.jsonl|corpus\.jsonl)$" && {
  echo "FAIL: input must be frozen for Step4-B B"
  exit 1
} || true

# baseline PR 변경도 즉시 FAIL
echo "$CHANGED" | rg -n "^webcore_appcore_starter_4_17/docs/ops/r10-s7-retriever-metrics-baseline\.json$" && {
  echo "FAIL: baseline must not be modified in PR"
  exit 1
} || true

echo "OK: input-fixed + baseline unchanged"

