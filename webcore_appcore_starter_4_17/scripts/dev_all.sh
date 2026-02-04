#!/usr/bin/env bash
set -euo pipefail

if ! command -v tmux >/dev/null 2>&1; then
  echo "[dev_all] ERROR: tmux is required"
  exit 1
fi

SESSION="appcore-dev"

cd "$(git rev-parse --show-toplevel)/webcore_appcore_starter_4_17"

tmux kill-session -t "${SESSION}" 2>/dev/null || true
tmux new-session -d -s "${SESSION}" -n bff "./scripts/dev_bff.sh restart"

# healthz 뜰 때까지 대기(최대 20초)
tmux new-window -t "${SESSION}" -n check "bash -lc 'for i in {1..20}; do curl -fsS http://127.0.0.1:8081/healthz >/dev/null && break; sleep 1; done; ./scripts/dev_check.sh; echo; echo \"[dev_all] Open http://localhost:8083\"; exec bash'"

tmux new-window -t "${SESSION}" -n web "./scripts/dev_web.sh"

tmux select-window -t "${SESSION}:bff"
tmux attach -t "${SESSION}"

