# R10-S1 PR 설명

## 개요

R10-S1: On-device LLM Backend v0.5 + Domain LLM 추상화 + LLM Usage Audit v0

온디바이스 LLM Stub을 Domain-독립적인 Backend 인터페이스로 추상화하고, DomainLLMService 인터페이스를 도입하여 회계/CS/HR/법무/보안 등이 같은 LLM 패턴을 공유하도록 하며, CS HUD에서 LLM 사용에 대한 최소 Audit 이벤트를 기록하는 v0 구조를 구현했습니다.

## 주요 변경사항

### 1. EngineMeta 확장 및 엔진 메타 구현
- `EngineMeta` 타입에 `id`, `stub`, `variant`, `supportedDomains` 필드 추가
- `LocalLLMEngineV1`: `id: 'local-llm'`, `stub: true`, `variant: 'local-llm-v0'`
- `LocalRuleEngineV1Adapter`: `id: 'local-rule-v1'`, `stub: false`, `variant: 'rule-v1'`
- HUD 상태바, OS Dashboard, 로그에서 Stub/실제 모델 구분 가능

### 2. DomainLLMService 인터페이스 도입
- `packages/service-core-cs/src/domain/domainLLMService.ts` 생성
- `csLLMService`가 `DomainLLMService<CsLLMContext, CsLLMResponse>` 구현
- 추후 AccountingLLMService, HrLLMService 등이 동일 패턴 사용 가능

### 3. 도메인 핸들러 레지스트리 패턴
- `domainHandlers.ts`: `DomainHandler` 인터페이스 및 레지스트리 함수 정의
- `domainHandlersRegistry.ts`: CS/Accounting 핸들러 등록 예시
- `LocalLLMEngineV1`에서 레지스트리 사용하여 if/switch 폭발 방지

### 4. LLM Usage Audit v0
- `packages/app-expo/src/hud/telemetry/llmUsage.ts`: Telemetry 유틸 구현
- `CsHUD`에서 `suggestion_shown` 이벤트 전송
- `packages/bff-accounting/src/routes/os-llm-usage.ts`: `/v1/os/llm-usage` POST 라우트 구현
- 텍스트 원문 없이 메타/통계만 수집 (Playbook 규칙 준수)

### 5. 데이터베이스 연결 개선
- `data-pg`: Pool lazy initialization 구현 (DATABASE_URL 로드 문제 해결)
- `service-core-cs`: `data-pg`의 `exec` 함수 사용

### 6. BFF 스키마 파일 경로 수정
- `approvals.ts`, `exports.ts`, `reconciliation.ts`, `suggest.ts`: ROOT_DIR 경로 수정 (`../../../../`)

### 7. 프론트엔드 에러 핸들링 개선
- `cs-api.ts`: 에러 응답 본문을 콘솔에 로깅하도록 개선

### 8. 문서
- `R10S1_SPRINT_BRIEF.md`: 스프린트 개요
- `R10S1_TICKETS.md`: 티켓 상세
- `R10S1_DESIGN_NOTES.md`: 설계 고려사항
- `AI_ONDEVICE_ENTERPRISE_PLAYBOOK.md`: LLM 버전/게이트웨이/Usage 예시 추가

## QA 결과

### Mock + Rule 모드
- CS HUD 탭 진입 시 `/v1/cs/tickets` 200 ✅
- 티켓 리스트 정상 표시 ✅
- "요약/추천" → `[Rule] "Mock CS Ticket 1" 문의에 대한 규칙 기반 Mock 응답입니다.` ✅
- Network HTTP/WS = 0 ✅
- 콘솔: LLM Usage가 `[MOCK] ...` 형태로 출력 ✅

### Mock + local-llm 모드
- CS HUD 탭 진입 시 `/v1/cs/tickets` 200 ✅
- 티켓 리스트 정상 표시 ✅
- "요약/추천" → 약 1.8초 후 LLM 스타일 Stub 응답 ✅
- Network HTTP/WS = 0 ✅
- 콘솔: `[MOCK] LLM usage event`에 `engineId: 'local-llm'`, `engineVariant: 'local-llm-v0'`, `engineStub: true` 포함 ✅

### Live + local-llm 모드
- `/v1/cs/tickets` 200 ✅
- `/v1/os/llm-usage` 204 ✅
- BFF 로그: `{"type":"llm_usage", "engineId":"local-llm", "engineVariant":"local-llm-v0", ...}` JSON 한 줄 출력 ✅

## 타입 체크

- R10-S1 변경사항에서 신규 타입 에러 없음 확인
- 기존 타입 에러는 별도 티켓으로 분리 예정

## 다음 스프린트 백로그

- DomainLLMService 공통 패키지로 승격
- LLM Usage 이벤트에 `eventType` 추가 (shown/used_as_is/edited/rejected/error)
- Remote LLM Gateway 설계 (실구현은 뒤로)
- LLM 응답 후처리 Hook 설계

## 관련 이슈

- R9-S2: CS 도메인 SuggestEngine 연동
- R10-S1: On-device LLM Backend v0.5 + Domain LLM 추상화 + LLM Usage Audit v0

