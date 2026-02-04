# R8-S2 스프린트 개별 티켓

이 문서의 티켓들은 Jira/Linear/노션 등에 바로 복사하여 사용할 수 있습니다.

---

## 0. 공통 · 스프린트 준비 티켓

### [R8S2-00] R8-S2 브랜치 생성 및 공통 스프린트 세팅

**설명**

R8-S2 스프린트용 브랜치 생성 및 기본 환경 세팅

기준선/원칙을 레포/보드에 명시

**할 일**

- `git checkout main && git pull`
- `git switch -c r8-s2-ondevice-llm`
- `docs/R8S2_SPRINT_BRIEF.md`, `R8S2_TICKETS.md` 스프린트 위키에 링크
- 보드 컬럼/레이블 세팅 (예: `engine:local-llm`, `domain:accounting`, `type:app/server/web/test`)

**Acceptance Criteria**

- [ ] `r8-s2-ondevice-llm` 브랜치 생성 및 원격에 푸시
- [ ] 스프린트 보드에 R8-S2용 필터/레이블 세팅
- [ ] 스프린트 설명에 "온디바이스 LLM 엔진 탑재, CS는 계속 Stub" 원칙 명시

**우선순위**: P0

---

## 1. App (A-09) 티켓

### [R8S2-A09-1] LocalLLMEngineV1 인터페이스 및 컨텍스트 타입 정의

**설명**

LocalLLMEngineV1가 사용할 입력·출력 타입을 도메인-범용 형태로 정리

LLMContext, LLMResponse 타입 정의

**할 일**

- `packages/app-expo/src/hud/engines/types.ts`에 다음 타입 추가:
  - `LLMContext` 인터페이스 (도메인/언어/유저 힌트 포함)
  - `LLMResponse<T>` 제네릭 타입
  - `LLMRequest` 인터페이스
- `LocalLLMEngineV1` 클래스에 타입 적용
- JSDoc 주석으로 각 타입의 용도 설명

**Acceptance Criteria**

- [ ] `LLMContext`, `LLMResponse`, `LLMRequest` 타입이 정의되어 있음
- [ ] 타입이 도메인-범용 형태로 설계되어 있음 (accounting/cs 모두 사용 가능)
- [ ] TypeScript 타입 체크 통과

**참고 파일**

- `packages/app-expo/src/hud/engines/types.ts`
- `packages/app-expo/src/hud/engines/localLLMEngineV1.ts`

**우선순위**: P0

**의존성**: 없음

---

### [R8S2-A09-2] LocalLLMEngineV1 실제 온디바이스 엔진 어댑터 구현

**설명**

LocalLLMEngineV1 Stub을 실제 온디바이스 추론 API에 연결할 수 있는 어댑터 계층 구현

더미 API 연동 포함 (실제 LLM 라이브러리 연동은 선택사항)

**할 일**

- `LocalLLMEngineV1` 클래스에 실제 추론 메서드 구현
- 온디바이스 추론 API 어댑터 인터페이스 정의:
  - `OnDeviceLLMAdapter` 인터페이스
  - 더미 구현체 `DummyLLMAdapter` (임시)
- `LocalLLMEngineV1.suggest()` 메서드에서 어댑터 호출
- 외부 네트워크 호출 금지 (온디바이스 추론만 가정)

**Acceptance Criteria**

- [ ] `OnDeviceLLMAdapter` 인터페이스가 정의되어 있음
- [ ] `DummyLLMAdapter` 구현체가 동작함
- [ ] `LocalLLMEngineV1.suggest()`가 어댑터를 통해 추론 결과를 반환함
- [ ] 네트워크 요청이 발생하지 않음 (온디바이스만)
- [ ] Mock 모드에서는 여전히 더미 데이터만 반환

**참고 파일**

- `packages/app-expo/src/hud/engines/localLLMEngineV1.ts`
- `packages/app-expo/src/hud/engines/adapters/OnDeviceLLMAdapter.ts` (신규)
- `packages/app-expo/src/hud/engines/adapters/DummyLLMAdapter.ts` (신규)

