#!/usr/bin/env bash
set -euo pipefail

PROOF_LATEST="docs/ops/PROOFS/ONPREM_REAL_WORLD_PROOF_LATEST.md"

fail() { echo "FAIL: $1" >&2; exit 1; }

[[ -f "$PROOF_LATEST" ]] || fail "proof file missing: $PROOF_LATEST"
[[ -s "$PROOF_LATEST" ]] || fail "proof file empty: $PROOF_LATEST"

# placeholder 금지
if rg -n "(TODO|TBD|PLACEHOLDER|FIXME|<gateway-host>|<port>|<uuid>)" "$PROOF_LATEST" ; then
  fail "placeholder found"
fi

# 민감정보 금지(강화 패턴)
if rg -n "(BEGIN (RSA|EC|OPENSSH) PRIVATE KEY|PRIVATE KEY|ed25519.*private|seed)" "$PROOF_LATEST" ; then
  fail "private key / seed-like content found"
fi
if rg -n "(DATABASE_URL=|EXPORT_SIGN_SECRET=|_PRIVATE_KEY|_TOKEN=|_PASSWORD=|_SECRET=)" "$PROOF_LATEST" ; then
  fail "secret-like env content found"
fi

# 필수 마커(출력 기반)
rg -n 'EXIT=0' "$PROOF_LATEST" >/dev/null || fail "missing EXIT=0"
rg -n 'ok=true' "$PROOF_LATEST" >/dev/null || fail "missing ok=true"
rg -n 'blocks=3' "$PROOF_LATEST" >/dev/null || fail "missing blocks=3"
rg -n 'signature\.mode=prod' "$PROOF_LATEST" >/dev/null || fail "missing signature.mode=prod"
rg -n 'X-OS-Algo-Latency-Ms' "$PROOF_LATEST" >/dev/null || fail "missing latency header marker"
rg -n 'X-OS-Algo-Manifest-SHA256' "$PROOF_LATEST" >/dev/null || fail "missing manifest header marker"
rg -n 'egress_default=deny' "$PROOF_LATEST" >/dev/null || fail "missing egress deny marker"
rg -n 'blocked_attempt_observed=true' "$PROOF_LATEST" >/dev/null || fail "missing blocked attempt marker"
rg -n 'external_success=false' "$PROOF_LATEST" >/dev/null || fail "missing external_success=false marker"

echo "ONPREM_REAL_WORLD_PROOF_OK=1"
echo "ONPREM_REAL_WORLD_PROOF_FORMAT_OK=1"
exit 0

