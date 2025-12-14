# R9-S2 스프린트 개별 티켓

이 문서의 티켓들은 Jira/Linear/노션 등에 바로 복사하여 사용할 수 있습니다.

---

## 0. 공통 · 스프린트 준비 티켓

### [R9S2-00] R9-S2 브랜치 생성 및 공통 스프린트 세팅

**설명**

R9-S2 스프린트용 브랜치 생성 및 기본 환경 세팅

기준선/원칙을 레포/보드에 명시

**할 일**

- `git checkout main && git pull`
- `git switch -c r9-s2-cs-llm`
- `docs/R9S2_SPRINT_BRIEF.md`, `R9S2_TICKETS.md` 스프린트 위키에 링크
- 보드 컬럼/레이블 세팅 (예: `engine:local-llm`, `domain:cs`, `type:app/server/service-core/test`)

**Acceptance Criteria**

- [ ] `r9-s2-cs-llm` 브랜치 생성 및 원격에 푸시
- [ ] 스프린트 보드에 R9-S2용 필터/레이블 세팅
- [ ] 스프린트 설명에 "CS 도메인 온디바이스 LLM 연동, 회계/OS 코어 구조 변경 금지" 원칙 명시

**가드레일**

- 회계/기존 OS/HUD 코어 구조 변경 금지
- `DEMO_MODE=mock`일 때는 `ENGINE_MODE`와 관계없이 네트워크 0 유지
- 'remote' 모드는 이번 스프린트에서 타입/플래그 정의까지만, 실제 원격 호출 구현은 포함하지 않음

**우선순위**: P0

---

## 1. App (A-11) 티켓

### [R9S2-A11-1] CsHUD에 SuggestEngine 통합

**설명**

CsHUD에서 SuggestEngine 계층을 사용하도록 통합

Accounting HUD와 동일한 패턴으로 엔진 모드별 분기 처리

**할 일**

- `packages/app-expo/src/ui/CsHUD.tsx` 수정:
  - `getSuggestEngine()` 함수 호출
  - `suggestWithEngine()` 함수 사용
  - 엔진 모드별 분기 처리 (Mock/Rule/Local-LLM)
- 상태바에 엔진 모드 표시:
  - `Engine: On-device LLM`, `Engine: On-device (Rule)` 등
- Mock 모드에서는 네트워크 요청 없이 더미 데이터만 사용

**Acceptance Criteria**

- [ ] CsHUD에서 `getSuggestEngine()` 호출 및 엔진 모드별 분기 처리
- [ ] 상태바에 현재 엔진 모드가 정확히 표시됨
- [ ] Mock 모드에서는 여전히 네트워크 0 유지 (E2E 테스트 통과)
- [ ] Accounting HUD와 동일한 엔진 선택 로직 재사용

**참고 파일**

- `packages/app-expo/src/ui/CsHUD.tsx`
- `packages/app-expo/src/hud/engines/index.ts`
- `packages/app-expo/src/ui/AccountingHUD.tsx` (참고)

**우선순위**: P0

**의존성**: 없음

---

### [R9S2-A11-2] CS 전용 LLM 컨텍스트 타입 정의

**설명**

CS 도메인 특화 LLM 입력 컨텍스트 및 응답 타입 정의

Accounting과 분리된 도메인별 타입 구조 유지

**할 일**

- `packages/app-expo/src/hud/engines/types.ts` 또는 별도 파일에 다음 타입 추가:
  - `CsLLMContext` 인터페이스:
    - `customerInquiry: string` (고객 문의 내용)
    - `ticketHistory?: CsTicket[]` (이전 티켓 히스토리)
    - `domain: 'cs'`
    - `language?: string`
    - `userHints?: Record<string, any>`
  - `CsLLMResponse` 타입:
    - `suggestions: CsResponseSuggestion[]` (응답 추천 목록)
    - `summary?: string` (상담 요약)
    - `explanation?: string` (추천 이유)
  - `CsResponseSuggestion` 인터페이스:
    - `response: string` (제안 응답 텍스트)
    - `confidence?: number`
    - `category?: string`
