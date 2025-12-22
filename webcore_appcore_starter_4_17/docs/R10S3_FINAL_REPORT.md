# R10-S3 최종 종료 보고서

## 1. 최종 판정

**FINAL PASS**

- ✅ build PASS
- ✅ dev_check PASS
- ✅ repo clean (r10-s3-llm-poc == origin/r10-s3-llm-poc)

## 2. 이번 장애가 2일 걸린 구조적 원인 (재발 방지 관점)

이번 이슈는 **기능 버그가 아니라 표준 부재로 인한 반복 장애**였습니다.

### 경로/경계 표준 부재

- Web ↔ BFF 분리 환경에서 CORS preflight가 "헤더 추가"마다 깨지는 구조
- 모델 아티팩트 로딩 경로가 외부 도메인으로 빠질 수 있는 리스크

### 재현/증빙 표준 부재

- DevTools 의존 증빙은 브라우저/환경에 따라 재현이 흔들림
- src 수정 ↔ dist 실행 불일치로 "코드는 바뀌었는데 로그/동작은 그대로" 반복

### Fail-fast/Fail-closed 부족

- DB/환경변수 문제를 런타임 500으로 늦게 맞는 형태 (스크립트에서 조기 차단이 필요)

## 3. 이번에 "표준으로 강제"한 것 (재발 방지 핵심)

### (A) 실행 표준: 스크립트 only

**로컬 실행/Live QA는 스크립트만 허용 (수동 kill/export 금지)**

```bash
./scripts/dev_bff.sh restart
./scripts/dev_check.sh
./scripts/dev_web.sh
npm run policy:check
```

### (B) CORS 표준: dev only reflect + localhost only

- dev 환경에서만 preflight 요청 헤더를 반사(Reflect)하여 "헤더 추가 시 재발" 제거
- Origin은 localhost/127.0.0.1만 허용
- 운영에서는 reflect 금지 (고정 allowlist 유지)

### (C) 텔레메트리 표준: meta-only 강제 + 서버 방화벽

- `/v1/os/llm-usage`는 **meta-only(eventType, suggestionLength)**만 전송
- 원문 텍스트 계열 키(prompt/text/message/content/… 등)는 서버에서 즉시 400 차단
- 도메인/레지스트리는 fail-closed, 미지원은 suggestion_error로 수렴

### (D) Real inference 표준: Adapter + 실패 UX 고정

- InferenceAdapter 구조로 Stub/Real 전환 고정
- Real(WebLLM) 실패 시:
  - suggestion_error 이벤트
  - Stub 자동 폴백
  - UI 멈춤 방지 (빈 결과 처리 + 진행률 UI)

### (E) 모델 아티팩트 경로/캐시 표준: BFF 프록시 + ETag/304 + Cache-Control

- 모델 파일은 동일 오리진 또는 BFF(`/v1/os/models/...`)로만 로딩
- 프록시에서:
  - ETag / 304 Not Modified 동작 확인
  - Cache-Control 정책 적용 (`public, max-age=86400`)
  - Content-Length 전달
  - (보안) allowlist / traversal / 확장자 제한 네거티브 테스트 통과
- CORS 중복 제거 (단일 applyDevCors만 유지)

## 4. dev_check PASS 증빙 (핵심만)

**PASS 기준 (자동):**

- ✅ healthz 200
- ✅ preflight 204
- ✅ llm-usage 204 (meta-only)
- ✅ cs tickets 200
- ✅ model proxy headers+cache+negative tests OK
  - ETag 존재
  - Cache-Control: `public, max-age=86400`
  - Content-Length 존재
  - If-None-Match → 304 동작
  - disallowed modelId → 403
  - path traversal → 400
  - disallowed extension → 400

## 5. 팀 공용 업스트림 표준 (v1)

### 환경변수

- `WEBLLM_UPSTREAM_BASE_URL` (끝 `/` 포함, 필수)
- `WEBLLM_ALLOWED_MODEL_IDS` (comma-separated, 선택)
- `WEBLLM_TEST_MODEL_ID=local-llm-v1` (기본값)
- `WEBLLM_TEST_MODEL_FILE=manifest.json` (기본값)

### 저장소 구조 고정

- `/webllm/<modelId>/<files...>`
- 모든 모델 폴더에 `manifest.json` 포함 (작은 probe 파일)

### 프록시 동작

- HEAD 요청 지원 (메타 정보만 확인)
- GET 요청 지원 (바디 스트리밍)
- If-None-Match → 304 Not Modified
- ETag pass-through
- Cache-Control: `public, max-age=86400`

## 6. 다음 단계 (R10-S4 권장 작업)

### 성능 계측 표준화

- 캐싱/재방문/메모리 계측 표준화
- 스트리밍 UX (토큰 생성 즉시 렌더링)

### 대용량 아티팩트 최적화

- 필요 시 Range 요청/206 지원 검토
- `immutable`을 장기 표준화하려면 URL 버저닝 (해시 세그먼트) 강제 후 적용

## 개발팀 결론 (한 줄)

이번 이슈는 기능 실패가 아니라 **OS 실행/검증/게이트 표준 부재로 인한 반복 장애**였고, 현재는 **SOP/정책게이트/방화벽/preflight 표준을 코드와 스크립트로 고정**하여 재발 가능성을 구조적으로 낮췄습니다.