**우선순위**: P0

**의존성**: [R8S2-A09-1]

---

### [R8S2-A09-3] AccountingHUD에 LLM 모드 토글 및 상태바 Engine 표시 개선

**설명**

AccountingHUD에서 `EXPO_PUBLIC_ENGINE_MODE=local-llm` 일 때 LLM 경로로 동작하도록 수정

상태바에 현재 엔진 모드 표시 개선

**할 일**

- `packages/app-expo/src/hud/engines/index.ts`의 `getSuggestEngine()` 함수 수정:
  - `EXPO_PUBLIC_ENGINE_MODE` 환경 변수 읽기
  - `local-llm` 모드일 때 `LocalLLMEngineV1` 반환
- `AccountingHUD.tsx`의 상태바에 엔진 모드 표시:
  - `On-device LLM`, `On-device (Rule)`, `BFF(remote)` 등
- 엔진 모드별 동작 확인

**Acceptance Criteria**

- [ ] `EXPO_PUBLIC_ENGINE_MODE=local-llm` 일 때 `LocalLLMEngineV1` 사용
- [ ] 상태바에 현재 엔진 모드가 정확히 표시됨
- [ ] Mock 모드에서는 여전히 로컬 규칙 엔진 사용 (불변 조건)
- [ ] CS HUD는 계속 Stub 모드 유지

**참고 파일**

- `packages/app-expo/src/hud/engines/index.ts`
- `packages/app-expo/src/ui/AccountingHUD.tsx`
- `packages/app-expo/App.tsx`

**우선순위**: P0

**의존성**: [R8S2-A09-2]

---

## 2. Server (S-08) 티켓

### [R8S2-S08-1] OS Dashboard 응답에 engine_mode 집계 필드 추가

**설명**

OS Dashboard API 응답에 engine_mode 집계 필드 추가

뷰 또는 쿼리 수준에서 engine_mode 집계

**할 일**

- `packages/data-pg/migrations/`에 engine_mode 집계 뷰 추가 (필요 시)
- `packages/bff-accounting/src/routes/os-dashboard.ts` 수정:
  - engine_mode 집계 쿼리 추가
  - 응답에 `engine_mode` 필드 포함
- 최소 필드 수준 (예: `engine_mode: { local_llm: 10, rule: 5, remote: 2 }`)

**Acceptance Criteria**

- [ ] OS Dashboard API 응답에 `engine_mode` 필드가 포함됨
- [ ] 각 엔진 모드별 사용 횟수가 집계됨
- [ ] 기존 응답 구조(pilot, health, risk 등)에 영향 없음
- [ ] 테스트 통과

**참고 파일**

- `packages/bff-accounting/src/routes/os-dashboard.ts`
- `packages/data-pg/migrations/` (필요 시)

**우선순위**: P1

**의존성**: 없음

---

### [R8S2-S08-2] Audit/로그에 engine_mode 기록 추가 (필요 시)

**설명**

suggest 호출 시 사용된 엔진 모드를 audit 이벤트에 기록

**할 일**

- `packages/bff-accounting/src/routes/suggest.ts` 수정:
  - suggest 호출 시 `engine_mode` 필드를 payload에 추가
- `accounting_audit_events` 테이블의 payload에 engine_mode 포함
- OS Dashboard에서 engine_mode 집계 시 audit 이벤트 활용

**Acceptance Criteria**

- [ ] suggest 호출 시 audit 이벤트에 `engine_mode` 필드가 기록됨
- [ ] OS Dashboard에서 engine_mode 집계가 정확히 동작함
- [ ] 기존 audit 이벤트 구조에 영향 없음

**참고 파일**

- `packages/bff-accounting/src/routes/suggest.ts`
- `packages/data-pg/migrations/` (필요 시)

**우선순위**: P1

