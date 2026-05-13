# Card1 Labeling Guide (단계 6.5.5 Day 1)

## 1. 목적

카드 1 (intent / action / deadline / material 추출) 평가 데이터의 라벨링 기준을 일치시킨다.
- 라벨러 합의도(intent ≥ 0.85 / deadline ≥ 0.80 / auto_apply ≥ 0.95)를 달성하기 위한 기준 정의.
- raw 입력 폐기 + digest16 보관 원칙 준수.
- 6.5.6 확장 평가까지 산정 외 작업 금지.

## 2. intent_type 5분류 정의

라벨러는 다음 5분류로만 표기한다. 4분류 운영 호환은 §3 참고.

| intent_type | 정의 | 예시 | 판정값 |
|-------------|------|------|--------|
| REQUEST | 사용자가 Butler에게 작업을 부탁 | "회의록 정리해서 공유해 주세요" | action_required=true, answer_required=true, auto_apply_allowed=false |
| COMMAND | 즉시 실행형 명령 (상하관계 / 파일 삭제 / 배포 / 외부 전송 / 권한 변경) | "지금 삭제하세요", "5시까지 배포하세요" | action_required=true, answer_required=false, auto_apply_allowed=false (risky_action) |
| REPORT | 사용자가 상태/결과/정보를 보고 | "PR 머지 완료했습니다", "이번 분기 실적 보고드립니다" | action_required=false, answer_required=false |
| NO_ACTION | Butler가 할 작업이 없음 (확인/참고/대기) | "오늘은 특별한 일정 없습니다" | action_required=false, answer_required=false |
| QUESTION | 답변만 필요, 외부 실행 없음 | "이번 PR 어떻게 처리됐어?" | action_required=false, answer_required=true, auto_apply_allowed=false |

판정 우선순위: NO_ACTION(부정형) > QUESTION(순수 의문문) > REPORT(보고형 어미) > COMMAND(상하관계/위험) > REQUEST(기본 요청).

## 3. 4분류 호환 매핑 (INTENT_COMPAT_MAP_V1)

운영 시스템(4분류: REPORT / REQUEST / COMMAND / NO_ACTION)과 호환 필요할 때 다음 매핑 사용.

| 원본 (5분류) | 운영 (4분류) | 비고 |
|--------------|--------------|------|
| REQUEST | REQUEST | 동일 |
| COMMAND | COMMAND | 동일 |
| REPORT | REPORT | 동일 |
| NO_ACTION | NO_ACTION | 동일 |
| QUESTION | NO_ACTION | 내부 보존 (answer_required=true 플래그로 구분) |

라벨 데이터는 원본 5분류로 저장하고, 운영 매핑은 호출 시점에 수행.

## 4. deadline_type 6종 정의

| deadline_type | 정의 | 예시 |
|---------------|------|------|
| NONE | 마감 표현 없음 | "회의록 정리해 주세요" |
| HARD | 절대 시점 / 기한 명시 | "금요일까지", "5월 10일까지", "오전 10시까지" |
| SOFT | 범위형 / 추정형 | "오늘 중", "이번 주 중", "다음 주 안에" |
| INQUIRY | 마감 질문 (실제 마감 아님) | "언제까지 가능하신가요?", "기한이 어떻게 되나요?" |
| URGENCY | 긴급 표현 (시점 미고정) | "지금 바로", "즉시", "ASAP" |
| CONDITION | 조건절 (시점 미고정) | "완료되면", "확인되면", "수정이 끝나면" |

deadline_is_actionable=true 는 HARD/SOFT 에만 부여. INQUIRY/URGENCY/CONDITION/NONE 은 false.

## 5. slice_tags 권장 목록

라벨러는 다음 태그 중 해당하는 것만 부여 (`^[a-z0-9_]+$` 패턴).

- 액션 복잡도: `complex_multi`, `boundary`
- deadline 유형: `deadline_hard`, `deadline_soft`, `deadline_inquiry`, `deadline_urgency`, `deadline_condition`
- 자료 유무: `material`, `no_material`
- 의도 부정: `negative`
- PII: `pii_redacted`
- 작업 영역: `document_task`, `code_task`, `server_task`, `report_status`, `answer_only`
- 위험 작업: `risky_action`, `external_send`, `deployment`, `file_delete`, `permission_change`

## 6. auto_apply_allowed 기준

기본값은 **false**. 다음 조건 중 하나라도 충족하면 **항상 false**:

1. risky_action 태그가 있다.
2. external_send / deployment / file_delete / permission_change 태그가 있다.
3. intent_type = COMMAND 이다.
4. intent_type = QUESTION 이다 (외부 실행 금지).
5. text_redacted 에 [SECRET] / [SERVER] / [ACCOUNT] 토큰이 포함된다.

