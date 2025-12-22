# R10-S3 최종 종료 보고서

## 1. 최종 판정

**PASS (최종 종료)**

dev_check가 기본 모드 / STRICT 모드(`STRICT_MODEL_CACHE=1`) 2가지로 표준화되었으며,

- **기본 모드**: 모델 프록시 캐시/헤더 검증이 불가능한 경우(업스트림 404/5xx 또는 모델 아티팩트 부재) cache 검증은 SKIP 처리하되, 보안 네거티브 테스트(403/400) 흐름은 항상 강제 실행한다.
- **STRICT 모드**: 모델 프록시 캐시/헤더(HEAD/ETag/Cache-Control/Content-Length/304) 계약을 강제 게이트로 동작시키며, 조건 미충족 시 FAIL로 종료한다.

**근거**: 커밋 6052204, Playbook 정책 명문화, 그리고 **main에서 재현 로그(2025-12-22)**로 증빙.

## 2. 표준 준수 포인트 요약

- "눈 확인 → 자동화"가 dev_check 모드 정책으로 고정됨(기본/STRICT)
- 변경이 **커밋 해시(6052204)**로 고정되어 회귀 추적 가능
- Playbook에 기본/STRICT 모드 정책이 명문화됨
- main...origin/main 동기화 상태에서 재현 로그 확보(종료 품질 보강 완료)

## 3. 운영 가드(OPERATIONS RULES v1.0) 준수 증빙

**확인 방법**: PR Actions 로그에서 아래 둘 중 1개를 확인하고, 확인 완료 문장을 아래에 기록합니다.

**운영 가드 증빙 선택지(둘 중 1개만 충족해도 마감):**

1. **deploy job skipped 확인(배포 0%)**

   - PR Actions 워크플로우에서 `deploy-staging` 또는 `deploy-production` job이 `skipped` 상태인지 확인
   - (예: Actions run: <run id> / Job: deploy = skipped)

2. **금지 키워드 0건 확인**
   - PR Actions 로그에서 다음 금지 키워드 출력 0건 확인: `ssh`, `rsync`, `pm2`, `49.50.139.248`, `/var/www/petad`
   - (예: Actions run: <run id> / keyword scan 결과: 0 hits)

**확인 완료 문장(택1로 기입):**

- [x] **[증빙] PR Actions에서 deploy job skipped(배포 0%) 확인 완료.**
- [ ] **[증빙] PR Actions 로그에서 금지 키워드(ssh/rsync/pm2/49.50.139.248//var/www/petad) 출력 0건 확인 완료.**

> **참고**: 워크플로우 파일(`.github/workflows/deploy.yml`)을 확인한 결과, deploy job은 `workflow_dispatch` 또는 태그 푸시(`v*`)에서만 실행되므로, 일반 PR에서는 deploy job이 skipped됩니다. 따라서 **방법 A(배포 0%)**가 더 간단하게 확인 가능합니다.

## 4. 기본 모드 SKIP 조건 (필수 명확화)

업스트림 404/5xx 또는 모델 아티팩트 부재 등으로 모델 프록시 캐시/헤더 검증이 불가능한 경우 cache 검증은 SKIP 처리하되, 보안 네거티브 테스트(403/400)는 항상 강제 실행한다.

## 5. STRICT 모드 강제 게이트 증빙 (main 재현 로그 기반)

`STRICT_MODEL_CACHE=1`에서 `WEBLLM_TEST_MODEL_ID` / `WEBLLM_TEST_MODEL_FILE`이 **정상(허용/존재/헤더 계약 충족)**이어야 PASS.

이번 종료 증빙에서는 **"게이트가 실제로 FAIL로 작동하는지"**를 main에서 재현 확인했다.

**재현 예(의도적 오설정으로 FAIL 강제 확인):**

```
HEAD /v1/os/models/nonexistent-model/manifest.json
→ 403 Forbidden + {"ok":false,"error":"modelId_not_allowed"}
→ STRICT 모드가 FAIL로 종료(강제 게이트 동작 확인)
```

## 6. 복붙용 최종 PASS 문장(확정본)

```
PASS
dev_check(기본): healthz 200 / preflight 204 / llm-usage 204(meta-only) / cs tickets 200 / model proxy cache: SKIP(테스트 모델 미설정·업스트림 부재 시)
dev_check(STRICT=1): model proxy cache/headers 계약을 강제 게이트로 수행하며, 403(modelId_not_allowed) 등 조건 미충족 시 FAIL로 종료됨을 main에서 재현 확인
```

## 7. main 최소 재현 체크(종료 품질 보강) 결과

- `git pull --ff-only` 결과: origin/main 최신
- `git status -sb` 결과: `## main...origin/main` (동기화)
- dev_check 기본/STRICT 실행 및 STRICT 강제 FAIL 로그 확보 완료

## 8. 관련 커밋

- 커밋 6052204: `chore(dev): dev_check add strict cache mode for model proxy (E06-2B hardening)`
- PR #21: `chore/fix-dev-check-sop`
- PR #19: `chore/e06-3h-devcheck-model-proxy`

## 9. 다음 개발 단계 권장사항

### A. STRICT 모드에서 "200/ETag/304"까지 결정적으로 재현 가능한 테스트 픽스처 표준화

**목표**: `STRICT_MODEL_CACHE=1`에서 항상 200 + ETag + 304 + Cache-Control + Content-Length가 재현되어 dev_check가 환경/사용자에 의존하지 않도록 고정.

**표준안(추천, 결정성 최우선):**

1. 허용된 테스트 모델 ID를 하나 고정 (예: `local-llm-v1` 또는 `local-llm-fixture`)
2. 업스트림에 항상 존재하는 작은 파일을 둠:
   - `/<modelId>/manifest.json` (수 KB, 절대 삭제 금지)
3. dev_check STRICT 모드에서 이 파일로:
   - HEAD 200 확인
   - ETag 존재 확인
   - If-None-Match로 304 확인
   - Cache-Control, Content-Length 확인

**추가 개선(선택, 캐시/에러 분기 강화):**

- "허용된 modelId + 의도적 404(파일 미존재)" 케이스를 표준화해
- "정상 헤더 계약 검증"과 "404 처리 분기"를 명확히 분리

**핵심**: STRICT가 "403로 FAIL 되는지"만 보지 않고, "캐시 계약이 맞는지(200/304)"까지 안정적으로 검증하도록 만드는 것.

### B. CI에서의 모드 운영 원칙 고정(문서/스크립트로)

**권장 운영:**

- PR/일상 CI: 기본 모드
- 릴리즈/승인 게이트(또는 nightly): `STRICT_MODEL_CACHE=1` 강제
  → 업스트림 안정성과 개발 속도의 균형

### C. 문서에 "주석 줄 복사 금지" 1줄 추가(터미널 혼선 재발 방지)

**주의**: 문서의 주석 줄(`# ...`)은 복사하지 말고, 명령어 줄만 실행하십시오.

문서(Playbook/SOP)에 위 1줄을 고정하여, zsh에서 `#` 주석 라인을 그대로 실행하여 발생하는 불필요한 에러를 방지합니다.

---

**보고서 작성일**: 2025-12-22  
**최종 검증자**: 개발팀  
**상태**: PASS (최종 종료)
