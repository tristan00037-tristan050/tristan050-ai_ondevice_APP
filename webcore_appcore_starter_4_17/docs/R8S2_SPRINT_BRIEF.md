# R8-S2 스프린트 개요

## 스프린트 정보

- **이름**: R8-S2 – On-device LLM Engine v1
- **기간**: 2025-12-09 ~ 2025-12-20 (예시)
- **목표 한 줄 요약**: LocalLLMEngineV1를 실제 온디바이스 추론 엔진으로 연결할 수 있는 첫 버전 구현

## 목표 (Goals)

1. **LocalLLMEngineV1 Stub → 실제 엔진 어댑터 계층으로 승격**
   - 현재 Stub 구현을 실제 온디바이스 추론 API(네이티브 모듈/로컬 WASM 등)에 연결할 수 있는 어댑터 계층 설계 및 구현

2. **SuggestEngine 모드 확장**
   - 엔진 모드: `'mock' | 'rule' | 'local-llm' | 'remote'` 형태로 정리
   - `EXPO_PUBLIC_ENGINE_MODE` 환경 변수로 엔진 모드 선택 가능

3. **Accounting HUD에서 LLM 모드로 동작하는 최소 경로 구현**
   - CS 도메인은 계속 Stub 모드 유지
   - Accounting HUD에서 LLM 모드 선택 시 온디바이스 추론 경로로 동작

4. **HUD 상단 상태바에 Engine 표시 개선**
   - 현재 엔진 모드 표시: `On-device LLM`, `On-device (Rule)`, `BFF(remote)` 등

## 범위 (Scope)

### App (A-09)

- **[A-09-1]** LocalLLMEngineV1 인터페이스 및 컨텍스트 타입 정의
  - `LLMContext`, `LLMResponse` 타입 정의
  - 입력·출력 타입을 도메인-범용 형태로 정리

- **[A-09-2]** LocalLLMEngineV1 실제 온디바이스 엔진 어댑터 구현
  - 온디바이스 추론 API(네이티브 모듈/로컬 WASM 등)에 대한 어댑터 계층
  - 더미 API 연동 포함 (실제 LLM 라이브러리 연동은 선택사항)

- **[A-09-3]** AccountingHUD에 LLM 모드 토글 및 상태바 Engine 표시 개선
  - `EXPO_PUBLIC_ENGINE_MODE=local-llm` 일 때 LLM 경로로 동작
  - 상태바에 현재 엔진 모드 표시

### Server (S-08)

- **[S-08-1]** OS Dashboard 응답에 engine_mode 집계 필드 추가
  - 뷰 또는 쿼리 수준에서 engine_mode 집계
  - 최소 필드 수준 (예: `engine_mode: { local_llm: 10, rule: 5, remote: 2 }`)

- **[S-08-2]** Audit/로그에 engine_mode 기록 추가 (필요 시)
  - suggest 호출 시 사용된 엔진 모드 기록

### Web (W-09)

- **[W-09-1]** OS Dashboard에 Engine Mode 카드/슬롯 추가
  - 현재 값 N/A 또는 Stub 상태로 자리만 확보
  - 실제 데이터 연동은 최소 수준

### Test (T-02)

- **[T-02-1]** SuggestEngine 모드별 동작 테스트
  - mock/rule/local-llm 모드별 동작 검증
  - 모드 전환 시 올바른 엔진 선택 확인

- **[T-02-2]** Mock 모드/LLM 모드 회귀 테스트
  - Mock 모드에서 여전히 네트워크 0/엔진 호출 0 유지
  - LLM 모드에서도 에러 가드 유지

## 비범위 (Non-goals)

1. **외부 LLM 벤더(클라우드 API)를 직접 호출하는 코드**
   - 온디바이스 추론만 대상으로 함

2. **특정 LLM 아키텍처/라이브러리(예: Llama, Phi 등)에 종속되는 구현**
   - 어댑터 계층을 통해 추상화하여 특정 라이브러리에 종속되지 않도록 설계

3. **CS 도메인 전체 LLM 전환**
   - 이번 스프린트에는 Accounting 도메인만 대상
   - CS는 계속 Stub 모드 유지

4. **DB 스키마 대규모 변경**
   - 필요 시 별도 스프린트로 진행

## Definition of Done

1. ✅ LocalLLMEngineV1가 실제로 "어떤 온디바이스 추론 API(또는 임시 더미)"를 호출하도록 연결
2. ✅ Accounting HUD에서 `EXPO_PUBLIC_ENGINE_MODE=local-llm` 일 때 LLM 경로로 동작
3. ✅ Mock 모드에서 여전히 네트워크 0/엔진 호출 0 유지
4. ✅ OS Dashboard에서 engine_mode 관련 슬롯/필드가 깨지지 않고 노출
5. ✅ 모든 테스트 통과 (기존 회귀 테스트 포함)

## 엔진 모드 플래그 고정

### EXPO_PUBLIC_ENGINE_MODE (환경 변수)

- `mock` → LocalRuleEngineV1Adapter + 더미 데이터
- `rule` → 기존 규칙 기반 엔진
- `local-llm` → LocalLLMEngineV1
- `remote` → BFF 기반 원격 엔진

### LocalLLMEngineV1 구현 원칙

1. **외부 네트워크 호출 금지** (온디바이스 추론만 가정)
2. **입력 타입**: `LLMContext` 안에 도메인/언어/유저 힌트 정도만 포함
3. **출력 타입**: `LLMResponse<{ suggestions: SuggestItem[]; explanation?: string; }>`

### Mock 모드 불변 조건

`EXPO_PUBLIC_DEMO_MODE=mock` 일 때:
- 어떤 엔진 모드 설정이든 실제로는 로컬 규칙 + 더미 데이터로만 동작
- E2E 테스트의 "네트워크 0" 조건 유지

## 참고 문서

- [R8S1_SPRINT_BRIEF.md](./R8S1_SPRINT_BRIEF.md) - 이전 스프린트 개요
- [R8S1_IMPLEMENTATION_GUIDE.md](./R8S1_IMPLEMENTATION_GUIDE.md) - 구현 가이드
- [R8S2_TICKETS.md](./R8S2_TICKETS.md) - 상세 티켓 목록

