# R7-H+4 개발 브리핑

## 개요

R7-H+4 스프린트는 R7-H 기준선을 확정하고, 실제 파일럿/PoC에서 사용할 수 있도록 API 계약, 에러 처리, UX를 안정화하는 작업입니다.

## R7-H 기준선 확정

### Server (BFF + DB)
- ✅ 001 ~ 009 마이그레이션 완료
- ✅ OS Dashboard 집계 뷰 (pilot, risk, manual_review, health)
- ✅ Health/Ready Check 엔드포인트
- ✅ osPolicyBridge 이전에 정의되어 인증 없이 접근 가능

### App (HUD)
- ✅ Mock/Live 모드 완전 분리
- ✅ Suggest 엔진 추상화 (localRuleEngineV1, remoteEngine)
- ✅ Offline Queue + Queue Inspector
- ✅ 에러 UX 일원화

### Web (Backoffice)
- ✅ OS Dashboard 완성
- ✅ Manual Review Workbench
- ✅ Demo 플로우 링크

## 개발 작업

### S-06: OS Dashboard & Risk/ManualReview API "실사용 모드"

#### S-06-1: OS Dashboard 파라미터화

**작업 내용**:
- `GET /v1/accounting/os/dashboard`에 쿼리 파라미터 추가:
  - `from=YYYY-MM-DD` (선택)
  - `to=YYYY-MM-DD` (선택)
  - `tenant=...` (선택)
  - 기본값: 지난 7일, default 테넌트

- 리포트 스크립트와 의미 일치:
  - `npm run report:pilot -- --from 2025-12-01 --to 2025-12-07 --tenant default`
  - Dashboard API: `?from=2025-12-01&to=2025-12-07&tenant=default`

- Health Summary 키 고정:
  - `success_rate_5m`
  - `error_rate_5m`
  - `p95_latency_5m`

**완료 기준**:
- 특정 날짜/테넌트로 Dashboard와 report 스크립트를 동시 실행 시 숫자가 일치
- R7_RELEASE_NOTES.md에 사용 예시 포함

#### S-06-2: Risk & Manual Review API 안정화

**작업 내용**:
- Risk API 표준 에러:
  - 존재하지 않는 posting_id → 404 + `RISK_NOT_FOUND`
  
- high 리스트 페이지네이션:
  - `page`, `page_size` 파라미터
  - 응답에 `has_more`, `next_page` 포함

- Manual Review 상태 enum 고정:
  - `PENDING`, `IN_REVIEW`, `APPROVED`, `REJECTED` 4개만 사용
  - SQL 및 코드에서 string literal 정리

- API 계약 문서화:
  - `API_MANUAL_REVIEW.md` 작성
  - 요청/응답 JSON 스키마 예시
  - typical flow 예시

**완료 기준**:
- 잘못된 ID/필터로 호출 시 항상 4xx + JSON 에러 (500 없음)
- 문서만 보고도 다른 팀이 직접 연동 가능한 수준

### A-07: Mock/Live 경계 + Offline Queue 가드

#### A-07-1: Mock 모드 네트워크 0 보장

**작업 내용**:
- `demo:app:mock` 모드에서:
  - `postSuggest`, `postApproval`, `postExport`, `postRecon*`, `postManualReview`
  - 모두 `if (isMock(cfg)) return [MOCK]` 경로를 먼저 타도록 재검증
  
- `offline-queue`:
  - `trySend`, `flushQueue`, `startQueueAutoFlush` → `isMock`일 때 바로 return

**완료 기준**:
- Chrome DevTools Network 탭 기준: `demo:app:mock` 실행 후 HTTP 요청 0건
- POC_PLAYBOOK.md에 체크포인트 명시

#### A-07-2: Live 모드 BFF 설정/권한 문제 노출

**작업 내용**:
- BFF 설정 검사 강화:
  - `EXPO_PUBLIC_BFF_URL`, `EXPO_PUBLIC_TENANT_ID`, `EXPO_PUBLIC_API_KEY` 검증
  - 비정상/빈 값 시 배너 표시

- 403/401/500 분리:
  - 401/403 → "권한 또는 API 키 문제입니다. 관리자에게 문의해 주세요."
  - 404 → "요청한 리소스를 찾을 수 없습니다. (URL/경로 확인 필요)"
  - 5xx → "서버 처리 중 오류가 발생했습니다. 잠시 후 다시 시도해 주세요."

- 상태바에 `Engine: BFF(remote – 오류)` 표시

