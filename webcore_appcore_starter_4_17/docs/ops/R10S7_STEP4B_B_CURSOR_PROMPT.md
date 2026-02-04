# S7 Step4-B B Cursor 원샷 프롬프트 (정본)

## Role
You are the Lead Search Engineer executing **S7 Step4-B B (Input-Fixed Algorithm Improvement)**.

## Non-negotiable Hard Rules
1) DO NOT modify:
   - docs/ops/r10-s7-retriever-goldenset.jsonl
   - docs/ops/r10-s7-retriever-corpus.jsonl
   - docs/ops/r10-s7-retriever-metrics-baseline.json
2) Mixed PR forbidden: input change + algo change must NOT be combined.
3) MUST PASS: verify_s7_always_on.sh, prove_retriever_regression_gate.sh, verify_rag_meta_only.sh
4) MUST ACHIEVE: strict improvement >= 1 (at least one metric strictly greater than baseline)
5) Plan B: DO NOT use --reanchor-input anywhere.

## Step 0) Input/Baseline Lock (Fail fast)
- Run from repo root:
  - git fetch origin main --depth=1
  - git diff --name-only origin/main...HEAD
- If any of the three locked files are modified, revert them immediately and stop.

## Step 1) Identify the tie-break switch and comparator
- Search for TIEBREAK_ENABLE usage and the sorting comparator:
  - rg -n "TIEBREAK_ENABLE|secondary_score|secondaryScore|tie|tiebreak|primary_score|primaryScore" webcore_appcore_starter_4_17
- Confirm current behavior:
  - primary_score is used for ranking
  - secondary_score exists but is not used (or is gated behind TIEBREAK_ENABLE)

## Step 2) Implement deterministic tie-breaking (input-fixed algorithm change)
- Change comparator to:
  - sort by primary_score desc
  - if primary_score ties, sort by secondary_score desc
  - final tie-breaker by doc_id asc (deterministic)
- Ensure meta-only: do not print raw query/doc text in logs/proofs.

## Step 3) Make sure the regression proof actually runs with tie-break enabled
- Ensure the evaluation path invoked by prove_retriever_regression_gate.sh uses tie-break.
- Preferred: set/propagate TIEBREAK_ENABLE=1 in the regression-gate execution path (without touching input/baseline).

## Step 4) Run the full proof + strict-improvement check (must PASS)
Run:
- cd webcore_appcore_starter_4_17
- bash scripts/ops/verify_s7_always_on.sh
- bash scripts/ops/verify_s7_corpus_no_pii.sh
- export TIEBREAK_ENABLE=1
- bash scripts/ops/prove_retriever_regression_gate.sh
- META_ONLY_DEBUG=1 bash scripts/ops/verify_rag_meta_only.sh

Then print strict-improvement JSON by comparing:
- docs/ops/r10-s7-retriever-quality-phase1-report.json
- docs/ops/r10-s7-retriever-metrics-baseline.json

If strict improvement is not achieved, do NOT commit; adjust only algorithm logic (still input-fixed) and retry.

## Step 5) Commit
- Commit only algorithm changes + generated proof/.latest artifacts.
- Commit message:
  ```
  feat(s7): step4-b-b enable deterministic tie-break for strict improvement (input fixed)
  ```

