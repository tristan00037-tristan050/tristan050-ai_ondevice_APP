#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "$ROOT"
OUT_ROOT="${OUT_ROOT:-out}"
FILES="$(find "$OUT_ROOT" -type f -name "result.jsonl" 2>/dev/null | sort || true)"
export FILES
bash scripts/verify/verify_exec_mode_latency_present_v1.sh