**완료 기준**:
- BFF를 안 띄운 상태에서 `demo:app:live` 실행 시:
  - 콘솔 스택 대신 HUD 상단에 "BFF 연결 실패 / 설정 오류" 명확히 표시

#### A-07-3: Offline Queue 폭주 방지

**작업 내용**:
- 최대 큐 길이 상한: 100건
- 초과 시:
  - 더 이상 enqueue 하지 않음
  - HUD 상단/Modal에 "오프라인 큐가 가득 찼습니다" 메시지

- 오래된 항목 자동 삭제:
  - 24시간 이상된 항목은 flush 시점에 drop
  - QueueInspector에서 "(만료)" 표시

**완료 기준**:
- 네트워크를 끊고 200번 눌러도 큐가 100 이상 커지지 않음
- HUD가 "이제 더 못 쌓는다"는 걸 사용자에게 명확히 표시

### W-07: OS Dashboard "브리핑 화면" 완성

#### W-07-1: 카드 텍스트/툴팁 자연어화

**작업 내용**:
- 카드 라벨을 "사람 언어"로 재작성:
  - "지난 24시간 Top-1 정확도"
  - "지난 24시간 수동 검토 비율"
  - "최근 5분간 BFF 성공률"
  - "지난 24시간 HIGH Risk 거래 수"
  - "현재 수동 검토 대기 건 수"

- 각 카드에 툴팁 추가:
  - "Top-1: AI 추천 중 1순위가 실제 선택과 일치한 비율입니다."

#### W-07-2: Demo 배너 텍스트 보강

**작업 내용**:
- 제목: "데모/파일럿 모드"
- 내용 2줄:
  - "현재 대시보드는 데모/파일럿 데이터 기준으로 동작합니다."
  - "실제 도입 시에는 귀사 ERP/회계 시스템과 연동됩니다."
- `VITE_DEMO_MODE=false`이면 배너 숨김

#### W-07-3: Demo Flow 블록 완성

**작업 내용**:
- `/os/dashboard` 하단에:
  1. 회계 데모 열기 → `/demo/accounting`
  2. 수동 검토 Workbench 열기 → `/manual-review`
  3. Risk 모니터 열기 → Risk 섹션/페이지

**완료 기준**:
- POC_PLAYBOOK.md에서 "/os/dashboard를 열고, 아래 순서대로 버튼을 클릭하세요"로 전체 데모 설명 가능

## 체크리스트

### 개발팀 (R7-H+4 착수 전)

- [ ] 헬스체크 연동 확인
  - k8s/Docker Compose에서 `/healthz`, `/readyz` 사용
  - 내부망/클러스터에서만 접근하도록 방화벽 설정

- [ ] POC 플레이북 시나리오 리허설
  - `npm run demo:app:mock` → Network 탭 0건 확인
  - `npm run demo:app:live` → BFF 연결 확인
  - `npm run demo:web` → OS Dashboard 확인
  - POC_PLAYBOOK.md 대로 한 번 쭉 따라가기

## 커밋/PR 메시지 템플릿

### Server PR
```
이 변경은 OS 게이트웨이가 파일럿 품질/안정성을 숫자로 보여주는 Dashboard API와 Health Check 책임을 추가로 지도록 한다.

- OS Dashboard 파라미터화 (from/to/tenant)
- Health Summary 키 고정 (success_rate_5m, error_rate_5m, p95_latency_5m)
- Risk & Manual Review API 안정화 (페이지네이션, 표준 에러)
```

### App(HUD) PR
```
이 기능은 회계/현장 담당자가 HUD 내에서 오프라인 큐와 에러 상태를 한눈에 파악하고, BFF 설정 문제를 화면에서 바로 인지할 수 있게 만든다.

- Mock 모드 네트워크 0 보장
- Live 모드 BFF 설정/권한 문제 노출 (401/403/404/5xx 분리)
- Offline Queue 폭주 방지 (최대 100건, 24시간 만료)
```

### Web(Backoffice) PR
```
이 화면 개편은 운영/대표/PoC 대상자가 /os/dashboard 하나만으로 AI 온디바이스 회계 OS의 상태와 데모 플로우를 이해할 수 있게 하는 것을 목표로 한다.

- 카드 텍스트/툴팁 자연어화
- Demo 배너 텍스트 보강
- Demo Flow 블록 완성
```

## 다음 단계

R7-H+4 완료 후:
1. 실제 파일럿 환경 배포
2. 외부 PoC 시연
3. 사용자 피드백 수집
4. R8 개발 계획 수립

