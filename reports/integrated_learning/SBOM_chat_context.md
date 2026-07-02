# Chat Context Learning SBOM / ML-BOM Overlay

STATUS=EVIDENCE_OVERLAY

## Components
| Component | Role |
|---|---|
| `chat_context_producer.py` | Converts verified digest-safe usage context artifacts to integrated learning candidates. |
| `producer_common.py` | Shared envelope, digest, source ref, and queue-ingest helpers. |
| `chat_context.py` | Existing adapter verify gate; unchanged by this producer. |
| `learning_core/*` | Existing intake gate, queue, contract, and runner; unchanged by this producer. |

## Data Classes
- Raw chat text: not accepted.
- PII: not accepted.
- Context storage: digest only via `context_digest`.
- Evidence storage: `evidence_digest` and `evidence_ref` only.

## Supply Chain Notes
- No model file changes.
- No PEFT/QLoRA changes.
- No new external API dependency.
- No runtime auto-apply path.
