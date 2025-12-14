# R9-S2 스프린트 개요

## 스프린트 정보

- **이름**: R9-S2 – CS Domain On-device LLM Integration
- **기간**: 2025-12-11 ~ 2025-12-25 (예시)
- **목표 한 줄 요약**: CS 도메인에 온디바이스 LLM 연동 (상담 요약/응답 추천), SuggestEngine 계층 재사용으로 Accounting/CS 동일 패턴 적용

## 배경

R9-S1까지 회계 + CS 도메인 v1이 OS/HUD/BFF/DB에 연결되었습니다. R8-S2에서 구현한 LocalLLMEngineV1 어댑터 계층이 Accounting HUD에서 동작 중이며, 이제 CS 도메인에도 동일한 온디바이스 LLM 기능을 적용하는 단계입니다.

## 목표 (Goals)

### Business Goals

1. **CS 도메인 온디바이스 LLM 기능 도입**
   - CS 상담 요약 자동 생성
   - CS 응답 추천 기능
   - 고객 문의에 대한 온디바이스 AI 응답 지원

2. **회계/CS 도메인 통합 엔진 아키텍처**
   - SuggestEngine 계층을 재사용하여 Accounting/CS가 동일 패턴으로 LLM 사용
   - 도메인 간 엔진 모드 정책 일관성 유지

### Technical Goals

1. **CS 도메인 SuggestEngine 통합**
   - CsHUD에서 SuggestEngine 계층 사용
   - Mock/Rule/Local-LLM/Remote 모드 정책을 CS에도 그대로 적용
   - Accounting HUD와 동일한 엔진 선택 로직 재사용

2. **CS 전용 LLM 컨텍스트 및 응답 타입 정의**
   - CS 도메인 특화 입력 컨텍스트 (고객 문의, 이전 대화 등)
   - CS 응답 추천 출력 형식 정의
   - Accounting과 분리된 도메인별 타입 구조 유지

3. **Mock 모드 네트워크 0 정책 유지**
   - CS 도메인에서도 Mock 모드 시 네트워크 요청 0건 보장
   - E2E 테스트 회귀 방어

## 범위 (Scope)

### In Scope

#### App (A-11)

- **[A-11-1]** CsHUD에 SuggestEngine 통합
  - CsHUD에서 `getSuggestEngine()` 사용
  - 엔진 모드별 분기 처리 (Mock/Rule/Local-LLM)
  - 상태바에 엔진 모드 표시

- **[A-11-2]** CS 전용 LLM 컨텍스트 타입 정의
  - `CsLLMContext` 타입 정의 (고객 문의, 티켓 히스토리 등)
  - `CsLLMResponse` 타입 정의 (응답 추천, 요약 등)

- **[A-11-3]** LocalLLMEngineV1 CS 도메인 어댑터 구현
  - CS 컨텍스트를 LLM 입력 형식으로 변환
  - LLM 출력을 CS 응답 형식으로 변환
  - Accounting과 동일한 어댑터 패턴 재사용

#### Server (S-10)

- **[S-10-1]** CS 도메인 Audit 이벤트에 engine_mode 기록
  - CS 티켓 생성/응답 시 사용된 엔진 모드 기록
  - Accounting과 동일한 audit 이벤트 구조 재사용

- **[S-10-2]** CS OS Dashboard에 엔진 모드 집계 추가 (선택)
  - CS 도메인별 엔진 모드 사용 통계
  - 기존 OS Dashboard 구조 확장

#### Test (T-04)

- **[T-04-1]** CS 도메인 엔진 모드별 동작 테스트
  - Mock/Rule/Local-LLM 모드별 CS HUD 동작 검증
  - Mock 모드 네트워크 0 회귀 테스트

- **[T-04-2]** CS SuggestEngine 통합 테스트
  - CsHUD에서 엔진 모드 전환 테스트
  - CS 컨텍스트 → LLM 입력 변환 검증

### Out of Scope

1. **회계/OS 코어 구조 변경 금지**
   - Accounting 도메인 기존 기능 변경 없음
   - OS Dashboard 기존 구조 유지 (CS 카드만 확장)

