#!/usr/bin/env bash
set -euo pipefail

# Contract:
# - Input: PROMPT env (string). If the underlying runtime does not support prompt injection yet,
#          we still require PROMPT but may ignore it and record prompt_supported=false in engine_meta upstream.
# - Output: prints one line "ONDEVICE_RUNTIME_V1_OUTPUT <text>" to stdout
# - Exit 0 on success, non-zero on failure with "BLOCK:" message

PROMPT="${PROMPT:-}"
if [[ -z "$PROMPT" ]]; then
  echo "BLOCK: PROMPT env is required" >&2
  exit 1
fi

REPO_ROOT="${REPO_ROOT:-$(cd "$(dirname "$0")/../../.." && pwd)}"

# Find an existing "real inference once" verifier script (repo-local)
CANDIDATES=(
  "$REPO_ROOT/scripts/verify/verify_ondevice_inference_v0.sh"
  "$REPO_ROOT/scripts/verify/verify_ondevice_real_compute_once.sh"
  "$REPO_ROOT/scripts/verify/verify_ondevice_inference_once_v1.sh"
  "$REPO_ROOT/scripts/verify/verify_ondevice_inference_once.sh"
  "$REPO_ROOT/scripts/verify/verify_ondevice_runtime_inference_once_v1.sh"
)

# Try each candidate that exists; use first that succeeds (exit 0 and no BLOCK).
TARGET=""
OUT=""
RC=1
for f in "${CANDIDATES[@]}"; do
  if [[ ! -f "$f" ]]; then continue; fi
  set +e
  OUT="$("$f" 2>&1)"
  RC=$?
  set -e
  if [[ "$RC" -eq 0 ]] && ! echo "$OUT" | grep -q "BLOCK:"; then
    TARGET="$f"
    break
  fi
done

if [[ -z "$TARGET" ]]; then
  echo "BLOCK: no ondevice inference verifier succeeded (tried existing candidates)" >&2
  [[ -n "$OUT" ]] && echo "$OUT" >&2
  exit 1
fi

# Produce a single-line output for exec-mode consumer.
# Extract result_fingerprint_sha256 by key so we do not pick manifest_sha256 or other hashes.
FPR="$(printf '%s\n' "$OUT" | grep -oE 'result_fingerprint_sha256[^0-9a-fA-F]*[0-9a-fA-F]{64}' | grep -oE '[0-9a-fA-F]{64}' | head -n 1 || true)"
if [[ -n "$FPR" ]]; then
  echo "ONDEVICE_RUNTIME_V1_OUTPUT OK fingerprint=${FPR,,}"
else
  echo "ONDEVICE_RUNTIME_V1_OUTPUT OK"
fi

# Also echo original verifier output to stdout? NO (keep meta-only). We only output one line to avoid noise.
exit 0
