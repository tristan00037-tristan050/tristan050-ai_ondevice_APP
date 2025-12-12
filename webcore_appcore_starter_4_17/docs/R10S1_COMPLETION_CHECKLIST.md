# R10-S1 완료 체크리스트

## 타입 체크

- [x] 타입 체크 실행 완료
- [x] R10-S1 변경사항에서 신규 타입 에러 없음 확인
- [ ] 기존 타입 에러는 별도 티켓으로 분리 (선택사항)

## 수동 QA

### 1. Mock + Rule
```bash
EXPO_PUBLIC_DEMO_MODE=mock \
EXPO_PUBLIC_ENGINE_MODE=rule \
npm run demo:app:mock
```

체크 항목:
- [ ] CS HUD 탭 진입 시 `/v1/cs/tickets` 200
- [ ] 티켓 리스트 정상 표시
- [ ] "요약/추천" → `[Rule] "Mock CS Ticket 1" 문의에 대한 규칙 기반 Mock 응답입니다.`
- [ ] Network HTTP/WS = 0
- [ ] 콘솔: LLM Usage가 `[MOCK] ...` 형태로 출력

### 2. Mock + local-llm
```bash
EXPO_PUBLIC_DEMO_MODE=mock \
EXPO_PUBLIC_ENGINE_MODE=local-llm \
npm run demo:app:mock
```

체크 항목:
- [ ] CS HUD 탭 진입 시 `/v1/cs/tickets` 200
- [ ] 티켓 리스트 정상 표시
- [ ] "요약/추천" → 약 1.8초 후 LLM 스타일 Stub 응답
- [ ] Network HTTP/WS = 0
- [ ] 콘솔: `[MOCK] LLM usage event`에 `engineId: 'local-llm'`, `engineVariant: 'local-llm-v0'`, `engineStub: true` 포함

### 3. Live + local-llm
```bash
EXPO_PUBLIC_DEMO_MODE=live \
EXPO_PUBLIC_ENGINE_MODE=local-llm \
npm run demo:app:live
```

체크 항목:
- [ ] `/v1/cs/tickets` 200
- [ ] `/v1/os/llm-usage` 204
- [ ] BFF 로그: `{"type":"llm_usage", "engineId":"local-llm", "engineVariant":"local-llm-v0", ...}` JSON 한 줄 출력 확인

## 커밋 및 PR

### 커밋
```bash
git add .
git commit -m "refactor(r10-s1): enrich engine meta and llm usage audit"
git push origin r10-s1-llm-backend-and-audit
```

### PR 생성
- Base: `main`
- Compare: `r10-s1-llm-backend-and-audit`
- 제목: `refactor(r10-s1): domain registry, engine meta, and llm usage audit v0`
- 머지 전략: Squash and merge

### 태그 생성 (선택사항)
```bash
git checkout main
git pull origin main
git tag r10-s1-done-20251212
git push origin --tags
```

## 주요 변경사항

### App (A-12)
- EngineMeta 타입 확장 (id, stub, variant, supportedDomains)
- LocalLLMEngineV1 / LocalRuleEngineV1Adapter 메타 구현
- 도메인 핸들러 레지스트리 패턴 도입
- LLM Usage Telemetry 구현
- CsHUD에서 LLM Usage 이벤트 전송

### Service-Core (SC-11)
- DomainLLMService 인터페이스 정의
- csLLMService가 DomainLLMService 구현

### BFF (S-11)
- `/v1/os/llm-usage` POST 라우트 구현
- LLM Usage 이벤트 로깅

### Data-PG
- Pool lazy initialization 구현 (DATABASE_URL 로드 문제 해결)

### 문서
- R10S1_SPRINT_BRIEF.md
- R10S1_TICKETS.md
- R10S1_DESIGN_NOTES.md
- AI_ONDEVICE_ENTERPRISE_PLAYBOOK.md (LLM 버전/게이트웨이/Usage 예시 추가)