2. **실제 LLM 모델 연동**
   - 실제 LLM 라이브러리(예: llama.cpp) 연동은 별도 스프린트
   - 이번 스프린트는 어댑터 계층 및 인터페이스 구현에 집중

3. **CS 도메인 대규모 기능 확장**
   - 티켓 CRUD, 워크플로우 등은 별도 스프린트
   - 이번 스프린트는 LLM 연동에만 집중

4. **클라우드 LLM 호출**
   - Remote 모드는 인터페이스만 준비, 실제 구현은 별도

## 산출물 (Deliverables)

### App

- CsHUD에 SuggestEngine 통합 완료
- CS 전용 LLM 컨텍스트/응답 타입 정의
- LocalLLMEngineV1 CS 어댑터 구현

### Server

- CS Audit 이벤트에 engine_mode 기록
- CS OS Dashboard 엔진 모드 집계 (선택)

### Test

- CS 엔진 모드별 동작 테스트
- Mock 모드 네트워크 0 회귀 테스트
- CS SuggestEngine 통합 테스트

## 리스크 및 가드레일

### 리스크

1. **Accounting/CS 엔진 계층 공유 시 충돌 가능성**
   - **완화**: 도메인별 컨텍스트 타입 분리, 공통 인터페이스만 공유

2. **Mock 모드 네트워크 0 정책 위반 가능성**
   - **완화**: E2E 테스트로 자동 검증, T-04-1에서 회귀 방어

3. **CS 도메인 LLM 컨텍스트 설계 복잡도**
   - **완화**: Accounting 패턴 재사용, 최소 기능부터 단계적 확장

### 가드레일

1. **회계 도메인 기존 기능 변경 금지**
   - Accounting HUD, BFF, Service Core 변경 없음
   - 기존 테스트 실패 시 즉시 롤백

2. **Mock 모드 네트워크 0 불변 조건**
   - Mock 모드에서 HTTP/WS 요청 0건 보장
   - E2E 테스트 실패 시 즉시 수정

3. **엔진 모드 정책 일관성**
   - Accounting과 CS에서 동일한 엔진 모드 선택 로직
   - `EXPO_PUBLIC_ENGINE_MODE` 환경 변수로 통일

## Definition of Done

1. **CsHUD에서 SuggestEngine 계층 사용**
   - `getSuggestEngine()` 호출 및 엔진 모드별 분기 처리
   - 상태바에 엔진 모드 표시

2. **CS 전용 LLM 타입 정의 및 어댑터 구현**
   - `CsLLMContext`, `CsLLMResponse` 타입 정의
   - LocalLLMEngineV1 CS 어댑터 구현

3. **Mock 모드 네트워크 0 유지**
   - E2E 테스트 통과
   - 수동 QA 확인

4. **CS Audit 이벤트에 engine_mode 기록**
   - CS 티켓 생성/응답 시 엔진 모드 기록
   - OS Dashboard에서 집계 가능

5. **테스트 커버리지**
   - CS 엔진 모드별 동작 테스트 통과
   - Mock 모드 회귀 테스트 통과
   - CS SuggestEngine 통합 테스트 통과

6. **문서화**
   - R9-S2 스프린트 브리프 및 티켓 문서 작성
   - CS LLM 연동 아키텍처 문서 (선택)

## 다음 스프린트 힌트

R9-S2 완료 후 자연스러운 다음 단계:

1. **실제 LLM 모델 연동** (R9-S3 또는 R10-S1)
   - llama.cpp, onnxruntime 등 실제 LLM 라이브러리 연동
   - 모델 로딩 및 추론 파이프라인 구현

2. **CS 도메인 기능 확장** (R10-S1)
   - 티켓 CRUD, 워크플로우, 상태 관리
   - CS 전용 OS Dashboard 확장

3. **엔진 모드별 성능 비교** (R10-S2)
   - 엔진 모드별 추론 시간/정확도 비교 리포트
   - 성능 메트릭 수집 및 시각화

