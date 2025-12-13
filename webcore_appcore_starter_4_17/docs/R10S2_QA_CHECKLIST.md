# R10-S2 PR 머지 전 QA 체크리스트

## 1. 브랜치 최신화 + 설치/빌드

```bash
git checkout r10-s2-domain-llm-service
git pull origin r10-s2-domain-llm-service

# 로컬에서도 CI와 동일하게
npm ci

# 워크스페이스 타입/빌드
npm run typecheck --workspaces
npm run build --workspaces
```

**체크**: ✅ 타입 에러 없음, 빌드 성공

---

## 2. Mock/Live 수동 QA (Playbook 핵심)

### 2-1. Mock + Rule (Network 0)

```bash
EXPO_PUBLIC_DEMO_MODE=mock \
EXPO_PUBLIC_ENGINE_MODE=rule \
npm run demo:app:mock
```

**기대 결과**:
- ✅ CS/회계 주요 플로우 정상 동작
- ✅ Network 탭 HTTP/WS 0건
- ✅ 텍스트 후처리 적용 확인 (개행 정리, 공백 제거, 4000자 제한)
- ✅ Rule 응답: `[Rule] "..." 문의에 대한 규칙 기반 Mock 응답입니다.`

**체크**: ✅ 모든 항목 통과

---

### 2-2. Mock + local-llm (Network 0)

```bash
EXPO_PUBLIC_DEMO_MODE=mock \
EXPO_PUBLIC_ENGINE_MODE=local-llm \
npm run demo:app:mock
```

**기대 결과**:
- ✅ local-llm-v0 Stub 응답 표시 (약 1.8초 지연 후)
- ✅ 후처리 적용 확인
- ✅ Usage eventType `shown`은 콘솔 로그만 출력 (BFF로 전송 안 함)
- ✅ Network 탭 HTTP/WS 0건

**⚠️ 주의**: Mock에서 BFF로 전송되면 Playbook 위반 가능성이 있으니 확인

**체크**: ✅ 모든 항목 통과

---

### 2-3. Live + local-llm

```bash
EXPO_PUBLIC_DEMO_MODE=live \
EXPO_PUBLIC_ENGINE_MODE=local-llm \
npm run demo:app:live
```

**기대 결과**:
- ✅ `/v1/os/llm-usage`로 이벤트 전송 (텍스트 원문 없이 메타만)
- ✅ BFF 로그에 `{"type":"llm_usage", ... "eventType":"shown", ...}` 형태 JSON 확인
- ✅ `/v1/os/llm-gateway/completions`는 501 Stub 유지 (실제 호출 안 함)

**체크**: ✅ 모든 항목 통과

---

## 3. BFF 라우트 확인

```bash
npm run build --workspace=@appcore/bff-accounting
npm run dev:bff
```

**체크 항목**:
- ✅ `/v1/os/llm-usage` POST가 200/204로 처리됨
- ✅ `/v1/os/llm-gateway/completions`는 501로 떨어짐 ("설계만" 가드)

**체크**: ✅ 모든 항목 통과

---

## 4. package-lock.json 확인

```bash
git log --oneline -5 | grep "package-lock"
```

**체크**: ✅ `chore: update package-lock.json for service-core-common` 커밋 포함

---

## 5. 최종 체크리스트

- [ ] 브랜치 최신화 완료
- [ ] `npm ci` 통과
- [ ] 타입 체크 통과
- [ ] 빌드 성공
- [ ] Mock+Rule QA 통과
- [ ] Mock+local-llm QA 통과
- [ ] Live+local-llm QA 통과
- [ ] BFF 라우트 확인 완료
- [ ] package-lock.json 업데이트 커밋 확인

**모든 항목 체크 완료 시 PR 머지 가능**


