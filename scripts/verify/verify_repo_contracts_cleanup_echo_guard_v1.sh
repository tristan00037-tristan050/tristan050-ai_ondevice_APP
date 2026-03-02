#!/usr/bin/env bash
set -euo pipefail

CLEANUP_ECHO_GUARD_V1_OK=0
finish() { echo "CLEANUP_ECHO_GUARD_V1_OK=${CLEANUP_ECHO_GUARD_V1_OK}"; }
trap finish EXIT

ROOT="$(git rev-parse --show-toplevel)"
cd "$ROOT"

CONTRACT="scripts/verify/verify_repo_contracts.sh"
test -f "$CONTRACT" || { echo "ERROR_CODE=CONTRACT_MISSING"; exit 1; }

# Optional: keys that may be declared but not echoed (legacy/conditional). Default empty.
ALLOW_MISSING_KEYS="${ALLOW_MISSING_KEYS:-}"

# 1) Declared _OK=0 keys (start of line)
declared=$(grep -E '^[A-Z0-9_]+_OK=0$' "$CONTRACT" | sed 's/=0$//' | sort -u)

# 2) Echoed in cleanup() block (echo "KEY_OK=${KEY_OK}")
cleanup_block=$(awk '/^cleanup\(\)\{?/,/^}$/' "$CONTRACT")
echoed=$(echo "$cleanup_block" | grep -oE 'echo "[A-Z0-9_]+_OK=' | sed 's/echo "//;s/=$//' | sort -u)

# 3) Missing = declared but not echoed
missing=$(comm -23 <(echo "$declared") <(echo "$echoed")) || true

# 4) Apply allowlist: remove allowed from missing
if [ -n "$ALLOW_MISSING_KEYS" ]; then
  allowed_pattern=$(echo "$ALLOW_MISSING_KEYS" | tr '|' '\n' | grep -v '^$' || true)
  if [ -n "$allowed_pattern" ]; then
    missing=$(echo "$missing" | grep -vE "^($(echo "$allowed_pattern" | paste -sd'|' -))$" || true)
  fi
fi

# 5) Fail if any missing
if [ -n "$missing" ]; then
  first_missing=$(echo "$missing" | head -n1)
  echo "ERROR_CODE=CLEANUP_ECHO_MISSING"
  echo "MISSING_KEY=${first_missing}"
  exit 1
fi

CLEANUP_ECHO_GUARD_V1_OK=1
exit 0
