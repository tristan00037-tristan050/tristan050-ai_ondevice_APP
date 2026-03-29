#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_DIR="${REPO_DIR:-$(cd "$SCRIPT_DIR/../.." && pwd)}"
ADAPTER_DIR="${ADAPTER_DIR:-output/butler_model_small_v1}"
EVAL_FILE="${EVAL_FILE:-data/eval/butler_eval_v3.jsonl}"
HARDCASE_FILE="${HARDCASE_FILE:-data/eval/butler_hardcase_v1.jsonl}"
MODEL_VERSION="${MODEL_VERSION:-butler_model_small_v1}"
BASELINE_PATH="${BASELINE_PATH:-data/eval/baseline_scores_v3.json}"
TRAIN_DIGEST_FILE="${TRAIN_DIGEST_FILE:-}"
DRY_RUN="${DRY_RUN:-false}"

cd "$REPO_DIR"
mkdir -p tmp

status=0
if [ "$DRY_RUN" = "true" ]; then
  python scripts/eval/eval_runner_v3.py     --dry-run     --eval-file "$EVAL_FILE"     --hardcase-file "$HARDCASE_FILE"     --model-version "$MODEL_VERSION"     --baseline-path "$BASELINE_PATH"     --report-path tmp/eval_report_v3.json || status=$?
else
  runner_args=(
    --adapter-dir "$ADAPTER_DIR"
    --eval-file "$EVAL_FILE"
    --hardcase-file "$HARDCASE_FILE"
    --model-version "$MODEL_VERSION"
    --baseline-path "$BASELINE_PATH"
    --report-path tmp/eval_report_v3.json
  )
  if [ -n "$TRAIN_DIGEST_FILE" ]; then
    runner_args+=(--train-digest-file "$TRAIN_DIGEST_FILE")
  fi
  python scripts/eval/eval_runner_v3.py "${runner_args[@]}" || status=$?
fi

if [ -f tmp/eval_report_v3.json ]; then
  python scripts/eval/eval_report_v3.py     --report-path tmp/eval_report_v3.json     --output-path tmp/eval_summary_v3.md
fi

exit "$status"
