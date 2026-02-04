# R10-S2 PR 생성 가이드

## 1. PR 생성 직전 로컬/브랜치 상태 최종 확인

✅ **완료됨:**
- 브랜치: `r10-s2-domain-llm-service`
- 원격과 동기화 완료
- R10-S2 관련 변경사항: 이미 커밋됨

⚠️ **참고:**
- 작업 트리에 다른 수정 파일들이 있지만, 이는 R10-S2 PR 범위 외입니다.
- 새 문서 파일들(`docs/R10S2_*`, `docs/R10S3_*`)은 추적되지 않지만, PR에 포함할 필요 없습니다.

### (선택) CI와 동일 조건으로 로컬 확인

```bash
npm ci
```

---

## 2. GitHub PR 생성

### PR 기본값

- **Base:** `main`
- **Compare:** `r10-s2-domain-llm-service`
- **Title:** `feat(r10-s2): domain registry, engine meta, llm usage audit, and post-processing hooks`
- **Description:** 아래 내용 복사/붙여넣기
- **Merge 전략:** `Squash and merge`

### PR Description (복사용)

`docs/R10S2_PR_DESCRIPTION_GITHUB.md` 파일을 열어서 **"## Description" 섹션 아래 내용 전체**를 복사하세요.

---

## 3. PR에서 반드시 확인할 것 (Playbook 관점 "최소 게이트")

### ✅ GitHub Actions CI가 Green인지
- 특히 `npm ci` 단계가 통과하는지 확인

### ✅ PR diff에 아래가 포함되는지

- `packages/service-core-common/**` (DomainLLMService 승격)
- `packages/app-expo/src/hud/telemetry/llmUsage.ts` (eventType)
- `packages/bff-accounting/src/routes/os-llm-gateway*` (501 stub 계약)
- `packages/app-expo/src/hud/engines/llmPostProcess.ts` (후처리 공통)
- `package-lock.json` (이번 CI 이슈 해결 핵심)

---

## 4. (선택) 머지 전 최소 QA — 문서 기반으로 "3케이스만"

이미 `docs/R10S2_QA_CHECKLIST.md`가 있으니, 시간이 없으면 아래 3개만 빠르게 확인해도 충분합니다.

### Mock + Rule (Network 0)
```bash
EXPO_PUBLIC_DEMO_MODE=mock \
EXPO_PUBLIC_ENGINE_MODE=rule \
npm run demo:app:mock
```

### Mock + local-llm (Network 0)
```bash
EXPO_PUBLIC_DEMO_MODE=mock \
EXPO_PUBLIC_ENGINE_MODE=local-llm \
npm run demo:app:mock
```

### Live + local-llm
```bash
EXPO_PUBLIC_DEMO_MODE=live \
EXPO_PUBLIC_ENGINE_MODE=local-llm \
npm run demo:app:live
```

### 체크 포인트(짧게)

- ✅ Mock에서 Network 탭 HTTP/WS 0
- ✅ Live에서 `/v1/os/llm-usage`로 메타만 전송되는지(원문 텍스트 금지)
- ✅ `/v1/os/llm-gateway/completions`는 501 stub 유지

---

## 5. PR Squash&Merge 후 태그 생성 (R10-S2 종료 선언)

PR이 머지되면 아래 그대로 실행하세요.

```bash
git checkout main
git pull origin main

git tag r10-s2-done-20251212
git push origin --tags
```

---

## 6. R10-S3 브랜치 생성 (즉시 착수 준비)

```bash
git switch -c r10-s3-llm-poc
git push origin r10-s3-llm-poc
```

---

## 7. R10-S3 첫 티켓 착수 포인트 (다음 액션 고정)

문서가 이미 있으니 그대로 가면 됩니다.

- `docs/R10S3_FIRST_TICKET_GUIDE.md`
- **[R10S3-A14-1] CS HUD eventType 완전 연결 (P0)**
  - 현재 `shown`/`error`만 연결되어 있으니,
  - `accepted_as_is` / `edited` / `rejected`를 버튼/행동에 매핑해서 KPI 루프를 완성

---

## 8. 참고: typecheck 스크립트 네이밍 이슈 처리 원칙

"type-check vs typecheck 이름 차이"는 R10-S2 PR 스코프에 억지로 끼우지 말고, R10-S3에서 chore 티켓으로 분리하는 지금 방식이 정석입니다. PR 설명에 "Known issue / follow-up"로 한 줄만 남겨도 충분합니다.