위 조건이 없고 (intent_type ∈ {REQUEST, REPORT, NO_ACTION}) AND (deadline_type ∈ {NONE, HARD, SOFT}) AND (action_required 와 일관성 있을 때) 만 true 후보로 검토.

## 7. 라벨링 순서 6단계

1. **PII 확인** — text_redacted 안에 [EMAIL]/[PHONE]/[SERVER_IP]/[SECRET]/[CARD] 가 남아 있으면 reject (label_status=rejected_pii).
2. **intent_type** — 5분류 중 하나 선택 (§2).
3. **deadline_type** — 6종 중 하나 선택 (§4).
4. **action_required / answer_required / auto_apply_allowed** — §2 판정값 + §6 규칙 적용.
5. **slice_tags** — §5 목록에서 해당 항목 부여.
6. **boundary** — 라벨러가 망설인 케이스(다른 라벨러와 충돌 가능)는 `boundary` 태그 부여.

## 8. 예시 30개 (각 intent_type 별 6개)

### REQUEST (6)

| text_redacted | deadline_type | slice_tags |
|---|---|---|
| 회의록 정리해서 [TEAM] 공유해 주세요 | NONE | document_task, no_material |
| [DOCUMENT] 검토 후 금요일까지 회신 부탁드립니다 | HARD | document_task, deadline_hard, material |
| 오늘 중에 PR 리뷰 한 번 봐주세요 | SOFT | code_task, deadline_soft |
| 자료 확인되면 공유해 주세요 | CONDITION | material, deadline_condition |
| 이거 정리해서 보내 주세요 | NONE | document_task |
| 다음 주 월요일까지 견적서 정리 부탁드립니다 | HARD | document_task, deadline_hard |

### COMMAND (6)

| text_redacted | deadline_type | slice_tags |
|---|---|---|
| [SERVER] 인스턴스 즉시 재시작하세요 | URGENCY | server_task, risky_action, deployment |
| 해당 파일 삭제하세요 | NONE | file_delete, risky_action |
| 오늘 안에 권한 회수하시기 바랍니다 | SOFT | permission_change, risky_action |
| [DOCUMENT] 외부로 전송하세요 | NONE | external_send, risky_action |
| 5시까지 배포 진행하세요 | HARD | deployment, risky_action, deadline_hard |
| 지금 [BRANCH] 머지하세요 | URGENCY | code_task, risky_action |

### REPORT (6)

| text_redacted | deadline_type | slice_tags |
|---|---|---|
| 이번 분기 실적 보고드립니다 | NONE | report_status |
| [PR] 머지 완료했습니다 | NONE | code_task, report_status |
| 회의 결과 정리해서 공유드리겠습니다 | NONE | document_task, report_status |
| 클라이언트 미팅 결과 말씀드리겠습니다 | NONE | report_status |
| 자료 취합하여 월요일까지 전달드리겠습니다 | HARD | document_task, report_status, deadline_hard |
| 프로젝트 진행 현황 안내드립니다 | NONE | report_status |

### NO_ACTION (6)

| text_redacted | deadline_type | slice_tags |
|---|---|---|
| 오늘은 특별한 일정 없습니다 | NONE | negative |
| 해당 건 더 이상 진행하지 않아도 됩니다 | NONE | negative |
| 이번 회의는 취소되었습니다 | NONE | negative |
| 견적서는 제출하지 않아도 됩니다 | NONE | negative |
| 결정된 사항이 없어 추후 안내드리겠습니다 | NONE | negative, report_status |
| 확인된 내용이 없어 추가 안내 어렵습니다 | NONE | negative |

### QUESTION (6)

| text_redacted | deadline_type | slice_tags |
|---|---|---|
| 이번 [PR] 어떻게 처리됐어? | NONE | answer_only, code_task |
| 보고서 검토 언제까지 가능하신가요? | INQUIRY | answer_only, deadline_inquiry |
| 마감이 언제인가요? | INQUIRY | answer_only, deadline_inquiry |
| [DOCUMENT] 어디에 있는지 알려줘 | NONE | answer_only, document_task |
| 다음 미팅이 언제죠? | INQUIRY | answer_only, deadline_inquiry |
| 누가 담당인가요? | NONE | answer_only |

## 9. 금지 규칙

- raw_text 저장 금지. text_redacted + raw_digest16 만 보관.
- PII 잔존 샘플은 gold 승격 금지. label_status=rejected_pii.
- 라벨러 추측 deadline 금지. text_redacted 에 표현 없으면 deadline_type=NONE.
- production candidate 판정은 6.5.6 이전 금지.
- LoRA / 모델 변경은 6.5.5 범위 외.

