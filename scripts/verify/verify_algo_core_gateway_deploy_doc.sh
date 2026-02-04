#!/usr/bin/env bash
set -euo pipefail
DOC="docs/ops/ALGO_CORE_GATEWAY_DEPLOYMENT.md"
test -s "$DOC" || { echo "BLOCK: missing $DOC"; exit 1; }
grep -nF "Fail-Closed" "$DOC" >/dev/null || { echo "BLOCK: doc must include Fail-Closed section"; exit 1; }
echo "ALGO_CORE_GATEWAY_DEPLOY_DOC_OK=1"
exit 0

