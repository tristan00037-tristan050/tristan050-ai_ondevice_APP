# Chat Context Learning AI Risk Register

STATUS=EVIDENCE_OVERLAY

## Scope
- Target kind: `chat_context`
- Producer: `butler_pc_core/learning_adapters/chat_context_producer.py`
- Purpose: accept only digest-safe, approved Butler usage-context learning candidates.
- Out of scope: raw chat text, peer/messenger import, PII retention, runtime auto-apply, model/PEFT training.

## Risks and Controls
| Risk | Control |
|---|---|
| Sensitive information disclosure | Producer accepts `context_digest` only; raw artifact fields are rejected. |
| False learning from casual chat | `explicit_business_confirmation`, manager/admin approval, and shadow eval >=100 are required. |
| Excessive agency | `auto_apply_to_runtime=false`, `human_review_required=true`, queue only. |
| Training data poisoning | `pii_zero=true`, `false_learning_zero=true`, source refs restricted to `usage_log` and `approval`. |
| Audit ambiguity | Integrated candidate envelope records target kind, payload digest, evidence digest, source ref digests. |

## Owner
- Risk owner: Butler integrated learning governance.
- Review gate: GroupA shadow eval + 재검토팀 review before operational activation.
