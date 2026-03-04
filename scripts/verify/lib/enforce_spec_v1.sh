#!/usr/bin/env bash
set -euo pipefail

# Return 1 if <PREFIX>_ENFORCE is "1", else 0.
enforce_spec_should_enforce() {
  local prefix="$1"
  local var="${prefix}_ENFORCE"
  local v="${!var:-0}"
  [ "$v" = "1" ]
}

# Emit standard SKIP keys (no missing keys).
enforce_spec_emit_skip() {
  local prefix="$1"
  echo "${prefix}_OK=0"
  echo "${prefix}_SKIPPED=1"
}
