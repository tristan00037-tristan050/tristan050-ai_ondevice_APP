# Box 3 v1.2 Quality Rubric

This package was built against the following acceptance rubric before final
packaging.

| Criterion | Gate | Result |
|---|---|---|
| Directive coverage | v1.2 requirements mapped to code, tests, evidence, and handoff docs | PASS |
| Endpoint compatibility | `/v1/cards/3/draft` with `input_text`, `prompt_template`, `max_new_tokens` | PASS |
| Asset honesty | Short display SHA never used as a seal; real claim blocked unless full SHA and interface inventory pass | PASS |
| Five-step pipeline | helper7 extract, box3 draft, helper4 grounding, helper3 format, helper8 style | PASS contract wrapper |
| Grounding fail-closed | Unsupported claim rate over threshold returns needs_review/block | PASS |
| Evaluation | 40 digest-only cases, verdict-only metrics, table/figure coverage at least 8 | PASS proxy |
| Raw boundary | raw text, filename, path, PII, secret, token evidence persistence blocked | PASS |
| Training boundary | no training, model promotion, adapter writing, or binary artifact | PASS |
| Claim boundary | no real, eval-pass, deployment, or shipping claim without asset inventory | PASS |

Final status is `PARTIAL_CONTRACT_ONLY_ASSET_INVENTORY_PENDING`, not real.
