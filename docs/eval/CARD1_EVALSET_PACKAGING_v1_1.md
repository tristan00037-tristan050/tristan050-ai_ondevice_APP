# Card 1 EvalSet v1_1 패키징 (Day 10, 6.5.5+ 종료)

## 1. 패키지 파일
- `tests/fixtures/card1_evalset_v1_1_500.jsonl` (500건)
- `tests/fixtures/card1_evalset_v1_gold.jsonl` (Day 5 gold 30건, 변경 없음)

## 2. 분포 결과 (의미 우선)

| intent_type | 건수 |
|---|---|
| REQUEST | 181 |
| QUESTION | 77 |
| REPORT | 110 |
| COMMAND | 72 |
| NO_ACTION | 60 |

| label_status | 건수 |
|---|---|
| gold_reviewed | 110 |
| gold_v1 | 60 |
| adjudicated | 100 |
| draft | 230 |

| 부가 지표 | 값 |
|---|---|
| boundary slice_tag | 47 (9.4%) |
| auto_apply_allowed | 27 (5.4%) |

## 3. 분포 정당화 (필수 문구)

> 분포는 목표값과 일부 차이가 있으나, 의미 라벨 정합성과 안전 라벨 품질을
> 우선하여 강제 재분류하지 않았다. 6.5.6 평가는 이 최종 분포 기준으로 수행한다.

## 4. CI Gate 통과 결과 (G1~G23)

| Gate | 결과 |
|---|---|
| G1 raw_text | ok=true (0건) |
| G2 digest16 | ok=true |
| G3 PII leak | ok=true (0건) |
| G4 distribution | ok=true |
| G5 합의도 | intent rate 0.93 / deadline 1.0 / auto 0.96 |
| G6 schema | ok=true |
| G7 evidence consistency | ok=true |
| G8~G16 label consistency | ok=true |
| G16 token distribution | ok=true |
| G17~G21 adjudication | ok=true |
| G22 v1 (action_required hard 승격) | ok=true (warning 0) |
| G22 v2 strict | ok=true (warning 0) |
| G23 v1 (PROMISE_BOUNDARY warning) | violation 0, warning 2 (PROMISE_BOUNDARY) |

## 5. action_required hard 승격 (Day 10)

조건 충족:
1. G22 strict warning_count = 0
2. G23 hard violation = 0
3. auto_apply=true 27건 모두 action_required=true
4. duplicate-group action_required 충돌 0건

→ HARD_FIELDS 에 `action_required` 추가, fail_class `DUPLICATE_ACTION_REQUIRED_INCONSISTENCY` 신설.

`answer_required` 는 6.5.6 이후 결정 (warning 유지).

## 6. fixture lineage
Day 6 500건 확장 → Day 7 분포 조정 → Day 8 옵션 C → Day 9 adjudication → Day 10 v1_1 패키징.

## 7. 6.5.6 입력 파일
`tests/fixtures/card1_evalset_v1_1_500.jsonl` 만 사용.

## 8. 금지 사항 (재확인)
- raw_text 저장 금지
- LoRA / 모델 변경 금지
- production candidate 판정 금지 (6.5.6 D mode 이후)
- answer_required hard 승격 금지 (Day 10 시점)
- 분포 강제 재분류 금지
