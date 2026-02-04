# R10-S1 Playbook 준수 검토 결과

## 개요

R10-S1 스프린트 완료 후, AI_ONDEVICE_ENTERPRISE_PLAYBOOK.md의 6가지 핵심 원칙에 대한 준수 여부를 검토한 결과입니다.

## 검토 결과 요약

### ✅ 1. 온디바이스 우선 (On-device first)

**지켜진 것:**
- LocalLLMEngineV1를 Stub(v0)로 두고 클라이언트 메모리 안에서 응답 생성
- 1.8초 지연으로 "온디바이스 추론 느낌"만 흉내
- remote LLM 호출 없음
- DEMO_MODE=mock에서:
  - ENGINE_MODE=rule → LocalRuleEngineV1Adapter
  - ENGINE_MODE=local-llm → LocalLLMEngineV1
  - 둘 다 Network 탭 HTTP/WS 0건 조건을 맞추도록 수정/검증
- R10-S1에서 EngineMeta/LLM Usage를 추가만 했지, 외부 LLM/HTTP 의존성은 늘리지 않음 (온디바이스 Stub 구조 유지)

**결론:** "지금은 Stub이지만, 추후 local-llm-v1 실제 모델을 올리기 위한 온디바이스 골격"이라는 Playbook 방향과 일치합니다.

### ✅ 2. 사내 게이트웨이 경계 (Enterprise Gateway)

**지켜진 것:**
- HUD(Web/app-expo)에서:
  - CS 데이터: 항상 cs-api.ts → /v1/cs/tickets, /v1/cs/os/dashboard
  - LLM Usage: llmUsage.ts → /v1/os/llm-usage
  - 직접 DB/외부 시스템/외부 LLM 호출 없음
- 민감 정보(Export 키, DB 커넥션 등)는 전부 BFF/.env + data-pg 계층에 유지
- service-core-cs에서 잠깐 Pool 직접 생성 시도했다가, 다시 @appcore/data-pg의 exec를 쓰도록 되돌린 것까지 정리 완료
- /v1/os/llm-usage: **"텍스트 원문은 받지 않는다"**는 규칙을 코드/문서 수준에서 명시
- 엔진 메타/도메인 정보/모드 정도만 Audit으로 전송

**결론:** 지금 구조는 항상 `HUD/Web → BFF(OS Gateway) → data-pg/DB/외부 시스템` 형태를 유지하고 있고, HUD가 외부 LLM이나 사내 시스템을 직접 치는 흔적은 없습니다.

### ✅ 3. Mock / Live 모드 쌍 유지

**지켜진 것:**
- 모드별 플로우를 명확히 고정:

| DEMO_MODE | ENGINE_MODE | 엔진 | 특징 |
|-----------|-------------|------|------|
| mock | rule | LocalRuleEngineV1Adapter | 규칙 기반 Mock 응답, Net=0 |
| mock | local-llm | LocalLLMEngineV1 Stub | 1.8s 지연 + Stub, Net=0 |
| live | local-llm | LocalLLMEngineV1 Stub | BFF/DB 사용 + Usage Audit |

- docs/R10S1_COMPLETION_CHECKLIST.md에 Mock + Rule / Mock + local-llm / Live + local-llm 세 플로우를 QA 항목으로 고정
- 새로운 기능(LLM Usage, Domain 핸들러 등)을 넣을 때도:
  - Mock 경로에서 HTTP 없이 동작하도록 설계
  - Live 경로만 BFF 경유하도록 유지

**결론:** "Mock 먼저, Live 나중" + "Mock은 항상 오프라인(Net=0)" 규칙을 잘 따라가고 있습니다.

### ✅ 4. OS 레이어 재사용성

**지켜진 것:**
- 도메인 핸들러 레지스트리 패턴 도입:
  - domainHandlers.ts, domainHandlersRegistry.ts로
  - domain → handler 등록 구조 준비
  - 앞으로 HR/법무/보안/반도체 등은 register('hr', hrHandler) 식으로 붙일 수 있는 발판 마련
- DomainLLMService 인터페이스 도입:
  - service-core-cs/domain/domainLLMService.ts + csLLMService.ts
  - 추후 accounting/HR/법무 서비스도 같은 인터페이스를 구현하도록 백로그에 P0로 올려둔 상태
- EngineMeta 확장:
  - id, variant, supportedDomains (그리고 Usage에 engineStub)
  - 앞으로 엔진/도메인/모드를 공통 규격으로 introspection 할 수 있는 OS 레이어 메타 구조

**결론:** 회계/CS에서 만든 패턴을 그대로 HR/법무/보안/반도체 HUD로 확산시키기 좋은 형태로 정리해 놓은 상태입니다.

