# Milestone 6 Kickoff: Production Proof & Traceability
Date: 2026-01-31

## Execution Queues
| Queue | Focus | Key Deliverable | DoD Key |
| --- | --- | --- | --- |
| REAL-PROOF | Ops Reality | Real-world proof file committed + verify gated | ONPREM_REAL_WORLD_PROOF_OK=1 |
| COMPAT-GUARD | Version Safety | compat enforcement (min runtime/gateway) fail-closed | MODEL_PACK_V0_COMPAT_ENFORCED_OK=1 |
| TRACE-OPS | Observability | request_id joinability (UI↔Runtime↔OpsHub) | OPS_HUB_TRACEABILITY_OK=1 |

## Invariants
- PASS = DoD keys + EXIT=0 only
- All failures must be explainable with request_id + reason_code (meta-only)
- No raw text, no secrets

