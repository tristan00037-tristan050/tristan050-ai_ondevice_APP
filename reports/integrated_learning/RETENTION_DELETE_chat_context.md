# Chat Context Learning Retention and Delete Overlay

STATUS=EVIDENCE_OVERLAY

## Retention Principle
`chat_context` candidates store only digest/ref material. No raw prompt, raw response, speaker identity, timestamp text, local path, or PII is stored by the producer.

## Retained Fields
- `candidate_id`
- `payload_digest`
- `expected_effect_digest`
- `context_digest`
- `source_refs[].ref_id_digest`
- `verification.evidence_digest`
- queue record digest

## Delete / Rollback
- Candidate deletion or rejection must operate by candidate digest / queue record digest.
- Operational activation requires a later human-approved workflow and is outside this producer.
- If evidence is invalidated, mark candidate queue status through governance tooling; do not mutate raw artifacts because raw artifacts are not stored here.

## Opt-out
If a tenant disables chat learning, keep `enable_chat=False`; producer-built candidates will be rejected by the existing chat adapter with `CHAT_LEARNING_DISABLED`.
