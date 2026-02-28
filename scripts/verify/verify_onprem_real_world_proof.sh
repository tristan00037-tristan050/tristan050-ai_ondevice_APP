#!/usr/bin/env bash
set -euo pipefail

PROOF_LATEST="docs/ops/PROOFS/ONPREM_REAL_WORLD_PROOF_LATEST.md"

fail() { echo "FAIL: $1" >&2; exit 1; }

have_rg() { command -v rg >/dev/null 2>&1 && rg --version >/dev/null 2>&1; }
match_n() { if have_rg; then rg -n "$1" "$2" >/dev/null 2>&1; else grep -nE "$1" "$2" >/dev/null 2>&1; fi; }

[[ -f "$PROOF_LATEST" ]] || fail "proof file missing: $PROOF_LATEST"
[[ -s "$PROOF_LATEST" ]] || fail "proof file empty: $PROOF_LATEST"

# placeholder 금지
if have_rg; then
  rg -n "(TODO|TBD|PLACEHOLDER|FIXME|<gateway-host>|<port>|<uuid>)" "$PROOF_LATEST" >/dev/null 2>&1 && fail "placeholder found"
else
  grep -nE "(TODO|TBD|PLACEHOLDER|FIXME|<gateway-host>|<port>|<uuid>)" "$PROOF_LATEST" >/dev/null 2>&1 && fail "placeholder found"
fi

# 민감정보 금지(강화 패턴)
if have_rg; then
  rg -n "(BEGIN (RSA|EC|OPENSSH) PRIVATE KEY|PRIVATE KEY|ed25519.*private|seed)" "$PROOF_LATEST" >/dev/null 2>&1 && fail "private key / seed-like content found"
  rg -n "(DATABASE_URL=|EXPORT_SIGN_SECRET=|_PRIVATE_KEY|_TOKEN=|_PASSWORD=|_SECRET=)" "$PROOF_LATEST" >/dev/null 2>&1 && fail "secret-like env content found"
else
  grep -nE "(BEGIN (RSA|EC|OPENSSH) PRIVATE KEY|PRIVATE KEY|ed25519.*private|seed)" "$PROOF_LATEST" >/dev/null 2>&1 && fail "private key / seed-like content found"
  grep -nE "(DATABASE_URL=|EXPORT_SIGN_SECRET=|_PRIVATE_KEY|_TOKEN=|_PASSWORD=|_SECRET=)" "$PROOF_LATEST" >/dev/null 2>&1 && fail "secret-like env content found"
fi

# 필수 마커(출력 기반)
match_n 'EXIT=0' "$PROOF_LATEST" || fail "missing EXIT=0"
match_n 'ok=true' "$PROOF_LATEST" || fail "missing ok=true"
match_n 'blocks=3' "$PROOF_LATEST" || fail "missing blocks=3"
match_n 'signature\.mode=prod' "$PROOF_LATEST" || fail "missing signature.mode=prod"
match_n 'X-OS-Algo-Latency-Ms' "$PROOF_LATEST" || fail "missing latency header marker"
match_n 'X-OS-Algo-Manifest-SHA256' "$PROOF_LATEST" || fail "missing manifest header marker"
match_n 'egress_default=deny' "$PROOF_LATEST" || fail "missing egress deny marker"
match_n 'blocked_attempt_observed=true' "$PROOF_LATEST" || fail "missing blocked attempt marker"
match_n 'external_success=false' "$PROOF_LATEST" || fail "missing external_success=false marker"

echo "ONPREM_REAL_WORLD_PROOF_OK=1"
echo "ONPREM_REAL_WORLD_PROOF_FORMAT_OK=1"
exit 0