### ✅ 5. 정책/권한/테넌트 (BFF 헤더 규칙)

**그간의 흐름:**
- CS BFF 라우트(/v1/cs/*)는 회계와 동일하게:
  - requireTenantAuth
  - requireRole('operator') 패턴을 따라가도록 붙여 왔고,
- HUD → BFF 호출 시 mkHeaders에서:
  - X-Tenant
  - X-User-Id
  - X-User-Role
  를 붙여 보내는 구조를 유지해 왔습니다.
- DB 접근/Export/LLM Usage 모두:
  - 테넌트/유저/역할을 기준으로 정책/로그를 쌓는 방향.

**남은 숙제(백로그 레벨):**
- /v1/os/llm-usage 같은 "운영/감사용 라우트"에 대해:
  - X-User-Role in { admin, auditor } 같은 구체 정책을
  - Playbook/설계 문서에 명시적으로 박아두는 작업은 앞 스프린트에서 제안만 되어 있고, R10-S2 이후에 다듬을 예정입니다.

**결론:** 그래도 **큰 틀(테넌트/역할 기반의 BFF 헤더 구조)**는 이미 잘 따라가고 있고, 위반되는 구현은 나오지 않았습니다.

### ✅ 6. KPI/감사 관점

**지켜진 것:**
- CS LLM의 핵심 UX: "요약/추천" 버튼
  - 상담사가 **매번 처음부터 타이핑하는 비율(Manual Touch Rate)**을 줄이는 구조.
- LLM Usage Audit v0 구현:
  - HUD 레벨에서 sendLlmUsageEvent(cfg, meta, evt) 호출
  - 이벤트에 engineId, engineVariant, engineMode, engineStub, 도메인 등 메타 포함
  - BFF /v1/os/llm-usage 라우트로 전송 → 추후 KPI/리포트에 사용 가능
- 프론트/서버 에러 핸들링 개선:
  - /v1/cs/tickets 실패 시 응답 body를 콘솔에 로그
  - BFF에서 DB/스키마/헤더 문제를 명시적으로 로그 → 운영/QA에서 장애 원인 추적 용이

**앞으로 백로그에 올라간 것:**
- docs/R10S2_BACKLOG.md에 이미 정리됨:
  - DomainLLMService 공통 패키지 승격 (P0)
  - LLM Usage 이벤트에 eventType (shown/used_as_is/edited/rejected/error) 추가 (P0)
  - LLM 응답 후처리 Hook 설계 (P1)
  - LLM Usage 대시보드 스키마 초안 (P2)

**결론:** KPI/감사/리스크 관리의 "기반"은 이미 코드에 들어갔고, 정밀한 이벤트 타입·대시보드는 R10-S2 이후로 밀어둔 상태입니다.

## 종합 평가

### ✅ 모든 원칙 준수 확인

R10-S1 스프린트는 AI_ONDEVICE_ENTERPRISE_PLAYBOOK.md의 6가지 핵심 원칙을 모두 준수하며 완료되었습니다.

### 주요 성과

1. **온디바이스 우선 구조 확립**
   - Stub 기반 온디바이스 골격 완성
   - Mock 모드에서 Network 0 유지

2. **게이트웨이 경계 명확화**
   - HUD → BFF → DB 구조 일관성 유지
   - 텍스트 원문 없이 메타/통계만 Audit

3. **Mock/Live 모드 쌍 완성**
   - 세 가지 플로우 모두 검증 완료
   - Mock 경로 오프라인 보장

4. **OS 레이어 재사용성 확보**
   - 도메인 핸들러 레지스트리 패턴
   - DomainLLMService 인터페이스
   - EngineMeta 확장

5. **정책/권한/테넌트 구조 유지**
   - requireTenantAuth / requireRole 패턴
   - 헤더 구조 일관성

6. **KPI/감사 기반 구축**
   - LLM Usage Audit v0 구현
   - 세부 이벤트 타입은 R10-S2 백로그

### 다음 스프린트 준비

- R10-S2 백로그 정리 완료
- DomainLLMService 공통 패키지 승격 (P0)
- LLM Usage eventType 추가 (P0)
- Remote LLM Gateway 설계 (P1)
- LLM 응답 후처리 Hook (P1)

## 관련 문서

- AI_ONDEVICE_ENTERPRISE_PLAYBOOK.md
- R10S1_SPRINT_BRIEF.md
- R10S1_TICKETS.md
- R10S1_DESIGN_NOTES.md
- R10S2_BACKLOG.md


- [E06-2B] WebLLM 모델 아티팩트는 동일 오리진 또는 BFF 경계로 제한(외부 도메인 직접 fetch 금지) 규칙을 Playbook에 반영했습니다.
