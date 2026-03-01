#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
SSOT="$ROOT/docs/ops/contracts/OUTPUT_ROOT_SSOT_V1.txt"

read_out_root() {
  local v=""
  if [ -f "$SSOT" ]; then
    v="$(grep -E '^OUT_ROOT=' "$SSOT" | tail -n1 | cut -d= -f2- | tr -d '\r')"
  fi

  # fallback: 로컬=docs, CI=out (단, SSOT가 있으면 SSOT 우선)
  if [ -z "$v" ]; then
    if [ "${CI:-}" = "true" ]; then v="out"; else v="docs"; fi
  fi

  case "$v" in
    out|docs) echo "$v" ;;
    *) exit 2 ;;
  esac
}
