#!/usr/bin/env bash
set -euo pipefail
umask 077

: "${BUTLER_PRODUCT_MODULE:?actual Butler product module required}"
: "${BUTLER_PRODUCT_ROOT:?actual Butler product root required}"
: "${BUTLER_PRODUCT_MODULE_SHA256:?approved module SHA-256 required}"
: "${BUTLER_PRODUCT_COMMIT_OID:?full product commit OID required}"
python3 -m butler_bench.cli product-preflight \
  --module "$BUTLER_PRODUCT_MODULE" \
  --product-root "$BUTLER_PRODUCT_ROOT" \
  --module-sha256 "$BUTLER_PRODUCT_MODULE_SHA256" \
  --commit-oid "$BUTLER_PRODUCT_COMMIT_OID"
PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=. python3 -m unittest discover -s tests/integration -p 'test_*.py' -v
