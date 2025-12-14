# R10-S2 티켓 상세

## 공통

### [R10S2-00] 브랜치 생성 및 공통 세팅

**설명:**
R10-S2 스프린트 브랜치 생성 및 초기 문서 작성

**할 일:**
- [ ] `r10-s2-domain-llm-service` 브랜치 생성
- [ ] `docs/R10S2_SPRINT_BRIEF.md` 생성
- [ ] `docs/R10S2_TICKETS.md` 생성

**Acceptance Criteria:**
- 브랜치가 생성되고 원격에 푸시됨
- 스프린트 문서가 작성됨

**참고 파일:**
- `docs/R10S2_SPRINT_BRIEF.md`
- `docs/R10S2_TICKETS.md`

**우선순위:** P0

---

## Service-Core

### [R10S2-SC12-1] DomainLLMService 공통 패키지 승격

**설명:**
`DomainLLMService` 인터페이스를 `service-core-common` 패키지로 이동하여, 회계/CS/HR/법무/보안이 같은 패턴으로 움직이도록 강제

**할 일:**
- [ ] `packages/service-core-common/src/llm/domainLLMService.ts` 생성
- [ ] `DomainLLMService<TContext, TResponse>` 인터페이스 정의
- [ ] `postProcess?` 메서드 추가
- [ ] `packages/service-core-cs/src/domain/csLLMService.ts` 수정
  - 기존 `domainLLMService.ts` import 제거
  - `@appcore/service-core-common/llm/domainLLMService` import 추가
- [ ] 타입 체크 및 빌드 확인

**Acceptance Criteria:**
- `DomainLLMService`가 `service-core-common`에 정의됨
- `csLLMService`가 공통 인터페이스를 import하고 구현
- 타입 체크 통과
- 기존 기능 동작 확인

**참고 파일:**
- `packages/service-core-common/src/llm/domainLLMService.ts` (신규)
- `packages/service-core-cs/src/domain/csLLMService.ts`
- `packages/service-core-cs/src/domain/domainLLMService.ts` (삭제 예정)

**우선순위:** P0

**의존성:**
- [R10S2-00] 브랜치 생성

---

## App

### [R10S2-A13-1] LLM Usage eventType 추가 및 CsHUD 연동

**설명:**
LLM Usage 이벤트에 `eventType` 필드를 추가하여, Manual Touch Rate, 추천 사용률, 수정률, 거부률을 측정 가능하도록 함

**할 일:**
- [ ] `packages/app-expo/src/hud/telemetry/llmUsage.ts` 수정
  - `LlmUsageEventType` 타입 정의 (shown/accepted_as_is/edited/rejected/error)
  - `LlmUsageEvent`에 `eventType` 필드 추가
  - `sendLlmUsageEvent` 함수 시그니처 업데이트
- [ ] `packages/app-expo/src/ui/CsHUD.tsx` 수정
  - 추천 패널 표시 시: `eventType: 'shown'`
  - "그대로 사용" 버튼 클릭 시: `eventType: 'accepted_as_is'`
  - 수정 후 전송 시: `eventType: 'edited'`
  - 추천 닫기/무시 시: `eventType: 'rejected'`
  - 엔진 에러 시: `eventType: 'error'`
- [ ] 타입 체크 및 빌드 확인

**Acceptance Criteria:**
- `LlmUsageEventType` 타입이 정의됨
- `LlmUsageEvent`에 `eventType` 필드가 추가됨
- `CsHUD`에서 각 액션별로 적절한 `eventType` 전송
- Mock 모드에서 콘솔 로그에 `eventType` 포함
- Live 모드에서 BFF로 `eventType` 전송

**참고 파일:**
- `packages/app-expo/src/hud/telemetry/llmUsage.ts`
- `packages/app-expo/src/ui/CsHUD.tsx`

**우선순위:** P0

**의존성:**
- [R10S2-00] 브랜치 생성

---

## BFF

### [R10S2-S12-1] Remote LLM Gateway 라우트 설계

**설명:**
HUD가 외부 LLM을 직접 호출하지 않고, OS Gateway를 통해 나가는 레일을 확보하기 위한 라우트 설계

**할 일:**
- [ ] `packages/bff-accounting/src/routes/os-llm-gateway.ts` 생성
  - POST `/v1/os/llm/proxy` 라우트 정의
  - `requireTenantAuth` / `requireRole('operator')` 적용
  - 현재는 501 Not Implemented 반환
  - 요청 body 타입 정의 (domain, engineId, prompt, metadata)
