# R10-S1 스프린트 개요

## 스프린트 정보

- **이름**: R10-S1 – On-device LLM Backend v0.5 + Domain LLM 추상화 + LLM Usage Audit v0
- **기간**: TBD
- **목표 한 줄 요약**: 온디바이스 LLM Stub을 Domain-독립적인 Backend 인터페이스로 추상화하고, DomainLLMService 인터페이스를 도입하여 회계/CS/HR/법무/보안 등이 같은 LLM 패턴을 공유하도록 하며, CS HUD에서 LLM 사용에 대한 최소 Audit 이벤트를 기록하는 v0 구조를 만든다.

## 배경

R9-S2에서 CS 도메인에 SuggestEngine이 연동되고 LocalLLMEngineV1 CS 어댑터가 구현되었습니다. 이제 OS 레이어의 장기 확장성을 위해 다음을 진행합니다:

1. **온디바이스 LLM Backend 추상화**: LocalLLMEngineV1을 Domain-독립적인 Backend 인터페이스로 추상화
2. **DomainLLMService 인터페이스 도입**: 회계/CS/HR/법무/보안 등이 같은 LLM 패턴을 공유
3. **도메인 핸들러 레지스트리 패턴 준비**: 엔진 if/switch 폭발 방지
4. **LLM Usage Audit v0**: suggestion_shown/accepted/edited/rejected 이벤트 기록

## 목표 (Goals)

1. **LocalLLMEngineV1 "Stub 메타 + 버전" 명시**
   - 엔진 메타 타입 추가 (stub, variant 등)
   - LocalLLMEngineV1에서 메타 구현
   - HUD 상태바, OS Dashboard, 로그에서 Stub/실제 모델 구분 가능

2. **DomainLLMService 인터페이스 도입 + csLLMService 적용**
   - 공통 인터페이스 정의
   - csLLMService가 DomainLLMService 구현하도록 확장
   - 추후 AccountingLLMService, HrLLMService 등이 동일 패턴 사용

3. **도메인 핸들러 레지스트리 패턴 준비**
   - 핸들러 타입/레지스트리 정의
   - CS/Accounting 핸들러 등록 예시
   - LocalLLMEngineV1에서 레지스트리 사용

4. **LLM Usage Audit v0 구현**
   - HUD 측 Telemetry 유틸 구현
   - CsHUD에서 이벤트 호출 포인트 추가
   - BFF 라우트 `/v1/os/llm-usage` 구현

5. **Playbook 문서 패치**
   - LLM 버전/엔진 명명 규칙 추가
   - Remote LLM 게이트웨이 규칙 명시
   - LLM Usage KPI/Audit 예시 추가

## 범위 (Scope)

### App (A-12)

- **[A-12-1]** EngineMeta 타입 추가 및 LocalLLMEngineV1 메타 구현
  - `EngineMeta` 타입 정의 (mode, stub, variant)
  - `SuggestEngine` 인터페이스에 `getMeta()` 메서드 추가
  - LocalLLMEngineV1에서 메타 구현

- **[A-12-2]** DomainLLMService 인터페이스 도입
  - 공통 인터페이스 정의
  - csLLMService가 DomainLLMService 구현하도록 확장

- **[A-12-3]** 도메인 핸들러 레지스트리 패턴 준비
  - 핸들러 타입/레지스트리 정의
  - CS/Accounting 핸들러 등록 예시
  - LocalLLMEngineV1에서 레지스트리 사용

- **[A-12-4]** LLM Usage Audit v0 구현
  - HUD 측 Telemetry 유틸 구현
  - CsHUD에서 이벤트 호출 포인트 추가

### Server (S-11)

- **[S-11-1]** BFF 라우트 `/v1/os/llm-usage` 구현
  - POST 엔드포인트 구현
  - requireTenantAuth 미들웨어 적용
  - 로그 기록 (R10-S1에서는 로그만, R10-S2 이후 PG 테이블 적재)

### Service-Core (SC-11)

