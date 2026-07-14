#!/usr/bin/env bash
set -euo pipefail
umask 077

# P0-3: actually runnable product integration. Imports the real butler_pc_core
# product adapter, calls the six benchmark entrypoints against real Box3/DLP
# functions, proves the observation hook is byte-identical off/on, and confirms the
# real Box3 endpoint/runner/DLP/approval surfaces connect. Runs in CI and in the
# owner's pre-M3 step. RUNTIME_ACTIVATION_ALLOWED stays 0; no model execution here.

BENCH_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
REPO_ROOT="$(git -C "$BENCH_DIR" rev-parse --show-toplevel)"
cd "$BENCH_DIR"

PYTHONDONTWRITEBYTECODE=1 PYTHONPATH="${REPO_ROOT}:${BENCH_DIR}:${BENCH_DIR}/tests" \
  python3 -m unittest discover -s tests/integration -p 'test_*.py' -v

# Optional (M3 pre-flight): when the owner supplies the approved product identity,
# also verify the committed adapter + every entrypoint owner blob against the
# approved commit tree. Absent these inputs the integration proof above stands alone.
if [ -n "${BUTLER_PRODUCT_MODULE:-}" ] && [ -n "${BUTLER_PRODUCT_ROOT:-}" ] \
   && [ -n "${BUTLER_PRODUCT_MODULE_SHA256:-}" ] && [ -n "${BUTLER_PRODUCT_COMMIT_OID:-}" ]; then
  PYTHONDONTWRITEBYTECODE=1 PYTHONPATH="${REPO_ROOT}:${BENCH_DIR}" \
    python3 -m butler_bench.cli product-preflight \
      --module "$BUTLER_PRODUCT_MODULE" \
      --product-root "$BUTLER_PRODUCT_ROOT" \
      --module-sha256 "$BUTLER_PRODUCT_MODULE_SHA256" \
      --commit-oid "$BUTLER_PRODUCT_COMMIT_OID"
fi
