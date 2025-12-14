# R10-S2 스프린트 개요

## 스프린트 정보

- **이름**: R10-S2 – Domain LLM Service 공통화 + LLM Usage 세분화 + Remote Gateway 설계
- **기간**: TBD
- **기준선**: `r10-s1-done-20251212`
- **목표 한 줄 요약**: DomainLLMService를 공통 패키지로 승격하고, LLM Usage 이벤트를 세분화하며, Remote LLM Gateway 설계를 완료한다.

## 배경

R10-S1에서 온디바이스 Stub + Domain Registry + EngineMeta + LLM Usage v0 + DB/Gateway 정리가 완료되었습니다. 이제 OS 레이어의 확장성과 KPI 측정 정밀도를 높이기 위해 다음을 진행합니다:

1. **DomainLLMService 공통 패키지 승격**: 회계/CS/HR/법무/보안이 같은 패턴으로 움직이도록 강제
2. **LLM Usage eventType 추가**: Manual Touch Rate, 추천 사용률, 수정률, 거부률 측정 가능
3. **Remote LLM Gateway 설계**: HUD가 외부 LLM을 직접 호출하지 않고 OS Gateway를 통해 나가는 레일 확보
4. **LLM 응답 후처리 Hook**: 개인정보/금지 표현/정책 위반 응답을 공통 레이어에서 필터링

## 목표 (Goals)

### P0 (필수)

1. **DomainLLMService 공통 패키지 승격**
   - `packages/service-core-common/src/llm/domainLLMService.ts` 생성
   - `csLLMService`가 공통 인터페이스 import하도록 수정
   - 추후 accounting/HR/법무 서비스도 같은 인터페이스 구현 강제

2. **LLM Usage eventType 추가**
   - `LlmUsageEventType` 타입 정의 (shown/accepted_as_is/edited/rejected/error)
   - `LlmUsageEvent`에 `eventType` 필드 추가
   - `CsHUD`에서 각 액션별로 적절한 `eventType` 전송
   - BFF `/v1/os/llm-usage` 라우트에서 `eventType` 처리

### P1 (중요)

3. **Remote LLM Gateway 설계**
   - `packages/bff-accounting/src/routes/os-llm-gateway.ts` 생성
   - POST `/v1/os/llm/proxy` 라우트 정의
   - `requireTenantAuth` / `requireRole('operator')` 적용
   - 현재는 501 Not Implemented 반환 (실제 LLM 호출은 R10-S3 이후)

4. **LLM 응답 후처리 Hook**
   - `DomainLLMService`에 `postProcess?` 메서드 추가
   - `LocalLLMEngineV1`에서 후처리 Hook 호출
   - 기본 후처리 구현 (개인정보 마스킹 등)

### P2 (선택)

5. **실제 온디바이스 모델 PoC (local-llm-v1)**
   - 온디바이스 LLM 라이브러리 선택 및 연동
   - `LocalLLMEngineV1`에서 실제 모델 호출

6. **LLM Usage 대시보드 스키마 초안**
   - PostgreSQL 테이블 스키마 설계
   - 마이그레이션 파일 작성

## 범위 (Scope)

### App (A-13)

- **[A-13-1]** LLM Usage eventType 추가 및 CsHUD 연동
  - `LlmUsageEventType` 타입 정의
  - `LlmUsageEvent`에 `eventType` 필드 추가
  - `CsHUD`에서 각 액션별 `eventType` 전송

### Service-Core (SC-12)

- **[SC-12-1]** DomainLLMService 공통 패키지 승격
  - `packages/service-core-common/src/llm/domainLLMService.ts` 생성
  - `csLLMService`가 공통 인터페이스 import하도록 수정
  - `postProcess?` 메서드 추가

### BFF (S-12)

- **[S-12-1]** Remote LLM Gateway 라우트 설계
  - POST `/v1/os/llm/proxy` 라우트 정의
  - `requireTenantAuth` / `requireRole('operator')` 적용
  - 현재는 501 Not Implemented 반환

### Engine (E-05)

- **[E-05-1]** LLM 응답 후처리 Hook 연동
  - `LocalLLMEngineV1`에서 `postProcess` 호출
  - 기본 후처리 구현

## 가드레일 (Guardrails)

1. **온디바이스 우선 유지**
   - Mock 모드에서 Network 0 유지
   - LocalLLMEngineV1 Stub(v0) 구조 유지

2. **게이트웨이 경계 유지**
   - HUD가 외부 LLM을 직접 호출하지 않음
   - 모든 LLM 요청은 BFF Gateway를 통해

3. **Mock/Live 모드 쌍 유지**
   - 새로운 기능도 Mock 경로에서 HTTP 없이 동작
   - Live 경로만 BFF 경유

4. **기존 구조 변경 최소화**
   - R10-S1에서 확립된 구조 유지
   - 공통 패키지 승격은 기존 코드와 호환되도록

## 정의 완료 (Definition of Done)

- [ ] DomainLLMService가 `service-core-common`에 정의되고 `csLLMService`가 이를 import
- [ ] LLM Usage 이벤트에 `eventType` 필드가 추가되고 `CsHUD`에서 각 액션별로 전송
- [ ] Remote LLM Gateway 라우트가 정의되고 501 Not Implemented 반환
- [ ] `DomainLLMService`에 `postProcess?` 메서드가 추가되고 `LocalLLMEngineV1`에서 호출
- [ ] 타입 체크 통과
- [ ] Mock + Rule / Mock + local-llm / Live + local-llm 플로우 검증
- [ ] 문서 업데이트 (R10S2_SPRINT_BRIEF.md, R10S2_TICKETS.md)

## 리스크 및 고려사항

1. **공통 패키지 의존성**
   - `service-core-common` 패키지가 없을 경우 생성 필요
   - 기존 `service-core-cs`와의 의존성 관계 확인

2. **타입 호환성**
   - `csLLMService`가 공통 인터페이스로 전환 시 타입 에러 가능
   - 점진적 마이그레이션 필요

3. **Remote Gateway 설계**
   - 실제 LLM 호출은 R10-S3 이후이므로, 현재는 계약만 정의
   - 향후 확장 가능하도록 설계

## 관련 문서

- R10S1_PLAYBOOK_COMPLIANCE.md
- R10S1_SPRINT_BRIEF.md
- R10S2_TICKETS.md (생성 예정)
- AI_ONDEVICE_ENTERPRISE_PLAYBOOK.md

