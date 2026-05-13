# CI Gate Registry (G1~G21 통합 명세)

단계 6.5.5 Day 1~5 누적 CI Gate 21개. 모두 fail-closed 원칙.

## Gate 1~6 — Day 1 정형 검증

| Gate | 이름 | 적용 | fail_class | exit |
|:----:|------|------|------------|:----:|
| G1 | check_no_raw_text | 모든 sample | RAW_TEXT_STORED | 1 |
| G2 | check_digest16 | 모든 sample | DIGEST16_INVALID | 1 |
| G3 | check_pii_leak | userlog_redacted | PII_LEAK / JSON_PARSE_ERROR | 1 |
| G4 | check_distribution | 모든 sample | DISTRIBUTION_BELOW_MIN / JSON_PARSE_ERROR | 1 |
| G5 | compute_agreement | annotator_a/b 또는 final_gold | NO_COMPARABLE_PAIRS / BELOW_AGREEMENT_THRESHOLD / FINAL_GOLD_FIELD_MISSING | 1 |
| G6 | validate_card1_schema | 모든 sample | SCHEMA_INVALID | 1 |

## Gate 7 — Day 2 evidence consistency

| Gate | 이름 | 적용 | fail_class |
|:----:|------|------|------------|
| G7 | check_evidence_consistency | label_status ∈ ENFORCED_STATUSES | EVIDENCE_NOT_IN_TEXT / EVIDENCE_MISSING / GOLD_MISSING_WHEN_ENFORCED / UNKNOWN_LABEL_STATUS / JSON_PARSE_ERROR |

## Gate 8~16 — Day 3 라벨 일관성 + 토큰 분포

| Gate | 이름 | 조건 | fail_class |
|:----:|------|------|------------|
| G8 | annotator missing | double_labeled + a/b 누락 | ANNOTATOR_MISSING_WHEN_DOUBLE_LABELED |
| G9 | reviewer missing | approved/gold_reviewed/gold_v1 + reviewer 누락 | REVIEWER_MISSING_WHEN_APPROVED |
| G10 | primary_intent ≠ gold.intent_type | enforced status | PRIMARY_INTENT_MISMATCH_GOLD |
| G11 | deadline_type ↔ deadline 정합 | enforced status | DEADLINE_TYPE_INCONSISTENT_WITH_OBJECT |
| G12 | NO_ACTION + actions ≠ [] | enforced status | NO_ACTION_HAS_NONEMPTY_ACTIONS |
| G13 | auto_apply=true + status ∉ APPROVED_LIKE_STATUSES | 전체 | AUTO_APPLY_REQUIRES_APPROVED_LIKE |
| G14 | userlog + text ≠ null | userlog source | USERLOG_TEXT_NOT_NULL |
| G15 | evidence 불일치 + APPROVED_LIKE_STATUSES | (adjudicated 포함) | EVIDENCE_INCONSISTENT_WHEN_APPROVED |
| G16 | check_token_distribution | userlog ≥ min | TOKEN_DISTRIBUTION_EMPTY (BLOCK) / SKEW (WARNING) / LOW_VARIETY (WARNING) |

## Gate 17~21 — Day 4~5 adjudication 정합

| Gate | 이름 | 조건 | fail_class |
|:----:|------|------|------------|
| G17 | adjudicator missing | adjudicated/gold_v1 | ADJUDICATOR_MISSING_WHEN_ADJUDICATED |
| G18 | final_gold missing | adjudicated/gold_v1 | FINAL_GOLD_MISSING_WHEN_ADJUDICATED |
| G19 | disagreement_resolution missing | annotator 불일치 + adjudicated/gold_v1 | APPROVED_WITHOUT_DISAGREEMENT_RESOLUTION |
| G20 | auto_apply_reasoning missing | top-level OR final_gold auto_apply=true | AUTO_APPLY_REASONING_MISSING |
| G21 | auto_apply mismatch | adjudicated/gold_v1 + top ≠ final_gold | AUTO_APPLY_MISMATCH |

## 정착 시점

| Day | 정착 Gate | PR |
|-----|-----------|----|
| Day 1 | G1~G6 | #702 |
| Day 2 | G7 | #703 |
| Day 3 | G8~G16 | #704 |
| Day 4~5 | G17~G21 | #705/#706 |

## fail-closed 원칙 적용 흔적

| Gate | 정정 이력 |
|------|----------|
| G5 | PR #702 P1 — NO_COMPARABLE_PAIRS 도입 (rate=1.0 자동 통과 결함 정정) |
| G5 | PR #705 P2-A — FINAL_GOLD_FIELD_MISSING 도입 (silent fallback 결함 정정) |
| G3 | PR #702 P2 — parse error fail-closed 정정 |
| G4 | PR #704 P1-A — parse error fail-closed 정정 |
| G15 | PR #704 P1-B — adjudicated 포함 (G13 동일 상수) |
| G16 | PR #703 P1 — TOKEN_DISTRIBUTION_EMPTY 도입 |
| G20 | PR #705 P2-B — final_gold 우회 차단 |
| G21 | PR #705 P2-C — 신규 (top vs final_gold 정합성) |

## 결함 발견 이력

| PR | 봇 발견 | 알고리즘 팀 발견 | 합계 |
|----|--------:|----------------:|----:|
| #702 | 2 | 0 | 2 |
| #703 | 2 | 0 | 2 |
| #704 | 2 | 2 | 4 |
| #705 | 2 | 1 | 3 |
| **합계** | **8** | **3** | **11** |
