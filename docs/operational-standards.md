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
- Algorithm Branch B = GitHub PR #720 (merge SHA `e838543b44cfa03ab31893304547f7218de44b82`)
- Algorithm Branch B-2 = GitHub PR #721+ (planned)
- GitHub PR #717 = ALGO-CORE-03 fix, separate track
- GitHub PR #719 = operational standards documentation PR

PR descriptions must explicitly state the Algorithm Branch label and the GitHub PR number when both are referenced.

Implementation note:

`expected_head_sha` squash merge is mandatory. It correctly blocks merges when an external PR merge causes head drift. This was proven during PR #718 cycle 4, where the head drifted from `54702f76` to `eff012ef` after an external PR merge was absorbed. The stale expected head merge was blocked, the drift was diagnosed, and the merge proceeded only after the expected head was updated.

PR #719 itself proved this standard: the slot initially expected for Algorithm Branch B became an operational standards documentation PR. Therefore Algorithm Branch naming must never be inferred from the next GitHub PR number.

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

## Standard 8 — Codex bot thread synchronization after correction commits

Background:

PR #720 cycle 5 saw a re-review report a "rediscovery" of P1 #1 and P1 #2 after a correction commit had already landed. A diagnostic cycle confirmed the correction was correctly applied at the new head, but the Codex bot threads still referenced the previous head and remained in an outdated state. The re-review reader interpreted the outdated thread alongside the new diff as evidence of recurrence.

Rule:

After a correction commit that resolves Codex P1/P2 findings:

1. The original Codex thread carries the `commit_id` and `line` of the OLD head.
2. GitHub may display this thread as outdated but not automatically resolved.
3. The new head must be explicitly referenced in subsequent review requests.
4. Reviewers should base diff inspection on the new head SHA, not on the outdated Codex thread's `original_line`.

Implementation:

- In correction completion reports, explicitly note: `Codex thread <id> outdated after head <new_sha> — please verify on new head diff`.
- In re-review requests, include the new head SHA in the first line of the request body.
- If a 5단 검토 reports "직접 diff 확인 결과 동일 재발견" but the head SHA is the new one, suspect Codex thread outdated state and trigger a diagnostic cycle before initiating any new correction commit.

Sentinel:

`test_codex_thread_outdated_detection` is an optional helper test, not enforced as a merge gate.

Proof case:

PR #720 cycle 5 — the diagnostic cycle confirmed that the correction was correctly applied at head `24dc8d092e61fed1782a2a7d621d623c8216cad9`. The Codex P1 #1 and P1 #2 threads remained outdated, pointing at `commit_id=025f403deaf95000bf9b356931e8d71ae21115d5` (the original first head) and `original_line=409` / `original_line=158`. The reviewer's auto-fetch surfaced these outdated comments alongside the new diff, producing an apparent "동일 재발견" report. Final outcome: PR #720 merged with merge SHA `e838543b44cfa03ab31893304547f7218de44b82`.

## Standards 9–12 — separate per-standard files

Standards 9 and later are codified as separate files under
`docs/operating-standards/`:

- Standard 9 — Dataset Integrity Fail-Closed: `docs/operating-standards/standard-09-dataset-integrity.md`
  (codified by GitHub PR #728; absorbs Standard 6 coverage fail-closed).
- Standard 10 — Strict Policy Base Drift: `docs/operating-standards/standard-10-strict-policy-base-drift.md`
  (codified by GitHub PR #729; metric threshold freeze, label guide SemVer
  bump, before/after comparison, policy drift report).
- Standard 11 — AB simulation variant distinctness (metric-only): proven in
  PR #724/#726, enforced in evaluation PR sentinels.
- Standard 12 — Honest Reporting Pattern: `docs/operating-standards/standard-12-honest-reporting.md`
  (codified by GitHub PR #728).

CI guards `scripts/ci/check_standard_09.py`, `scripts/ci/check_standard_10.py`,
and `scripts/ci/check_standard_12.py` enforce these. The evaluation PR template
`.github/PULL_REQUEST_TEMPLATE/eval_pr.md` applies Standards 1–12 as a checklist.

## Required pre-merge evaluation PR checklist

Every future evaluation PR must satisfy the following before merge:

- [ ] PR status and latest head SHA are stated in the PR body.
- [ ] Evidence correction commits are reflected across the full PR body.
- [ ] `expected_head_sha` squash merge is used.
- [ ] Algorithm Branch label is separate from the GitHub PR number.
- [ ] Multiset/weighted invariant sentinels are present when aggregates are used.
- [ ] Coverage fail-closed sentinel is present (Standard 9 — coverage_report 12 fields).
- [ ] Stratified composition sentinel is present when A/B or sampled evaluation is used.
- [ ] Honest reporting pattern is satisfied (Standard 12 — expected_vs_observed, delta).
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

These standards apply starting with the next evaluation PR after this standards PR, including Algorithm Branch B-2 / GitHub PR #721+ and all later `scripts/eval/*` changes.