**의존성**: [R8S2-S08-1]

---

## 3. Web (W-09) 티켓

### [R8S2-W09-1] OS Dashboard에 Engine Mode 카드/슬롯 추가

**설명**

OS Dashboard에 Engine Mode 카드/슬롯 추가

현재 값 N/A 또는 Stub 상태로 자리만 확보

**할 일**

- `packages/ops-console/src/pages/os/OsDashboard.tsx` 수정:
  - Engine Mode 카드 추가
  - 현재 값은 N/A 또는 Stub로 표시
- 실제 데이터 연동은 최소 수준 (필요 시 S-08-1 결과 활용)

**Acceptance Criteria**

- [ ] OS Dashboard에 Engine Mode 카드가 표시됨
- [ ] 카드 툴팁에 "R8-S2 이후 실제 엔진 모드 집계 연동 예정" 등 설명 문구 포함
- [ ] 기존 카드 UI/데이터에 영향 없음

**참고 파일**

- `packages/ops-console/src/pages/os/OsDashboard.tsx`

**우선순위**: P1

**의존성**: 없음

---

## 4. Test (T-02) 티켓

### [R8S2-T02-1] SuggestEngine 모드별 동작 테스트

**설명**

SuggestEngine 모드별 동작 검증

mock/rule/local-llm 모드별 동작 확인

**할 일**

- `packages/app-expo/e2e/` 또는 `packages/app-expo/test/`에 테스트 파일 추가:
  - mock 모드 테스트
  - rule 모드 테스트
  - local-llm 모드 테스트
- 모드 전환 시 올바른 엔진 선택 확인
- 각 모드별 응답 형식 검증

**Acceptance Criteria**

- [ ] mock/rule/local-llm 모드별 테스트가 모두 통과함
- [ ] 모드 전환 시 올바른 엔진이 선택됨
- [ ] 각 모드별 응답 형식이 올바름

**참고 파일**

- `packages/app-expo/e2e/engine-mode.spec.mjs` (신규)
- `packages/app-expo/src/hud/engines/index.ts`

**우선순위**: P0

**의존성**: [R8S2-A09-3]

---

### [R8S2-T02-2] Mock 모드/LLM 모드 회귀 테스트

**설명**

Mock 모드/LLM 모드 회귀 테스트

네트워크 0, 에러 가드 유지 확인

**할 일**

- 기존 `mock-no-network.spec.mjs` 테스트 확장:
  - Mock 모드에서 여전히 네트워크 0 확인
  - LLM 모드에서도 에러 가드 유지 확인
- OS Dashboard API 가드 테스트 확장:
  - engine_mode 필드 검증 추가

**Acceptance Criteria**

- [ ] Mock 모드에서 여전히 네트워크 0/엔진 호출 0 유지
- [ ] LLM 모드에서도 에러 가드 유지
- [ ] 기존 회귀 테스트 모두 통과

**참고 파일**

- `packages/app-expo/e2e/mock-no-network.spec.mjs`
- `packages/bff-accounting/test/os-dashboard-guards.test.mjs`

**우선순위**: P0

**의존성**: [R8S2-A09-3], [R8S2-S08-1]

---

## 우선순위 요약

- **P0 (필수)**: A-09-1, A-09-2, A-09-3, T-02-1, T-02-2
- **P1 (권장)**: S-08-1, S-08-2, W-09-1

## 의존성 그래프

```
R8S2-00 (공통 세팅)
  ↓
R8S2-A09-1 (타입 정의)
  ↓
R8S2-A09-2 (어댑터 구현)
  ↓
R8S2-A09-3 (HUD 통합)
  ↓
R8S2-T02-1 (모드별 테스트)
  ↓
R8S2-T02-2 (회귀 테스트)

R8S2-S08-1 (OS Dashboard 집계)
  ↓
R8S2-S08-2 (Audit 기록)

R8S2-W09-1 (OS Dashboard 카드)
```