- JSDoc 주석으로 각 타입의 용도 설명

**Acceptance Criteria**

- [ ] `CsLLMContext`, `CsLLMResponse`, `CsResponseSuggestion` 타입이 정의되어 있음
- [ ] 타입이 CS 도메인 특화 형태로 설계되어 있음
- [ ] Accounting 타입과 분리되어 있음
- [ ] TypeScript 타입 체크 통과

**참고 파일**

- `packages/app-expo/src/hud/engines/types.ts`
- `packages/app-expo/src/hud/cs-api.ts` (CsTicket 타입 참고)

**우선순위**: P0

**의존성**: 없음

---

### [R9S2-A11-3] LocalLLMEngineV1 CS 도메인 어댑터 구현

**설명**

LocalLLMEngineV1가 CS 도메인 컨텍스트를 처리할 수 있도록 어댑터 구현

Accounting과 동일한 어댑터 패턴 재사용

**할 일**

- `packages/app-expo/src/hud/engines/localLLMEngineV1.ts` 수정:
  - CS 컨텍스트를 LLM 입력 형식으로 변환하는 로직 추가
  - LLM 출력을 CS 응답 형식으로 변환하는 로직 추가
  - 도메인별 분기 처리 (`domain === 'cs'` vs `domain === 'accounting'`)
- CS 전용 어댑터 함수 구현:
  - `adaptCsContextToLLMInput(context: CsLLMContext): LLMRequest`
  - `adaptLLMOutputToCsResponse(output: LLMResponse): CsLLMResponse`
- Accounting 어댑터와 동일한 패턴 유지

**Acceptance Criteria**

- [ ] CS 컨텍스트 → LLM 입력 변환 함수가 동작함
- [ ] LLM 출력 → CS 응답 변환 함수가 동작함
- [ ] Accounting 어댑터와 동일한 패턴으로 구현됨
- [ ] 도메인별 분기 처리가 올바르게 동작함
- [ ] Mock 모드에서는 더미 CS 응답 반환

**참고 파일**

- `packages/app-expo/src/hud/engines/localLLMEngineV1.ts`
- `packages/app-expo/src/hud/engines/types.ts`

**우선순위**: P0

**의존성**: [R9S2-A11-2]

---

## 2. Server (S-10) 티켓

### [R9S2-S10-1] CS 도메인 Audit 이벤트에 engine_mode 기록

**설명**

CS 티켓 생성/응답 시 사용된 엔진 모드를 audit 이벤트에 기록

Accounting과 동일한 audit 이벤트 구조 재사용

**할 일**

- `packages/bff-accounting/src/routes/cs-tickets.ts` 또는 CS 관련 라우트 수정:
  - CS 티켓 생성/응답 시 `engine_mode` 필드를 payload에 추가
  - `auditLog()` 호출 시 engine_mode 포함
- CS audit 이벤트 테이블/뷰에 engine_mode 필드 확인 (필요 시 마이그레이션)
- OS Dashboard에서 CS 엔진 모드 집계 시 audit 이벤트 활용

**Acceptance Criteria**

- [ ] CS 티켓 생성/응답 시 audit 이벤트에 `engine_mode` 필드가 기록됨
- [ ] Accounting audit 이벤트와 동일한 구조로 기록됨
- [ ] OS Dashboard에서 CS 엔진 모드 집계가 가능함
- [ ] 기존 audit 이벤트 구조에 영향 없음

**참고 파일**

- `packages/bff-accounting/src/routes/cs-tickets.ts`
- `packages/bff-accounting/src/routes/suggest.ts` (Accounting 참고)
- `packages/data-pg/migrations/` (필요 시)

**우선순위**: P1

**의존성**: [R9S2-A11-1]

---

### [R9S2-S10-2] CS OS Dashboard에 엔진 모드 집계 추가 (선택)

