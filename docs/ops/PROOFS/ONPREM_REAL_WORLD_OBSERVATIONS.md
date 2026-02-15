# Onprem Real-world Proof Observations

Date: 2026-02-15
Scope: Failure observations (meta-only, no raw text)

## Observation Summary

This document tracks observed failures during onprem proof execution attempts. These observations are separate from the LATEST proof file, which must contain only PASS markers.

## 2026-02-15 Observations

### Baseline anchor
- Status: STAMP_SHA_MISMATCH (resolved by creating build stamp)
- Resolution: Build stamp generation step added to workflow

### Gateway/Runtime smoke
- Status: INFER_FAILED
- Observation: BFF service running but model inference failed
- Possible causes: Model pack not loaded, inference environment issue

### Egress policy proof
- Status: external_success=true (egress deny not enforced)
- Observation: curl to example.com succeeded from host environment
- Note: Egress deny requires compose/K8s environment with network policy enforcement

## Redaction policy
- No private keys
- No tokens/passwords/secrets
- No raw text

