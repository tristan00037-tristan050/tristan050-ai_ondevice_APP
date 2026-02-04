#!/usr/bin/env bash
set -euo pipefail

SSOT="docs/ops/contracts/PERF_P95_BUDGET_SSOT.json"
[ -f "$SSOT" ] || { echo "PERF_P95_BUDGET_DEFINED_OK=0"; exit 1; }

command -v node >/dev/null 2>&1 || { echo "BLOCK: node not found"; exit 1; }

contract="$(node -e "const j=require('./$SSOT'); process.stdout.write(String(j.contract_ms||0))")"
[ "${contract}" -ge 1 ] || { echo "PERF_P95_BUDGET_DEFINED_OK=0"; exit 1; }

echo "PERF_P95_BUDGET_DEFINED_OK=1"

out="$(node scripts/perf/run_p95_harness.mjs)"
p95="$(node -e "const o=JSON.parse(process.argv[1]); process.stdout.write(String(o.p95_ms));" "$out")"

# numeric compare (ms)
p95_int="$(node -e "const x=Number(process.argv[1]); process.stdout.write(String(Math.ceil(x))); " "$p95")"

if [ "$p95_int" -gt "$contract" ]; then
  echo "PERF_P95_CONTRACT_OK=0"
  echo "PERF_P95_REGRESSION_BLOCK_OK=0"
  echo "BLOCK: p95_ms=${p95} > contract_ms=${contract}"
  echo "$out"
  exit 1
fi

echo "PERF_P95_CONTRACT_OK=1"
echo "PERF_P95_REGRESSION_BLOCK_OK=1"
echo "OK: p95_ms=${p95} <= contract_ms=${contract}"

