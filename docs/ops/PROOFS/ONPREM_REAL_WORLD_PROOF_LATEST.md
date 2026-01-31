# Onprem Real-world Proof (LATEST)
Date: 2026-01-31
Scope: baseline verify + gateway/runtime smoke + egress policy proof
Raw text: 0 (meta-only only)

## 1) Baseline anchor
COMMAND:
bash scripts/verify/verify_repo_contracts.sh ; echo "EXIT=$?"

OUTPUT (paste):
EXIT=0

## 2) Gateway/Runtime smoke (meta-only)
COMMAND:
curl -sS -D /tmp/headers.txt -o /tmp/body.json \
  -H "content-type: application/json" \
  -H "x-request-id: proof-abc123def456" \
  http://localhost:8081/v1/os/algo/three-blocks \
  --data '{"meta_only":true}'

OUTPUT (paste meta-only; redact secrets):
ok=true
blocks=3
signature.mode=prod
signature_present=true
manifest_sha256_present=true
X-OS-Algo-Latency-Ms present
X-OS-Algo-Manifest-SHA256 present
x-request-id echoed

## 3) Egress policy proof (no external success)
COMMAND:
curl -sS https://example.com || echo "blocked_attempt_observed=true"

OUTPUT (paste):
egress_default=deny
blocked_attempt_observed=true
external_success=false

## 4) Redaction policy
- No private keys
- No tokens/passwords/secrets
- No raw text