## 10. 의미-라벨 일관성 보강 규칙 (Day 8 옵션 C → Day 10 G23 v1)

알고리즘 팀 옵션 C 확정 (2026-05-12): 합성 시드의 패턴 재사용으로 인한 의미-라벨 충돌을 차단하기 위해 다음 규칙을 hard gate 로 운영한다 (CI Gate G23).

### 10.1 PURE_QUESTION 패턴 — REQUEST 금지

다음 어미가 본문에 포함되고 **행동동사 (§10.3)** 가 동반되지 않을 경우, `intent_type=QUESTION` 만 허용한다.

| 패턴 | 라벨 |
|------|------|
| 어떻게 되나요 / 언제인가요 / 누구인가요 / 어디인가요 | QUESTION + action_required=false + answer_required=true |

예시:
- "회사 주소가 어떻게 되나요?" → QUESTION (REQUEST 금지)
- "마감이 언제인가요?" → QUESTION + deadline_type=INQUIRY
- "회사 주소 정리해서 보내주세요" → REQUEST (행동동사 "보내주" 동반)

### 10.2 REPORT_FIXED 패턴 — REQUEST 금지

다음 어미가 본문에 포함되면 `intent_type=REPORT` 만 허용한다 (행동동사 무관).

| 패턴 | 라벨 |
|------|------|
| 완료했습니다 / 보고드립니다 / 안내드립니다 / 공유했습니다 / 전달했습니다 | REPORT + action_required=false |

### 10.3 행동동사 (action verb) 17종

REQUEST 판정 시 본문에 다음 중 하나가 있어야 한다. 없으면 §10.1 적용.

`보내`, `전달`, `공유`, `검토`, `작성`, `수정`, `제출`, `회신`, `업로드`, `확인 부탁`, `조율`, `해 주`, `부탁드립`, `보고 부탁`, `정리해`, `보내주`, `주실 수 있나요`

### 10.4 경계 패턴 — warning (라벨러 재검토 권장)

다음 패턴은 G23 가 warning 만 발행. fail 아님.

| 패턴 | 라벨 | 비고 |
|------|------|------|
| 가능한가요 / 확인 가능할까요 | REQUEST + 행동동사 없음 → AMBIGUOUS_REQUEST_PATTERN | QUESTION 도 가능 |
| 처리하겠습니다 | REPORT 또는 REQUEST → AMBIGUOUS_REPORT_PATTERN | 자발 행동 보고 |
| 처리하겠습니다 / 진행하겠습니다 / 전달드리겠습니다 | REPORT 또는 REQUEST → PROMISE_BOUNDARY_PATTERN (Day 10 G23 v1) | 약속/수행 경계, hard 승격 금지 |

### 10.5 자동 정정 (Day 8 환원 4건 사례)

Day 8 환원 27건 grep 전수 조사 결과 4건이 §10.1~§10.2 위반으로 자동 정정됨.

| sample_id | 본문 (요약) | 변경 |
|-----------|-------------|------|
| card1_200003 | "[PERSON] 회사 주소가 어떻게 되나요?" | REQUEST → QUESTION |
| card1_200024 | "프로젝트 마감이 언제인가요?" | REQUEST → QUESTION |
| card1_200005 | "[PR] 머지 완료했습니다" | REQUEST → REPORT |
| card1_200028 | "배포 결과는 추후 안내드립니다" | REQUEST → REPORT |

### 10.6 G22 / G23 hard / warning 분리 (Day 10 확정)

| 필드 / 패턴 | 단계 | 비고 |
|------|------|------|
| intent_type | HARD (G22) | Day 6 이후 |
| deadline_type | HARD (G22) | Day 6 이후 |
| auto_apply_allowed | HARD (G22) | Day 6 이후 |
| action_required | HARD (G22, Day 10 승격) | DUPLICATE_ACTION_REQUIRED_INCONSISTENCY |
| answer_required | WARNING (G22 v2) | 6.5.6 이후 결정 |
| PURE_QUESTION 어미 + REQUEST | HARD (G23) | §10.1 |
| REPORT_FIXED 어미 + REQUEST | HARD (G23) | §10.2 |
| AMBIGUOUS_REQUEST_PATTERN | WARNING (G23) | 가능한가요 등 |
| AMBIGUOUS_REPORT_PATTERN | WARNING (G23) | 처리하겠습니다 |
| PROMISE_BOUNDARY_PATTERN | WARNING (G23 v1, Day 10) | 진행/전달드리겠습니다, hard 승격 금지 |
