# CI Gate Registry (G1~G23 통합 명세, Day 10 v1_1 패키징 확정)

단계 6.5.5 Day 1~10 누적 CI Gate 23개. 모두 fail-closed 원칙.

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

## Gate 22 — Day 6 데이터 일관성 (신규)

| Gate | 이름 | 조건 | fail_class |
|:----:|------|------|------------|
| G22 | duplicate label consistency | 같은 raw_digest16 + 핵심 라벨 불일치 | DUPLICATE_LABEL_INCONSISTENCY / GOLD_V1_DUPLICATE_CONFLICT / REVIEWED_DUPLICATE_CONFLICT |

G22 명세 (알고리즘 팀 확정 2026-05-14, Day 10 v1 확장):
- Scope: 모든 row
- Group key: raw_digest16
- Hard fields v1 (Day 6): intent_type / deadline_type / auto_apply_allowed
- Hard fields Day 10 추가: **action_required** (승격) — DUPLICATE_ACTION_REQUIRED_INCONSISTENCY
- Warning fields (Day 7+): answer_required (6.5.6 이후 결정 보류)
- Priority: gold_v1 > gold_reviewed > adjudicated > double_labeled > draft
- 예외 허용: 금지 (context_digest16 도입 후만 — Day 7+)
- 각 violation 그룹에 recommended_truth_source (priority 최상위 sample_id) 출력

### Day 10 hard 승격 조건 (action_required)
1. G22 strict 모드 warning_count = 0
2. G23 hard violation = 0
3. auto_apply=true row 100% action_required=true
4. duplicate-group action_required 충돌 = 0
모두 충족 시 hard 승격 (Day 9 strict 통과 후 Day 10 진행).

### answer_required hard 승격 (6.5.6 이후 보류)

## G22 v2 strict trigger (Day 7 정착, 알고리즘 팀 옵션 2 확정)

### 정의

G22 v2 WARNING_FIELDS (`action_required` / `answer_required`) 는 기본 모드에서
관측용 warning 이지만, strict mode (`--fail-on-warning` 또는
`EVALSET_FAIL_ON_WARNING=1`) 에서는 fail-closed.

### strict mode 필수 적용 시점

| # | 시점 |
|---|------|
| 1 | Day 10 최종 EvalSet 패키징 |
| 2 | 6.5.6 production candidate 판정 |
| 3 | gold_v1 최종 패키징 |
| 4 | 모델 학습 handoff |
| 5 | release branch 생성 |

### fail_class

`DUPLICATE_WARNING_FIELD_INCONSISTENCY` (통합)

### 우선순위

CLI 옵션 (`--fail-on-warning`) > 환경변수 (`EVALSET_FAIL_ON_WARNING=1`) > 기본값 (False)

## Gate 23 — Day 8 의미-라벨 일관성 (신규, 옵션 C)

| Gate | 이름 | 조건 | fail_class |
|:----:|------|------|------------|
| G23 | semantic label pattern guard | 모든 row text 패턴 매칭 | SEMANTIC_LABEL_PATTERN_VIOLATION |

G23 v1 명세 (알고리즘 팀 옵션 C 확정 2026-05-12, Day 10 옵션 1 통합 정정 2026-05-14):
- Scope: 모든 row
- Hard fail 1: PURE_QUESTION_MISLABELED_AS_REQUEST — `어떻게 되나요/언제인가요/누구인가요/어디인가요` + REQUEST + action_required=true + 행동동사 없음
- Hard fail 2: REPORT_MISLABELED_AS_REQUEST — `완료했습니다/보고드립니다/안내드립니다/공유했습니다/전달했습니다` + REQUEST
- Warning 1: AMBIGUOUS_REQUEST_PATTERN — `가능한가요/확인 가능할까요` + REQUEST + 행동동사 없음 (라벨러 재검토 권장)
- Warning 2: PROMISE_BOUNDARY_PATTERN — `처리하겠습니다/진행하겠습니다/전달드리겠습니다` + REPORT/REQUEST 경계 (수행 의사·약속·경계 표현, hard 승격 금지)
- 제거 (옵션 1): AMBIGUOUS_REPORT_PATTERN / WARNING_PATTERNS_REPORT → `처리하겠습니다` 는 PROMISE_BOUNDARY 단독 매칭
- 라벨 가이드 §10 참고

## 정착 시점

| Day | 정착 Gate | PR |
|-----|-----------|----|
| Day 1 | G1~G6 | #702 |
| Day 2 | G7 | #703 |
| Day 3 | G8~G16 | #704 |
| Day 4~5 | G17~G21 | #705/#706 |
| Day 6 | G22 (데이터 일관성) | #707 |
| Day 7 | G22 v2 strict mode | #709 |
| Day 8 | G23 (의미-라벨 일관성) | #710 |
| Day 9 | adjudication 100건 + G5 합의도 | #711 |
| Day 10 | G22 action_required hard 승격 + G23 v1 + v1_1 패키징 | #712 |

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
