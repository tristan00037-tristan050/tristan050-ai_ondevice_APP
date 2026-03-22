#!/usr/bin/env bash
set -euo pipefail

AI20_REAL_TRAIN_CLI_FAIL_CLOSED_OK=0
REAL_TRAIN_GIT_SHA_RESOLVED_OK=0
TRAINING_ARGUMENTS_STRATEGY_KEY_RESOLVED_FOR_REAL_RUN_OK=0

cleanup() {
  echo "AI20_REAL_TRAIN_CLI_FAIL_CLOSED_OK=${AI20_REAL_TRAIN_CLI_FAIL_CLOSED_OK}"
  echo "REAL_TRAIN_GIT_SHA_RESOLVED_OK=${REAL_TRAIN_GIT_SHA_RESOLVED_OK}"
  echo "TRAINING_ARGUMENTS_STRATEGY_KEY_RESOLVED_FOR_REAL_RUN_OK=${TRAINING_ARGUMENTS_STRATEGY_KEY_RESOLVED_FOR_REAL_RUN_OK}"
  if [[ "$AI20_REAL_TRAIN_CLI_FAIL_CLOSED_OK" == "1" ]]; then
    exit 0
  fi
  exit 1
}
trap cleanup EXIT

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
SCRIPT="$ROOT_DIR/scripts/ai/finetune_qlora_small_v1.py"
TRAIN_FILE="$ROOT_DIR/data/synthetic_v40/train.jsonl"
EVAL_FILE="$ROOT_DIR/data/synthetic_v40/validation.jsonl"
TMP_DIR="$ROOT_DIR/tmp/ai20_cli_failclosed"
rm -rf "$TMP_DIR"
mkdir -p "$TMP_DIR"

# Case 1: outside a git repo -> git SHA unresolved must fail first.
OUT1="$TMP_DIR/case_git_unknown.log"
if (cd /tmp && python3 "$SCRIPT"   --model-id Qwen/Qwen2.5-3B-Instruct   --train-file "$TRAIN_FILE"   --eval-file "$EVAL_FILE"   --output-dir "$TMP_DIR/out_git_unknown"   --target-tag small_default) >"$OUT1" 2>&1; then
  echo "FAIL: git_unknown case unexpectedly succeeded" >&2
  exit 1
fi
if grep -q 'REAL_TRAIN_GIT_SHA_RESOLVED_OK=0' "$OUT1"; then
  REAL_TRAIN_GIT_SHA_RESOLVED_OK=1
else
  echo "FAIL: git_unknown case did not emit expected fail-closed marker" >&2
  cat "$OUT1" >&2 || true
  exit 1
fi

# Case 2: inside a git repo but with unresolved TrainingArguments strategy key -> must fail.
REPO="$TMP_DIR/repo_case"
mkdir -p "$REPO"
(
  cd "$REPO"
  git init -q
  git config user.email ai20@example.com
  git config user.name ai20
  echo ok > seed.txt
  git add seed.txt
  git commit -q -m init
)
OUT2="$TMP_DIR/case_strategy_unresolved.log"
if (cd "$REPO" && PYTHONNOUSERSITE=1 python3 "$SCRIPT"   --model-id Qwen/Qwen2.5-3B-Instruct   --train-file "$TRAIN_FILE"   --eval-file "$EVAL_FILE"   --output-dir "$TMP_DIR/out_strategy_unresolved"   --target-tag small_default) >"$OUT2" 2>&1; then
  echo "FAIL: strategy_unresolved case unexpectedly succeeded" >&2
  exit 1
fi
if grep -q 'TRAINING_ARGUMENTS_STRATEGY_KEY_RESOLVED_FOR_REAL_RUN_OK=0' "$OUT2"; then
  TRAINING_ARGUMENTS_STRATEGY_KEY_RESOLVED_FOR_REAL_RUN_OK=1
else
  echo "FAIL: strategy_unresolved case did not emit expected fail-closed marker" >&2
  cat "$OUT2" >&2 || true
  exit 1
fi

AI20_REAL_TRAIN_CLI_FAIL_CLOSED_OK=1
