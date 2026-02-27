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

TARGET=""
for f in "${CANDIDATES[@]}"; do
  if [[ -f "$f" ]]; then
    TARGET="$f"
    break
  fi
done

if [[ -z "$TARGET" ]]; then
  echo "BLOCK: ondevice inference verifier not found (expected one of: ${CANDIDATES[*]})" >&2
  exit 1
fi

# Execute verifier once. We intentionally do not pass PROMPT unless the verifier supports it.
# Keep stdout/stderr intact so markers/fingerprints can be captured upstream.
set +e
OUT="$("$TARGET" 2>&1)"
RC=$?
set -e

# Fail-closed on non-zero or explicit BLOCK:
if [[ "$RC" -ne 0 ]] || echo "$OUT" | grep -q "BLOCK:"; then
  echo "$OUT" >&2
  echo "BLOCK: ondevice_runtime_v1 inference verifier failed (rc=$RC)" >&2
  exit 1
fi

# Produce a single-line output for exec-mode consumer.
# Prefer a short proof string if present, else generic OK.
FPR="$(printf '%s\n' "$OUT" | grep -Eo '([0-9a-fA-F]{64})' | head -n 1 || true)"
if [[ -n "$FPR" ]]; then
  echo "ONDEVICE_RUNTIME_V1_OUTPUT OK fingerprint=${FPR,,}"
else
  echo "ONDEVICE_RUNTIME_V1_OUTPUT OK"
fi

# Also echo original verifier output to stdout? NO (keep meta-only). We only output one line to avoid noise.
exit 0
