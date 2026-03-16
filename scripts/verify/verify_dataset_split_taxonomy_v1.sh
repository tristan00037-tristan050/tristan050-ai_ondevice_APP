#!/usr/bin/env bash
set -euo pipefail
DATASET_SPLIT_TAXONOMY_V1_OK=0
DATASET_SPLIT_NO_ALIAS_WRITE_OK=0
VAL_ALIAS_FORBIDDEN_OK=0
DRY_RUN=0
if [[ "${1:-}" == "--dry-run" ]]; then
  DRY_RUN=1
fi
cleanup() {
  echo "DATASET_SPLIT_TAXONOMY_V1_OK=${DATASET_SPLIT_TAXONOMY_V1_OK}"
  echo "DATASET_SPLIT_NO_ALIAS_WRITE_OK=${DATASET_SPLIT_NO_ALIAS_WRITE_OK}"
  echo "VAL_ALIAS_FORBIDDEN_OK=${VAL_ALIAS_FORBIDDEN_OK}"
  [[ "$DATASET_SPLIT_TAXONOMY_V1_OK" == "1" ]] && [[ "$DATASET_SPLIT_NO_ALIAS_WRITE_OK" == "1" ]] && [[ "$VAL_ALIAS_FORBIDDEN_OK" == "1" ]] && exit 0
  exit 1
}
trap cleanup EXIT
TARGET="scripts/ai/generate_synthetic_data_v1_final.py"
if [[ "$DRY_RUN" == "1" ]]; then
  TARGET="$(cd "$(dirname "$0")/../.." && pwd)/scripts/ai/generate_synthetic_data_v1_final.py"
fi
if grep -En '"split"\s*:\s*"val"([^i]|$)' "$TARGET"; then
  echo "BLOCK: val 사용 금지 — validation 사용할 것"
  exit 1
fi
DATASET_SPLIT_TAXONOMY_V1_OK=1
DATASET_SPLIT_NO_ALIAS_WRITE_OK=1
VAL_ALIAS_FORBIDDEN_OK=1
