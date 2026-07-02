# Chat Context Learning Incident and Rollback Runbook

STATUS=EVIDENCE_OVERLAY

## Trigger Conditions
- A candidate is accepted without five-gate evidence.
- Queue summary or logs include raw text or identity material.
- Shadow eval evidence later shows PII leakage or false learning.
- `enable_chat=True` is used without GroupA approval.

## Immediate Response
1. Disable chat learning by using `enable_chat=False`.
2. Stop promotion of affected queue records.
3. Identify affected records by `candidate_id` and `record_digest` only.
4. Do not print or reconstruct raw chat contents.

## Recovery
- Re-run producer tests and static verifier.
- Re-run GroupA shadow eval >=100 with digest-safe report.
- Resume only after `pii_zero=true` and `false_learning_zero=true` are re-established.

## Rollback Boundary
This producer never applies runtime changes, never commits automatically, and never trains a model. Rollback is queue/manifest governance only.
