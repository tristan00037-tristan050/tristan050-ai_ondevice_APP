# B-2G Over-extraction Guard Implementation (자문 5차 5.3)

## metadata
- source_pr: 732
- branch: B-2G
- patch_type: post_processing_over_extraction_guard
- verdict: MEASURED_ONLY

## 본질

B-2G 는 **post-processing guard** 다. prompt / model weight 를 변경하지
않고, 모델 출력(predictions)의 action 리스트를 출력 후 단계에서 필터한다.
zero-shot prompt + guard 구조 — Branch B-2R(recall 강화 prompt) 및
Branch F(LoRA) 는 사용하지 않는다.

## guard_decision(text) — 3 분기

| 결정 | 조건 | 처리 |
|---|---|---|
| `block` | REPORT 마커 ∧ ¬imperative, 또는 NO_ACTION 마커 | action 전체 제거 |
| `manual_suggestion` | QUESTION 패턴 | action 보존 + `manual_suggestion_allowed=True`, `auto_apply=False` |
| `keep` | 그 외 | action 보존 (변경 없음) |

## REPORT 패턴 (declarative 완료/공유 진술)

`공유드립니다 / 공유했습니다 / 완료했습니다 / 완료했어요 / 갱신했습니다 /
등록했습니다 / 반영했습니다 / 알려드리겠습니다 / 정리해 두 / 두었어요`

**A5-safety**: 마커는 declarative 현재/과거형으로 한정한다. 의도형
`공유드리려고 합니다 / 보고드리려고 합니다` 는 마커에서 **제외** — gold≥1
인 A5 케이스(card1_100078 "회의록 정리 후 공유드리려고 합니다")와 표면
동일하므로, 의도형까지 차단하면 A5 의 실제 gold action 을 손실한다.

imperative 요청 동반 시 (`해 주세요 / 부탁 / 바랍니다 / 주시기`) REPORT
차단을 보류한다 — "회의록 공유드립니다. 검토 부탁드려요" 같은 복합문에서
실제 요청 action 을 보호.

## QUESTION 패턴 (A3 보존)

`? / 나요 / 까요 / 어떻게 / 누가 / 무엇 / 언제 / 있을까요 / 가능한가요 /
되나요 / 끝났나요`

QUESTION 케이스(A3 product_equivalent)는 차단하지 않고 보존하되,
`manual_suggestion_allowed=True` + `auto_apply=False` 메타데이터를 부여한다.
자동 실행은 막되 사용자 가치(수동 제안)는 유지 — 자문 5차 5.4 정합.

> 자문 인계의 "QUESTION 패턴 차단" 과 "A3 보존" 은 표면상 상충한다.
> 성공 기준 "A3 32건 과차단 0건" 에 따라 QUESTION 은 **보존**으로
> 정합 처리한다 (auto_apply OFF 가 곧 over-classify 차단).

## NO_ACTION 마커

`참고만 / 확인만 / 정보 공유만 / 참고 바랍 / 참고용 / fyi` — 명시적
no-action 지시. 해당 시 action 차단.

**Codex P2 정정 — case-insensitive**: NO_ACTION_MARKER 는 `re.IGNORECASE`
flag 로 컴파일한다. 영어 마커 `fyi` 는 FYI / Fyi / fyi 모든 대소문자
변형을 매칭해야 한다 (이전엔 소문자만 매칭). 한국어 마커는 case 개념이
없어 flag 영향이 없다. 상세는 `regex_case_sensitivity_audit.md` 참조.

## guard 대상별 영향

| subtype | gold/pred | guard 영향 |
|---|---|---|
| A4 true_over_extraction | gold=0/pred≥1, REPORT | block (declarative 한정) |
| A3 product_equivalent | gold=0/pred≥1, QUESTION | manual_suggestion 보존 |
| A5 metric_contract_gap | gold≥1/pred≥1 | block 대상 아님 (imperative/의도형 보호) |

## 한계 (정직 보고)

text-only guard 는 다음을 안전 차단할 수 없다:
- "부탁드립니다" 형 A4 (7건) — 실제 요청과 표면 동일.
- "보고드리려고 합니다" 형 A4 (2건) — A5 card1_100078 과 표면 동일.

이 잔여 9건은 gold / metric contract review 영역이며 B-2G 범위 밖이다.