**설명**

CS OS Dashboard API에 엔진 모드 집계 필드 추가

기존 OS Dashboard 구조 확장

**할 일**

- `packages/bff-accounting/src/routes/cs-os-dashboard.ts` 수정:
  - CS audit 이벤트에서 engine_mode 집계 쿼리 추가
  - 응답에 `engine_mode` 필드 포함
- 최소 필드 수준 (예: `engine_mode: { local_llm: 5, rule: 3, mock: 0 }`)
- 기존 OS Dashboard 구조 유지

**Acceptance Criteria**

- [ ] CS OS Dashboard API 응답에 `engine_mode` 필드가 포함됨
- [ ] 각 엔진 모드별 사용 횟수가 집계됨
- [ ] 기존 응답 구조에 영향 없음
- [ ] 테스트 통과

**참고 파일**

- `packages/bff-accounting/src/routes/cs-os-dashboard.ts`
- `packages/bff-accounting/src/routes/os-dashboard.ts` (Accounting 참고)

**우선순위**: P2

**의존성**: [R9S2-S10-1]

---

## 3. Service-Core (SC-10) 티켓

### [R9S2-SC10-1] CS + LocalLLMEngineV1 연동용 도메인 서비스 인터페이스 정의

**설명**

CS 도메인에서 LLM 엔진을 사용하기 위한 도메인 서비스 인터페이스 정의

Accounting 패턴 재사용

**할 일**

- `packages/service-core-cs/src/domain/`에 CS LLM 관련 인터페이스 추가:
  - `CsLLMService` 인터페이스 정의
  - `suggestCsResponse(context: CsLLMContext): Promise<CsLLMResponse>` 메서드
- 도메인별 분리 유지 (accounting과 cs 분리)

**Acceptance Criteria**

- [ ] `CsLLMService` 인터페이스가 정의되어 있음
- [ ] CS 도메인 특화 메서드가 포함됨
- [ ] Accounting 서비스와 분리되어 있음
- [ ] TypeScript 타입 체크 통과

**참고 파일**

- `packages/service-core-cs/src/domain/csLLMService.ts` (신규)
- `packages/service-core-accounting/src/` (참고)

**우선순위**: P1

**의존성**: [R9S2-A11-2]

---

### [R9S2-SC10-2] CS LLM 도메인 서비스 구현 (Stub)

**설명**

CS LLM 도메인 서비스 구현 (초기에는 Stub)

실제 LLM 연동은 다음 스프린트로

**할 일**

- `packages/service-core-cs/src/domain/csLLMService.ts` 구현:
  - `CsLLMService` 인터페이스 구현
  - 초기에는 Stub 구현 (더미 응답 반환)
  - 엔진 모드별 분기 처리 준비
- `packages/service-core-cs/src/index.ts`에 export 추가

**Acceptance Criteria**

- [ ] `CsLLMService` 구현체가 동작함
- [ ] Stub 모드에서 더미 CS 응답 반환
- [ ] 엔진 모드별 분기 처리 구조 준비됨
- [ ] 다음 스프린트에서 실제 LLM 연동 가능한 구조

**참고 파일**

- `packages/service-core-cs/src/domain/csLLMService.ts`
- `packages/service-core-cs/src/index.ts`

**우선순위**: P1

**의존성**: [R9S2-SC10-1]

---

## 4. Test (T-04) 티켓

### [R9S2-T04-1] CS 도메인 엔진 모드별 동작 테스트

**설명**

CS 도메인에서 Mock/Rule/Local-LLM 모드별 동작 검증

Mock 모드 네트워크 0 회귀 테스트 포함

**할 일**

- `packages/app-expo/e2e/` 또는 `packages/app-expo/test/`에 테스트 파일 추가:
  - Mock 모드 CS HUD 테스트
  - Rule 모드 CS HUD 테스트
  - Local-LLM 모드 CS HUD 테스트
