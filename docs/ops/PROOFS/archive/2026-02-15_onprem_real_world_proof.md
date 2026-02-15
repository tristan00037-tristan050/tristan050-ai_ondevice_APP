# Onprem Real-world Proof (LATEST)
Date: 2026-02-15
Scope: baseline verify + gateway/runtime smoke + egress policy proof
Raw text: 0 (meta-only only)

## 1) Baseline anchor
COMMAND:
bash scripts/verify/verify_repo_contracts.sh ; echo "EXIT=$?"

OUTPUT (paste):
BLOCK: STAMP_SHA_MISMATCH
EXIT=1

## 2) Gateway/Runtime smoke (meta-only)
COMMAND:
curl -sS -D /tmp/headers.txt -o /tmp/body.json \
  -H "content-type: application/json" \
  -H "x-request-id: proof-abc123def456" \
  http://localhost:8081/v1/os/algo/three-blocks \
  --data '{"meta_only":true}'

OUTPUT (paste meta-only; redact secrets):
curl_failed=true
localhost:8081_not_running
service_unavailable

## 3) Egress policy proof (no external success)
COMMAND:
curl -sS https://example.com || echo "blocked_attempt_observed=true"

OUTPUT (paste):
external_success=true
example.com_accessible
egress_policy_not_enforced_or_whitelisted

## 4) Redaction policy
- No private keys
- No tokens/passwords/secrets
- No raw text

