# Card1 EvalSet Spec (단계 6.5.5 Day 1)

## 1. 500건 분포 (± 5% 허용 오차)

| intent_type | 목표 | 비율 | 허용 |
|-------------|-----:|-----:|-----:|
| REQUEST | 150 | 30% | ±8 |
| QUESTION | 75 | 15% | ±4 |
| REPORT | 100 | 20% | ±5 |
| COMMAND | 75 | 15% | ±4 |
| NO_ACTION | 50 | 10% | ±3 |
| 복합 다중 액션 | 25 | 5% | ±2 |
| boundary | 25 | 5% | ±2 |
| **합계** | **500** | 100% | — |

복합 다중 액션과 boundary 는 위 intent_type 분포 내부에서 slice_tags(`complex_multi`, `boundary`)로 식별. 합계 500은 sample 총 개수이지 sum of subset이 아니다.

## 2. source 구분

| source | 정의 | 용도 |
|--------|------|------|
| `synthetic_gold` | 알고리즘 팀이 작성한 시드 샘플 | 라벨 기준 정렬 + smoke fixture |
| `beta_log_redacted` | 사용자 동의 기반 베타 로그 익명화 | 실제 분포 반영 |
| `internal_log_redacted` | 내부 사용자 로그 익명화 | 도메인 어휘 커버리지 |
| `adjudicated_boundary` | 라벨러 합의 보류 → 조정 후 확정 | 어려운 케이스 + boundary 태그 |

## 3. raw_text 금지 정책

EvalSet 어디에서도 다음 5개 키를 **저장 금지**:

1. `raw_text`
2. `original_text`
3. `plain_text`
4. `user_text`
5. `source_text`

대신 다음 2개만 보관:

- `text_redacted` — 21종 표준 토큰으로 치환된 본문
- `raw_digest16` — 원문의 `sha256:<16 hex>` (중복 방지 목적, 복원 불가)

검사: `scripts/evalset/check_no_raw_text.py` — JSONL 의 모든 key 를 재귀 검사.

## 4. CI Gate 6개 명세

| # | Gate | 스크립트 | 실패 코드 |
|---|------|----------|----------|
| 1 | raw_text 금지 키 검출 | `check_no_raw_text.py` | `RAW_TEXT_STORED` |
| 2 | digest16 형식 검사 | `check_digest16.py` | `DIGEST16_INVALID` |
| 3 | PII 잔존 검사 | `check_pii_leak.py` | `PII_LEAK` |
| 4 | 분포 검사 | `check_distribution.py` | `DISTRIBUTION_BELOW_MIN` |
| 5 | 합의도 검사 | `compute_agreement.py` | `AGREEMENT_BELOW_THRESHOLD` |
| 6 | JSON Schema 검증 | `validate_card1_schema.py` | `SCHEMA_INVALID` |

모든 Gate 는 exit code 0 (PASS) / 1 (FAIL) 반환. CI 에서 6개 모두 PASS 해야 머지 가능.

## 5. 6.5.6 판정 기준 (다음 단계 평가 기준)

500건 EvalSet 재평가 후 다음 조건을 모두 만족할 때만 다음 단계 진행을 검토:

- intent_type_accuracy ≥ 0.90
- normalized_action_f1 ≥ 0.90
- false_deadline_rate ≤ 0.02
- no_action_fp_rate ≤ 0.03
- auto_apply_accuracy ≥ 0.98
- schema_valid_rate ≥ 0.98
- verifier_error_with_auto_apply = 0
- PII leak count = 0
- 분포 ±5% 이내

(이 PR 의 6.5.5 Day 1 는 평가 인프라 봉인 단계이며 위 기준에 도달하기 위한 사전 작업이다.)

## 6. 합의도 기준 (annotator_count ≥ 2)

라벨러 2인이 라벨링한 sample 의 합의도 (Cohen κ 또는 정확률) 기준:

| 항목 | 기준 |
|------|-----:|
| intent_type | ≥ 0.85 |
| deadline_type | ≥ 0.80 |
| auto_apply_allowed | ≥ 0.95 |
| PII leak 비율 | = 0 |

기준 미달 시 해당 sample 은 `label_status=adjudicated` 단계로 송부되어 조정자(arbiter)가 최종 판정. 조정 완료 시 `label_status=gold_reviewed` 로 승격.
