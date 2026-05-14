# Evaluation PR Operational Standards

Status: active from the next evaluation PR after PR #718
Scope: `scripts/eval/*`, `tests/eval/*`, `evidence/day*/`, and evaluation PR descriptions

## Purpose

This document codifies the governance rules proven during the PR #715/#716/#718 measurement integrity cycles. These standards are intended to prevent evidence/body drift, unreviewed head drift, silent coverage skips, stratification drift, and ambiguous Algorithm Branch naming.

## Verified source incidents

- PR #715: calibration and auto-apply threshold rework cycle; measurement integrity fixes and data leakage gates.
- PR #716: extraction error decomposition cycle; body/evidence alignment recovery and invariant sentinels.
- PR #717: ALGO-CORE-03 p95 hook fix as a separate non-eval track; p95 budget remained unchanged.
- PR #718: Algorithm Branch A vocabulary patch; head drift, coverage fail-closed, and stratified composition sentinels were proven.

## Standard 1 — Evidence correction commits require full PR description synchronization

When an evidence correction commit changes any measured value, count, decision, split, file count, or recommendation, the PR description must be synchronized against the evidence in the same correction cycle.

Required scope of synchronization:

1. Top summary tables
2. Head SHA / review SHA sections
3. Evidence tree counts
4. Measurement definition sections
5. Correction cycle sections
6. Follow-up PR recommendation sections
7. Verdict boundary sections

Partial body updates are not sufficient. If a top table and a lower correction section disagree, the PR must be held until the entire body is synchronized.

Rationale:

- PR #716 had a body table vs evidence mismatch and was held for body/evidence alignment.
- PR #718 repeated the same pattern when the upper summary table was not updated after a second P1 correction cycle.

## Standard 2 — Commit, then SHA confirmation, then body patch

For correction cycles, update order must be:

1. Commit evidence/code/test correction
2. Confirm the new PR head SHA
3. Patch the PR body using the new head SHA and corrected evidence values
4. Request re-review using the latest head SHA

The review request must not cite a stale SHA.

## Standard 3 — Team naming is limited to the 7 governance groups

Do not introduce ad-hoc team names in evaluation PRs. Use only the approved governance group names already in project operation.

Allowed examples:

- 메인 개발팀
- 알고리즘 개발팀
- 재검토팀
- 테스트/보완팀
- 문제해결팀
- 기획/심사팀
- 실행팀

If a new functional area is needed, describe it as a workstream or module, not as a new team.

## Standard 4 — Multiset and weighted invariant sentinels are mandatory

Evaluation PRs that count errors, buckets, aliases, mappings, labels, actions, or deadline classes must include sentinels for:

- multiset correctness
- weighted aggregation correctness
- duplicate handling
- missing/extra sample handling
- declared total vs computed total

The sentinel must fail closed when a counted aggregate can be silently undercounted or overcounted.

## Standard 5 — Algorithm Branch names must be tracked separately from GitHub PR numbers

Algorithm Branch labels and GitHub PR numbers are different namespaces.

Required notation:

- Algorithm Branch A = GitHub PR #718
- Algorithm Branch B = GitHub PR #719
- GitHub PR #717 = ALGO-CORE-03 fix, separate track

PR descriptions must explicitly state the Algorithm Branch label and the GitHub PR number when both are referenced.

Implementation note:

`expected_head_sha` squash merge is mandatory. It correctly blocks merges when an external PR merge causes head drift. This was proven during PR #718 cycle 4, where the head drifted from `54702f76` to `eff012ef` after an external PR merge was absorbed. The stale expected head merge was blocked, the drift was diagnosed, and the merge proceeded only after the expected head was updated.

## Standard 6 — Coverage fail-closed sentinel is mandatory

All evaluation PRs must prove that the evaluated sample set and prediction set match exactly.

Mandatory checks:

- `expected_samples == measured_samples`
- `missing_prediction_ids == []`
- `extra_prediction_ids == []`
- duplicate prediction IDs are rejected
- silent skip is forbidden

Mandatory failure class:

```text
FULL_EVAL_COVERAGE_MISMATCH
```

Recommended evidence fields:

```json
{
  "expected_samples": 500,
  "measured_samples": 500,
  "missing_prediction_count": 0,
  "extra_prediction_count": 0,
  "duplicate_prediction_count": 0,
  "fail_class": null
}
```

This standard applies before computing F1, precision, recall, ECE, deadline rates, or any downstream aggregate.

## Standard 7 — Stratified composition sentinel is mandatory

All A/B or sampled evaluation subsets must prove that the actual sample composition matches the declared composition.

Mandatory checks:

- declared category quotas are recorded
- actual category counts are recorded
- declared and actual composition must match
- insufficient pool must fail closed or be explicitly recorded as blocked

Mandatory failure class:

```text
AB_COMPOSITION_MISMATCH
```

Recommended structure:

```json
{
  "declared_composition": {
    "fp_fn_high_risk": 20,
    "mapping_gap": 15,
    "parser_vs_llm": 10,
    "deadline_monitor": 5
  },
  "actual_composition": {
    "fp_fn_high_risk": 20,
    "mapping_gap": 15,
    "parser_vs_llm": 10,
    "deadline_monitor": 5
  },
  "composition_ok": true,
  "fail_class": null
}
```

## Required pre-merge evaluation PR checklist

Every future evaluation PR must satisfy the following before merge:

- [ ] PR status and latest head SHA are stated in the PR body.
- [ ] Evidence correction commits are reflected across the full PR body.
- [ ] `expected_head_sha` squash merge is used.
- [ ] Algorithm Branch label is separate from the GitHub PR number.
- [ ] Multiset/weighted invariant sentinels are present when aggregates are used.
- [ ] Coverage fail-closed sentinel is present.
- [ ] Stratified composition sentinel is present when A/B or sampled evaluation is used.
- [ ] Forbidden production wording grep passes.
- [ ] No metric threshold lowering is present.
- [ ] No PROCEED verdict appears outside the designated final re-measurement PR.

## Forbidden shortcuts

- Do not merge with a stale PR body.
- Do not merge with a stale head SHA.
- Do not use sampled A/B results without composition proof.
- Do not compute metrics when coverage does not match exactly.
- Do not call an Algorithm Branch by a GitHub PR number without explicit mapping.
- Do not lower thresholds to make a result pass.
- Do not claim production readiness from a MEASURED_ONLY or PATCH evidence PR.

## Next application

These standards apply starting with the next evaluation PR after PR #718, including Algorithm Branch B / GitHub PR #719 and all later `scripts/eval/*` changes.
