# GitHub PR에 붙여넣을 내용

## Title (GitHub PR Title 필드에 입력)

```
feat(r10-s2): domain registry, engine meta, llm usage audit, and post-processing hooks
```

---

## Description (GitHub PR Description 필드에 아래 내용 전체 복사)

### 검토팀 승인용 요약

이번 PR은 **AI 온디바이스 Enterprise OS 레이어**의 LLM 서비스 표준화를 완료합니다. DomainLLMService를 공통 패키지로 승격하여 다도메인 확장 기반을 마련하고, LLM Usage Audit에 eventType을 도입해 KPI 측정이 가능하도록 했습니다. Remote LLM Gateway 계약(501 stub)과 3단계 후처리 Hook 구조를 확립하여 Playbook 원칙을 준수합니다.

**Playbook 6원칙 준수 확인:**
- ✅ **온디바이스 우선**: Mock 모드에서 Network 0(HTTP/WS 0) 유지, local-llm-v0 Stub으로 온디바이스 경로 확보
- ✅ **사내 게이트웨이 경계**: HUD→BFF 경계 유지, Remote Gateway는 계약만 정의(501 Stub)로 외부 LLM 호출 미포함
- ✅ **Mock/Live 모드 쌍 유지**: 모든 변경이 Mock/Live 둘 다 검증됨
- ✅ **OS 레이어 재사용성**: DomainLLMService 공통 인터페이스로 HR/법무/보안 등 다도메인 확장 준비 완료
- ✅ **정책/권한/테넌트**: BFF 헤더 규칙(X-Tenant, X-User-Role) 유지, Usage 라우트에 requireTenantAuth 적용
- ✅ **KPI/감사**: Usage는 메타만 수집(원문 텍스트 금지), eventType으로 Manual Touch Rate/추천 사용률 측정 가능

### OS Contribution

이번 PR은 **AI 온디바이스 Enterprise OS 레이어**에 다음 4가지 표준을 고정합니다:

1. **DomainLLMService 공통 패키지(service-core-common) 승격**

   - 회계/CS/HR/법무/보안 등 모든 도메인이 같은 인터페이스로 LLM을 사용하도록 강제
   - `packages/service-core-common/src/llm/domainLLMService.ts` 생성
   - `csLLMService`가 공통 인터페이스 import하도록 수정

2. **LLM Usage eventType(shown/accepted_as_is/edited/rejected/error) 도입**

   - Manual Touch Rate, 추천 사용률, 수정률, 거부율 측정 가능
   - `packages/app-expo/src/hud/telemetry/llmUsage.ts`에 `LlmUsageEventType` 추가
   - `CsHUD`에서 `shown` / `error` eventType 전송 (완전 연결은 R10-S3)

3. **Remote LLM Gateway 계약(/v1/os/llm-gateway/completions) 추가(501 stub)**

   - HUD가 외부 LLM을 직접 호출하지 않고 OS Gateway를 통해 나가는 레일 확보
   - `packages/bff-accounting/src/routes/os-llm-gateway.ts` 생성
   - 현재는 501 Not Implemented 반환 (실제 구현은 R10-S3)

4. **LLM 응답 후처리 Hook 3단계(HUD/Domain/BFF) 구조 확립**
   - `DomainLLMService.postProcess`: 도메인 특화 필터 자리
   - `applyLlmTextPostProcess` (HUD): 공통 텍스트 정리/길이 제한, 향후 온디바이스 PII 필터 자리
   - `sanitizeLlmGatewayOutput` (BFF): remote 응답 서버단 필터 자리
   - `packages/app-expo/src/hud/engines/llmPostProcess.ts` 생성

### Playbook Compliance

- ✅ **Mock 모드 Network 0 유지**: 모든 변경이 Mock 경로에서 HTTP 없이 동작
- ✅ **HUD→BFF 경계 유지**: 텍스트 원문 Audit 금지 준수 (메타/행동 정보만 수집)
- ✅ **Mock/Live 모드 쌍 QA 수행**: 새로운 기능도 Mock/Live 둘 다 검증

### QA

- ✅ Mock+Rule: CS/회계 주요 플로우 정상, Network 탭 HTTP/WS 0, 텍스트 후처리 적용
- ✅ Mock+local-llm: local-llm-v0 Stub 응답 + 후처리 적용, Usage eventType shown은 콘솔 로그만
- ✅ Live+local-llm: /v1/os/llm-usage로 이벤트 전송(텍스트 원문 없이 메타만)
- ✅ /v1/os/llm-gateway/completions 501 stub 확인

### Ops

- ✅ npm ci 실패 원인(lock 불일치) 해결: `package-lock.json` 업데이트 커밋 포함
- ✅ 타입 체크 통과
- ✅ 워크스페이스 빌드 성공

### 주요 변경 파일

- `packages/service-core-common/src/llm/domainLLMService.ts` (신규)
- `packages/app-expo/src/hud/telemetry/llmUsage.ts` (eventType 추가)
- `packages/app-expo/src/hud/engines/llmPostProcess.ts` (신규)
- `packages/app-expo/src/hud/engines/local-llm.ts` (후처리 적용)
- `packages/app-expo/src/hud/engines/index.ts` (후처리 적용)
- `packages/bff-accounting/src/routes/os-llm-gateway.ts` (신규)
- `packages/bff-accounting/src/routes/os-llm-usage.ts` (eventType 처리)
- `package-lock.json` (service-core-common 추가)

### Follow-ups (R10-S3)

- [R10S3-A14-1] CS HUD eventType 완전 연결 (P0)
- [R10S3-E06-1] local-llm-v1 실제 모델 PoC (P0)
- [R10S3-S13-1] Remote Gateway 제한적 실제 구현 (P1)

### 관련 문서

- `docs/R10S2_SPRINT_BRIEF.md`
- `docs/R10S2_TICKETS.md`
- `docs/R10S2_IMPLEMENTATION_GUIDE.md`
- `docs/R10S3_SPRINT_BRIEF.md`