- [ ] `packages/bff-accounting/src/index.ts` 수정
  - `os-llm-gateway` 라우트 등록
- [ ] 타입 체크 및 빌드 확인

**Acceptance Criteria:**
- POST `/v1/os/llm/proxy` 라우트가 정의됨
- `requireTenantAuth` / `requireRole('operator')` 적용됨
- 현재는 501 Not Implemented 반환
- 라우트가 BFF에 등록됨

**참고 파일:**
- `packages/bff-accounting/src/routes/os-llm-gateway.ts` (신규)
- `packages/bff-accounting/src/index.ts`

**우선순위:** P1

**의존성:**
- [R10S2-00] 브랜치 생성

---

## Engine

### [R10S2-E05-1] LLM 응답 후처리 Hook 연동

**설명:**
개인정보/금지 표현/정책 위반 응답을 공통 레이어에서 필터링할 수 있는 Hook을 `DomainLLMService`와 `LocalLLMEngineV1`에 연동

**할 일:**
- [ ] `DomainLLMService` 인터페이스에 `postProcess?` 메서드 추가 (이미 [R10S2-SC12-1]에서 포함)
- [ ] `packages/app-expo/src/hud/engines/local-llm.ts` 수정
  - `LocalLLMEngineV1.suggest`에서 `domainService.postProcess` 호출
  - 후처리 결과를 `recordAudit`에 전달
- [ ] `packages/service-core-cs/src/domain/csLLMService.ts` 수정
  - `postProcess?` 메서드 구현 (기본 구현: 개인정보 마스킹 등)
- [ ] 타입 체크 및 빌드 확인

**Acceptance Criteria:**
- `DomainLLMService`에 `postProcess?` 메서드가 추가됨
- `LocalLLMEngineV1`에서 `postProcess` 호출
- `csLLMService`에 기본 후처리 구현
- 타입 체크 통과

**참고 파일:**
- `packages/service-core-common/src/llm/domainLLMService.ts`
- `packages/app-expo/src/hud/engines/local-llm.ts`
- `packages/service-core-cs/src/domain/csLLMService.ts`

**우선순위:** P1

**의존성:**
- [R10S2-SC12-1] DomainLLMService 공통 패키지 승격

---

## Test

### [R10S2-T05-1] LLM Usage eventType 테스트

**설명:**
LLM Usage 이벤트의 `eventType`이 각 액션별로 올바르게 전송되는지 테스트

**할 일:**
- [ ] Mock 모드에서 각 `eventType` 전송 확인
- [ ] Live 모드에서 BFF로 `eventType` 전송 확인
- [ ] BFF 로그에서 `eventType` 포함 여부 확인

**Acceptance Criteria:**
- Mock 모드에서 콘솔 로그에 `eventType` 포함
- Live 모드에서 BFF 로그에 `eventType` 포함
- 각 액션별로 올바른 `eventType` 전송

**참고 파일:**
- `packages/app-expo/src/ui/CsHUD.tsx`
- `packages/app-expo/src/hud/telemetry/llmUsage.ts`
- `packages/bff-accounting/src/routes/os-llm-usage.ts`

**우선순위:** P0

**의존성:**
- [R10S2-A13-1] LLM Usage eventType 추가

---

## 의존성 다이어그램

```
[R10S2-00] 브랜치 생성
    │
    ├─→ [R10S2-SC12-1] DomainLLMService 공통 패키지 승격
    │       │
    │       └─→ [R10S2-E05-1] LLM 응답 후처리 Hook 연동
    │
    ├─→ [R10S2-A13-1] LLM Usage eventType 추가
    │       │
    │       └─→ [R10S2-T05-1] LLM Usage eventType 테스트
    │
    └─→ [R10S2-S12-1] Remote LLM Gateway 라우트 설계
```

## 우선순위 요약

- **P0 (필수):**
  - [R10S2-00] 브랜치 생성
  - [R10S2-SC12-1] DomainLLMService 공통 패키지 승격
  - [R10S2-A13-1] LLM Usage eventType 추가
  - [R10S2-T05-1] LLM Usage eventType 테스트

- **P1 (중요):**
  - [R10S2-S12-1] Remote LLM Gateway 라우트 설계
  - [R10S2-E05-1] LLM 응답 후처리 Hook 연동

- **P2 (선택):**
  - 실제 온디바이스 모델 PoC (local-llm-v1)
  - LLM Usage 대시보드 스키마 초안

