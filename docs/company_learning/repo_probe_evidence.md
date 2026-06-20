# Company Learning Repo Probe Evidence

Date: 2026-06-20

## Verified Baseline

- `butler_pc_core/retrieval/chunkers/base.py`: `BaseChunker.chunk(content: str, source_file: str = "")` accepts runtime text, not a file path.
- `butler_pc_core/retrieval/chunkers/base.py`: `_make_id()` derives `chunk_id` from `source_file`, so company learning passes digest-only `source_id` values such as `file:<hex>`.
- `butler_pc_core/retrieval/chunkers/dispatcher.py`: `get_chunker()` falls back to `MeetingMinutesChunker` when file type/extension is not matched. Company learning therefore checks `ALLOWED_EXTENSIONS` before calling `get_chunker()`.
- `butler_pc_core/retrieval/pipeline.py`: `PersonalPackIndex.build(chunks)` builds the existing BM25+Vector index pair, and `HybridRetrievalPipeline(index).retrieve(...)` is the existing retrieval surface.
- `schemas/connect_loop/learning_event_v1.schema.json`: `additionalProperties` is `false`, required fields are the 19 fields in the schema, and there is no `source_kind` property.
- `schemas/connect_loop/learning_event_v1.schema.json`: `label.intent_label="memory_search"` requires `label.target_box_id="helper1"`.
- `schemas/connect_loop/learning_event_v1.schema.json`: `policy_approval.reason_code` accepts uppercase code pattern `^[A-Z][A-Z0-9_]{0,63}$`; `FOLDER_UNDERSTANDING_CANDIDATE` is schema-shaped.
- `butler_pc_core/connect_loop/learning_candidate_gate.py`: `APPROVED_REF_RE = ^(vault|keyring)://[^\s]{1,240}$`; company learning emits `vault://company-learning/<digest>`.
- `butler_pc_core/connect_loop/dlp_guard.py`: `scan_runtime_text()` returns exactly `passed`, `pii_detected`, `secret_detected`, and `policy_violation` booleans.
- `butler_pc_core/inference/llm_runtime.py`: `LlmRuntime.status` is `ready`, `no_model`, `loading`, or `error`; non-ready generation returns a `[stub]` string, so company learning does not use non-ready LLM output for understanding claims.
- `butler_pc_core/company_fact/routes.py` and `butler_pc_core/sidecar/routes/company_profile.py`: route-local capability token verification and admin header parsing are the current sidecar pattern.
- `butler-desktop/src/lib/admin_policy/adminContext.ts`: frontend admin context reuses `buildAdminHeadersInput`; company learning adds no new admin provider.

## Implementation Consequences

- Unsupported extensions are skipped before chunker dispatch.
- Folder path and file names remain runtime-only. Responses expose `folder_digest`, `ingest_digest`, counters, and evidence chips only.
- Evidence chips contain `chunk_digest`, digest-only `source_id`, `section_digest`, `page_or_sheet`, and numeric `char_span`; no snippet is emitted.
- Handoff appends only a schema-valid `learning_event.v1` CANDIDATE with `verified_for_training=false`. No fine-tune, trainer, model adapter, or team server path is invoked.

## Integration Backport Evidence

- `folder_ingest.py` now preflights OOXML files before `python-docx`, `openpyxl`, or `python-pptx` receives the archive bytes.
- OOXML preflight checks ZIP signature, member count, total uncompressed bytes, per-member bytes, and compression ratio. Failures become skip/fail-class paths without raw path or file name exposure.
- PDF extraction now has a page-count guard before `pdfminer.extract_text`, and extracted runtime text is bounded by per-file and total character limits.
- `sidecar/routes/company_learning.py` now checks `request.client.host` against `LOCALHOST_HOSTS` before capability token and registered-admin checks on all four endpoints.
- B4 encrypted approved-text vault remains intentionally out of scope; handoff still stops at digest-only `learning_event.v1` CANDIDATE registration.
