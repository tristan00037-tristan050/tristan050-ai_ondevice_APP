#!/usr/bin/env bash
set -euo pipefail

# Contract:
# - Input: a single prompt string via env PROMPT (for v1 slot)
# - Output: prints one line "ONDEVICE_RUNTIME_V1_OUTPUT <text>" to stdout
# - Exit 0 on success, non-zero on failure with "BLOCK:" message

PROMPT="${PROMPT:-}"
if [[ -z "$PROMPT" ]]; then
  echo "BLOCK: PROMPT env is required" >&2
  exit 1
fi

# TODO: wire to real on-device runtime.
# For now, fail-closed to prevent false success.
echo "BLOCK: ondevice_runtime_v1 not wired yet" >&2
exit 1