- **[SC-11-1]** DomainLLMService 인터페이스 정의
  - 공통 인터페이스 타입 정의
  - csLLMService 구현

### Docs

- **[D-01]** Playbook 문서 업데이트
  - LLM 버전/엔진 명명 규칙 추가
  - Remote LLM 게이트웨이 규칙 명시
  - LLM Usage KPI/Audit 예시 추가

## 비범위 (Non-goals)

1. **실제 온디바이스 LLM 모델 연동**
   - 이번 스프린트는 추상화 및 인터페이스 정의에 집중
   - 실제 모델 연동은 다음 스프린트로

2. **LLM Usage 데이터의 PG 테이블 적재**
   - R10-S1에서는 로그만 기록
   - PG 테이블 적재/리포트는 R10-S2 이후

3. **모든 도메인 핸들러 전환**
   - CS/Accounting 핸들러만 등록 예시로 구현
   - 나머지 도메인은 점진적으로 전환

4. **원문 텍스트 수집**
   - Playbook 규칙에 따라 메타데이터(길이, 엔진 모드, 도메인 등)만 수집
   - 원문 텍스트는 수집하지 않음

## Definition of Done

1. ✅ EngineMeta 타입이 정의되고 LocalLLMEngineV1에서 메타 반환
2. ✅ DomainLLMService 인터페이스가 정의되고 csLLMService가 구현
3. ✅ 도메인 핸들러 레지스트리 패턴이 준비되고 CS/Accounting 핸들러 등록 예시 구현
4. ✅ LLM Usage Audit v0가 구현되고 CsHUD에서 이벤트 전송
5. ✅ BFF 라우트 `/v1/os/llm-usage`가 구현되고 로그 기록
6. ✅ Playbook 문서가 업데이트됨
7. ✅ 모든 테스트 통과 (기존 회귀 테스트 포함)

## 엔진 메타 명명 규칙

### 엔진/모델 명명 예시

- `rule-v1`: 규칙 기반 엔진 v1
- `local-llm-v0`: Stub 버전 (R9-S2 기준)
- `local-llm-v1`: 실제 온디바이스 모델 (추후)
- `remote-llm-x`: 원격 LLM 엔진

### 코드/설정/로그 어디서든 동일한 이름 사용

- `local-llm-v0`는 Stub이며, 클라이언트 메모리에서만 동작하고 네트워크를 사용하지 않음
- `local-llm-v1` 이후 버전은 실제 온디바이스 모델(예: 양자화된 SLM)만 사용

## Remote LLM 게이트웨이 규칙

- Remote LLM 모드는 항상 다음 경로만 허용:
  - `HUD/Web → BFF(LLM Gateway 모듈) → 외부 LLM`
- HUD/Web 코드가 외부 LLM(OpenAI/Gemini 등)을 직접 HTTP 호출하는 구현은 금지
- 모든 LLM 요청(Local/Remote 불문)은 SuggestEngine 인터페이스를 통과해야 함

## LLM Usage Audit 이벤트

### 최소 이벤트 타입

- `suggestion_shown`: 추천이 화면에 표시됨
- `suggestion_used_as_is`: 그대로 적용됨
- `suggestion_edited`: 수정 후 전송됨
- `suggestion_rejected`: 무시됨

### 수집 메타데이터

- 원문 텍스트는 수집하지 않음
- 다음 메타데이터만 수집:
  - 길이 (suggestionLength)
  - 엔진 모드 (engineMode)
  - 도메인 (domain)
  - 테넌트 (tenantId)
  - 사용자 (userId)
  - 역할 (userRole)
  - 타임스탬프 (timestamp)

## 참고 문서

- [R9S2_SPRINT_BRIEF.md](./R9S2_SPRINT_BRIEF.md) - 이전 스프린트 개요
- [AI_ONDEVICE_ENTERPRISE_PLAYBOOK.md](./docs/AI_ONDEVICE_ENTERPRISE_PLAYBOOK.md) - Playbook 문서

