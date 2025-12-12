# R10-S2 이후 백로그

## 개요

R10-S1 완료 후, 다음 스프린트에서 진행할 수 있는 백로그 항목들을 정리했습니다.

## 우선순위 높음 (P0)

### 1. DomainLLMService 공통 패키지로 승격

**현재 상태:**
- `packages/service-core-cs/src/domain/domainLLMService.ts`에 정의됨

**목표:**
- `packages/service-core-common/src/domain/domainLLMService.ts` 또는
- `packages/os-llm-core/src/domainLLMService.ts`로 이동
- 회계/CS/HR/법무 도메인이 전부 같은 인터페이스를 implement 하도록 강제

**작업:**
- [ ] 공통 패키지 생성 또는 기존 패키지 활용
- [ ] `DomainLLMService` 인터페이스 이동
- [ ] `csLLMService`가 공통 인터페이스 import하도록 수정
- [ ] AccountingLLMService, HrLLMService 등이 동일 패턴 사용하도록 확장

### 2. LLM Usage 이벤트에 eventType 추가

**현재 상태:**
- `LlmUsageEvent`에 `outcome` 필드만 있음 (shown/used_as_is/edited/rejected/error)

**목표:**
- `eventType` 필드 추가하여 더 세분화된 이벤트 타입 정의
- Manual Touch Rate, 추천 사용률, 재문의율 같은 KPI 바로 뽑을 수 있도록

**작업:**
- [ ] `LlmUsageEvent` 타입에 `eventType` 필드 추가
- [ ] `CsHUD`에서 각 액션별로 적절한 `eventType` 전송
- [ ] BFF `/v1/os/llm-usage` 라우트에서 `eventType` 처리
- [ ] OS Dashboard에서 `eventType` 기반 KPI 집계

## 우선순위 중간 (P1)

### 3. Remote LLM Gateway 설계 (실구현은 뒤로)

**현재 상태:**
- Remote LLM 모드는 타입/플래그 정의만 있음

**목표:**
- "HUD → BFF(LLM Gateway 모듈) → 외부 LLM" 계약만 정의
- HUD/Web에서 외부 LLM 직접 호출하는 루트를 아예 없애는 쪽으로 Playbook 강화

**작업:**
- [ ] Remote LLM Gateway 인터페이스 설계
- [ ] BFF에 LLM Gateway 모듈 스켈레톤 추가
- [ ] Playbook에 Remote LLM Gateway 규칙 명시
- [ ] HUD/Web에서 외부 LLM 직접 호출 금지 검증

### 4. LLM 응답 후처리 Hook 설계

**현재 상태:**
- LLM 응답이 바로 반환됨

**목표:**
- `postProcessResponse(ctx, res)` 같은 후크를 `DomainLLMService`나 `LocalLLMEngineV1`에 추가
- 개인정보/금지 표현 필터링/안전성 체크를 꽂을 수 있는 위치 확보

**작업:**
- [ ] `DomainLLMService`에 `postProcessResponse` 메서드 추가
- [ ] `LocalLLMEngineV1`에서 후처리 Hook 호출
- [ ] 기본 후처리 구현 (개인정보 마스킹 등)
- [ ] 후처리 Hook 확장 가능하도록 인터페이스 정의

## 우선순위 낮음 (P2)

### 5. 실제 온디바이스 LLM PoC (local-llm-v1)

**현재 상태:**
- `LocalLLMEngineV1`은 Stub (variant: 'local-llm-v0')

**목표:**
- 실제 온디바이스 모델(양자화된 SLM) 연동
- `local-llm-v1` 버전으로 구현

**작업:**
- [ ] 온디바이스 LLM 라이브러리 선택 (예: llama.cpp, onnxruntime)
- [ ] 모델 로딩 및 추론 파이프라인 구현
- [ ] `LocalLLMEngineV1`에서 실제 모델 호출
- [ ] 성능 최적화 (양자화, 배치 처리 등)

### 6. LLM Usage 대시보드 스키마 초안

**현재 상태:**
- LLM Usage 이벤트는 로그만 남김

**목표:**
- PostgreSQL 테이블 스키마 설계
- OS Dashboard에서 LLM Usage 통계 표시

**작업:**
- [ ] `llm_usage_events` 테이블 스키마 설계
- [ ] 마이그레이션 파일 작성
- [ ] BFF에서 DB 저장 로직 구현
- [ ] OS Dashboard에서 LLM Usage 통계 쿼리 및 표시

## 참고

- R10-S1 완료 기준선: `r10-s1-done-20251212` 태그
- 다음 스프린트는 R10-S2 또는 R11로 진행 예정

