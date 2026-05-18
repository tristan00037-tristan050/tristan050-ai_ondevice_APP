# Internal Alpha Authoritative Measurement Plan

Status: MEASURED_ONLY_PLAN
Scope: Card 1 Internal Alpha authoritative measurement protocol
Base evidence: PR #734 merge `343c1f6f402abe47bcabb2328d8c6dd9e9e353c6`
Reference advisory head: `48ffca8fe0d8ba88cba4a38061ba65bb104faa25`

## 1. Purpose

This plan defines how Card 1 Internal Alpha will collect an authoritative manual suggestion precision measurement without changing labels, model weights, prompts, thresholds, or deployment gates.

The plan exists because the current manual_suggestion_precision proxy is not authoritative enough for the next-stage judgment. Internal Alpha may run only with:

- auto_apply OFF
- manual review only
- no automatic action execution
- no model replacement
- no LoRA / fine-tuning
- no prompt strengthening for Branch B-2R

## 2. Proxy vs authoritative separation

Proxy measurement:

- deterministic reviewer-simulation proxy
- useful for readiness analysis
- not valid as next-stage decision evidence
- must not be represented as human reviewer precision

Authoritative measurement:

- independent human review on selected Internal Alpha samples
- reviewer calibration round before final rating
- disagreement adjudication
- Cohen's kappa or equivalent agreement statistic
- final manual_suggestion_precision computed from adjudicated labels

## 3. Measurement flow

1. Sample selection
   - build 150 recommended samples or 100 fallback samples
   - use digest16/sample_id only in evidence
   - do not store raw plaintext in measurement artifacts

2. Reviewer assignment
   - recommended: 3 reviewers
   - minimum: 2 reviewers
   - every sample receives at least 2 independent ratings
   - residual A4 and ambiguous request/report samples are oversampled

3. Reviewer calibration round
   - 10 to 20 samples
   - train reviewers on useful / irrelevant / unsafe / needs_edit definitions
   - adjust reviewer guide language only, not gold labels or model behavior

4. Independent rating
   - reviewer sees redacted sample metadata, model suggestion, digest IDs, and allowed context markers
   - reviewer does not see raw plaintext
   - reviewer selects one label: useful, irrelevant, unsafe, needs_edit

5. Disagreement adjudication
   - disagreement cases are routed to adjudication
   - majority vote preferred for 3 reviewers
   - for 2 reviewers, disagreement requires adjudicator or forced review meeting

6. Agreement calculation
   - compute Cohen's kappa for 2-reviewer setup
   - compute pairwise kappa or Fleiss-style aggregate for 3-reviewer setup
   - kappa threshold: >= 0.70

7. Authoritative MSP calculation
   - compute manual_suggestion_precision from adjudicated labels
   - success threshold: MSP >= 0.80 and kappa >= 0.70
   - confidence interval is reported with sample count

8. Decision boundary
   - this PR does not decide the next stage
   - this PR only enables Internal Alpha authoritative measurement

## 4. MSP and kappa interpretation

The authoritative path requires both usefulness precision and reviewer agreement. A high MSP with low agreement is not trusted. A high agreement with low MSP means users consistently found the suggestions not useful enough.

Required decision gate:

```text
manual_suggestion_precision_authoritative >= 0.80
cohens_kappa_or_equivalent >= 0.70
```

## 5. Standard 12-B~J integration areas

This plan explicitly preserves:

- proxy vs authoritative separation
- quantitative reversal reporting
- readiness gate integrity
- privacy audit reporting
- honest limitation disclosure
- no immediate metric contract v2.1.0 bump
- no upper-stage readiness claim
- no auto_apply exposure
- no prompt/model/threshold change

## 6. Raw data and privacy boundary

Evidence files must contain only:

- sample_id
- digest16
- redaction class metadata
- reviewer_id_digest
- rating labels
- adjudication outcome
- aggregate counts

Evidence files must not contain:

- raw plaintext
- original user input
- raw document contents
- company names
- person names
- email addresses
- file paths
- server addresses
- model prompt text copied from user data

## 7. Allowed output status

Allowed:

- INTERNAL_ALPHA_MEASUREMENT_PLAN
- MEASURED_ONLY_PLAN
- ALPHA_PROMOTION_CONTEXT

Disallowed wording is controlled by the validation script and must not appear in evidence files.

## 8. Next step

After this plan PR is merged, a separate Internal Alpha collection execution PR can collect authoritative ratings using this protocol. Next-stage judgment remains blocked until authoritative MSP and kappa thresholds are measured and independently reviewed.