- 각 모드별 응답 형식 검증
- Mock 모드 네트워크 0 검증 (기존 `mock-no-network.spec.mjs` 확장)

**Acceptance Criteria**

- [ ] Mock/Rule/Local-LLM 모드별 CS HUD 테스트가 모두 통과함
- [ ] Mock 모드에서 네트워크 요청 0건 확인
- [ ] 각 모드별 응답 형식이 올바름
- [ ] 기존 Accounting 테스트에 영향 없음

**참고 파일**

- `packages/app-expo/e2e/cs-engine-mode.spec.mjs` (신규)
- `packages/app-expo/e2e/mock-no-network.spec.mjs` (확장)

**우선순위**: P0

**의존성**: [R9S2-A11-1], [R9S2-A11-3]

---

### [R9S2-T04-2] CS SuggestEngine 통합 테스트

**설명**

CsHUD에서 SuggestEngine 통합 및 엔진 모드 전환 테스트

CS 컨텍스트 → LLM 입력 변환 검증

**할 일**

- `packages/app-expo/test/` 또는 통합 테스트 파일에 추가:
  - CsHUD에서 엔진 모드 전환 테스트
  - CS 컨텍스트 → LLM 입력 변환 검증
  - LLM 출력 → CS 응답 변환 검증
  - 엔진 모드별 CS 응답 품질 검증 (기본)

**Acceptance Criteria**

- [ ] CsHUD에서 엔진 모드 전환이 올바르게 동작함
- [ ] CS 컨텍스트 → LLM 입력 변환이 정확함
- [ ] LLM 출력 → CS 응답 변환이 정확함
- [ ] 각 엔진 모드별 CS 응답이 올바른 형식으로 반환됨

**참고 파일**

- `packages/app-expo/test/cs-suggest-engine.test.ts` (신규)
- `packages/app-expo/src/hud/engines/localLLMEngineV1.ts`

**우선순위**: P1

**의존성**: [R9S2-A11-3]

---

## 우선순위 요약

- **P0 (필수)**: R9S2-00, A-11-1, A-11-2, A-11-3, T-04-1
- **P1 (권장)**: S-10-1, SC-10-1, SC-10-2, T-04-2
- **P2 (선택)**: S-10-2

## 의존성 그래프

```
R9S2-00 (공통 세팅)
  ↓
R9S2-A11-2 (CS 타입 정의)
  ↓
R9S2-A11-3 (CS 어댑터 구현)
  ↓
R9S2-A11-1 (CsHUD 통합)
  ↓
R9S2-T04-1 (엔진 모드별 테스트)
  ↓
R9S2-T04-2 (통합 테스트)

R9S2-A11-1
  ↓
R9S2-S10-1 (CS Audit 기록)
  ↓
R9S2-S10-2 (CS OS Dashboard 집계)

R9S2-A11-2
  ↓
R9S2-SC10-1 (CS LLM 서비스 인터페이스)
  ↓
R9S2-SC10-2 (CS LLM 서비스 구현)
```

## 가드레일 (재확인)

1. **회계/OS 코어 구조 변경 금지**
   - Accounting HUD, BFF, Service Core 변경 없음
   - OS Dashboard 기존 구조 유지 (CS 카드만 확장)
   - 기존 테스트 실패 시 즉시 롤백

2. **Mock 모드 네트워크 0 불변 조건**
   - `DEMO_MODE=mock`일 때는 `ENGINE_MODE`와 관계없이 네트워크 0 유지
   - E2E 테스트 실패 시 즉시 수정

3. **엔진 모드 정책 일관성**
   - Accounting과 CS에서 동일한 엔진 모드 선택 로직
   - `EXPO_PUBLIC_ENGINE_MODE` 환경 변수로 통일

4. **Remote 모드 제한**
   - 'remote' 모드는 이번 스프린트에서 타입/플래그 정의까지만
   - 실제 원격 호출 구현은 포함하지 않음

