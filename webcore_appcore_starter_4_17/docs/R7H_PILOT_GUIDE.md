# R7-H 파일럿 운영 가이드

## 개요

R7-H는 파일럿 테넌트 대상 운영을 위한 준비 단계입니다. 제한된 테넌트만 접근 가능하도록 게이팅하고, 외부 어댑터 연결, 모니터링 대시보드, 피드백 루프를 구축합니다.

## 1. 파일럿 테넌트 게이팅

### 목적
UI 노출뿐 아니라 API 레벨에서도 파일럿 테넌트만 통과시키기

### 구현
`packages/bff-accounting/src/middleware/osPolicyBridge.ts`에 테넌트 allowlist 환경변수 지원 추가

### 설정

#### Helm values.yaml
```yaml
env:
  OS_POLICY_BRIDGE_ENFORCE: "true"
  OS_ROLE_MAP_JSON: '{"viewer":"viewer","operator":"operator","auditor":"auditor","admin":"admin"}'
  OS_TENANT_ALLOWLIST_JSON: '["default","pilot-a"]'  # 파일럿 테넌트만 허용
```

#### 환경변수
```bash
export OS_TENANT_ALLOWLIST_JSON='["default","pilot-a"]'
```

### 검증
```bash
# 파일럿 테넌트 (허용)
curl -H 'X-Tenant: default' -H 'X-User-Role: operator' http://localhost:8081/v1/accounting/audit

# 비파일럿 테넌트 (403 차단)
curl -H 'X-Tenant: pilot-b' -H 'X-User-Role: operator' http://localhost:8081/v1/accounting/audit
# 응답: {"error_code":"TENANT_NOT_ENABLED","tenant":"pilot-b",...}
```

## 2. 외부 어댑터 샌드박스 연결

### 근거
R7-S2에서 BankSandboxAdapter/CronJob/상태 API/알람까지 구현 완료

### 주요 파일
- `packages/data-pg/migrations/003_external_ledger.sql`
- `packages/service-core-accounting/src/adapters/BankSandboxAdapter.ts`
- `scripts/worker_sync_external.mjs`
- `charts/bff-accounting/templates/cronjob-sync-external.yaml`

### Helm values 설정
```yaml
env:
  BANK_SBX_BASE: "https://sandbox.example-bank.com"
  BANK_SBX_TOKEN: ""  # Kubernetes Secret에서 주입

adapters:
  bankSbx:
    enabled: true
    base: "https://sandbox.example-bank.com"
    tokenSecretName: "bank-sbx-secret"

cronJobs:
  syncExternal:
    enabled: true
    schedule: "*/5 * * * *"  # 5분 주기
    sinceDays: 7

alerts:
  ExternalSyncStale:
    enabled: true
    thresholdMinutes: 5
```

### Kubernetes Secret 생성
```bash
kubectl create secret generic bank-sbx-secret \
  --from-literal=TOKEN=your-sandbox-token \
  -n accounting
```

### 검증 쿼리 (운영 DB)
```sql
-- 최근 동기화된 외부거래 존재 여부
SELECT count(*) FROM external_ledger
WHERE tenant='default' AND ts >= now() - interval '10 minute';

-- 오프셋/커서 확인
SELECT * FROM external_ledger_offset 
WHERE tenant='default' 
ORDER BY updated_at DESC LIMIT 1;
```

### 상태 API 확인
```bash
curl -H 'X-Tenant: default' -H 'X-User-Role: admin' \
  http://localhost:8081/v1/accounting/os/sources | jq .
```

## 3. 운영 대시보드/알림 체크

### PromQL 스니펫

#### p95 latency
```promql
histogram_quantile(0.95,
  sum by (le) (rate(http_request_duration_seconds_bucket{job="bff-accounting"}[5m]))
)
```

#### 5xx 비율
```promql
sum(rate(http_requests_total{job="bff-accounting",code=~"5.."}[10m]))
/
sum(rate(http_requests_total{job="bff-accounting"}[10m]))
```

#### 외부 동기화 지연(초)
```promql
(time() - external_sync_last_ts_seconds{job="bff-accounting"})
```

### SLO 기준
- 가용성: 99.9%
- p95 latency: ≤ 300ms
- 5xx error rate: < 0.5% (10분 윈도)
- 외부 동기화 지연: ≤ 5분

### 알람
- `ExternalSyncStale`: 외부 동기화 지연 5분 초과 시 경보
- `BffHighErrorRate`: 5xx 에러율 > 5%
- `BffHighLatencyP95`: p95 레이턴시 > 0.5s

## 4. Backoffice/HUD 파일럿 시나리오

### HUD 오프라인 큐
1. 오프라인에서 승인/요청 수행
2. QueueBadge 카운트 증가 확인
3. 온라인 전환 시 자동 플러시 확인

### 수동 검토
1. HUD에서 ManualReviewButton 클릭
2. BFF `POST /v1/accounting/audit/manual-review` 호출 확인
3. Backoffice AuditList에서 `action=manual_review_request` 필터로 검출 확인

### Recon 근거
- HUD에 rationale 텍스트 노출 확인
- 정책 차단/실패 케이스 포함 확인

## 5. 릴리스/롤백 운용

### 키 로테이션
1. 배포 시: `EXPORT_SIGN_SECRET`(신규) + `EXPORT_SIGN_SECRET_PREV`(기존) 동시 활성
2. 24~48시간 후(오류·로그 문제 없을 때) `EXPORT_SIGN_SECRET_PREV` 제거

### 롤백
```bash
# Helm 사용
./scripts/rollback.sh <tag>

# kubectl 대안
./scripts/rollback-kubectl.sh <tag>
```

### 문서
- `docs/R7_FINAL_RELEASE_NOTES.md`
- `docs/ROLLBACK_GUIDE.md`
- `docs/R7_RETRO.md`

## 6. 실행 체크리스트

### 게이트
- ✅ gate-os-integration
- ✅ gate_mobile
- ✅ 정확도·데이터
- ✅ 퍼시스턴스
- ✅ no-artifacts
→ All Green

### API/관측
- ✅ `/health` OK
- ✅ `/ready` OK
- ✅ `/metrics` OK
- ✅ `/v1/accounting/os/sources` 값 정상
- ✅ `external_sync_*` 지표 갱신

### UX
- ✅ HUD(오프라인 배지·수동 검토·근거) 시나리오 통과
- ✅ Backoffice(필터/검색/페이지) 시나리오 통과

### 파일럿 게이팅
- ✅ `OS_TENANT_ALLOWLIST_JSON`으로 비파일럿 테넌트 403 차단 확인

### SLO
- ✅ p95 ≤ 300ms
- ✅ 5xx < 0.5%
- ✅ 동기화 지연 ≤ 5분
- ✅ 알람 라우팅 정상

## 7. 피드백 루프

### Backoffice 수동 검토 큐
- AuditList에 `action=manual_review_request` 필터 고정 노출
- 실패 케이스 자동 링크 (감사 이벤트 subject_id 포함)

### 운영 Slack/이슈 트래커
- 실패 케이스 자동 링크
- 감사 이벤트 subject_id 포함

## 8. 수용 기준 (AC)

- 파일럿 테넌트 일일 사용(HUD/Backoffice/OS 카드)
- 2~4주 누적 오류/수동 검토/미매칭 데이터 확보
- 대시보드/알람으로 운영자 자가 점검 가능

