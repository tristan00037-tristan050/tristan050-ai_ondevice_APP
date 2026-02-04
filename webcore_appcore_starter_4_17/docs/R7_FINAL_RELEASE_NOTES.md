# R7 Final Release Notes

## 개요

R7 릴리스는 OS 통합, 외부 어댑터 실연동, 제품화(Backoffice/HUD UX), 모바일 CI 정규화를 포함합니다.

## 주요 변경사항

### R7-S1: OS 통합
- OS 정책 헤더 브릿지 미들웨어 (`osPolicyBridge`)
- 감사 검색 API (`/v1/accounting/audit`)
- OS 요약 API (`/v1/accounting/os/summary`)
- 감사 인덱스 마이그레이션 (004_audit_idx.sql)
- OS 요약 뷰 마이그레이션 (005_os_summary_views.sql)
- Ops-Console AccountingCard 컴포넌트

### R7-S2: 외부 어댑터 실연동
- `external_ledger` 및 `external_ledger_offset` 테이블 (003_external_ledger.sql)
- `ExternalLedgerAdapter` 인터페이스 및 `BankSandboxAdapter` 구현
- 동기화 유즈케이스 (`reconciliation_sync.ts`) - Prometheus 메트릭 지원
- 워커 스크립트 (`worker_sync_external.mjs`) - CronJob 실행용
- BFF 상태 API (`/v1/accounting/os/sources`)
- Helm CronJob 템플릿 및 PrometheusRule 경보

### R7-S3: 제품화 & 모바일 CI
- **Backoffice 화면 3종**:
  - `AuditList.tsx`: 감사 로그 검색/필터/페이지네이션
  - `ExportJobs.tsx`: Export Job 상태 모니터링
  - `ReconSessions.tsx`: Reconciliation 세션 관리
- **HUD UX 개선**:
  - `QueueBadge`: 오프라인 큐 가시화 배지
  - `useOfflineQueue` hook: 큐 상태 모니터링
  - `ManualReviewButton`: 수동 검토 요청 버튼
  - 매칭 근거 표시 (rationale)
- **BFF API 확장**:
  - `POST /v1/accounting/audit/manual-review`: 수동 검토 요청
- **모바일 CI**:
  - `mobile.yml`: typecheck, expo bundle, EAS Android 빌드
  - `release.yml`: `gate_mobile` 의존성 추가, `r7-*` 태그 지원

## 운영 절차

### 서명 키 로테이션
1. 배포 시: `EXPORT_SIGN_SECRET`(신규) + `EXPORT_SIGN_SECRET_PREV`(기존) 동시 활성
2. 24~48시간 후(오류·로그 문제 없을 때) `EXPORT_SIGN_SECRET_PREV` 제거

### 롤백
```bash
# 이전 태그로 롤백 (예: r6-s4-20241201)
helm upgrade --install bff charts/bff-accounting \
  --set image.tag=r6-s4-20241201 \
  --namespace accounting

# 또는 최신 태그 확인 후 롤백
git tag | grep -E "r[67]-" | sort -V | tail -5
helm upgrade --install bff charts/bff-accounting \
  --set image.tag=<실제-태그-이름> \
  --namespace accounting
```

### 헬스 체크
```bash
curl -s https://<domain>/health
curl -s https://<domain>/ready
curl -s https://<domain>/metrics | head
```

### 상태 API 확인
```bash
curl -s -H 'X-Tenant: default' -H 'X-User-Id: ops' -H 'X-User-Role: admin' \
  https://<domain>/v1/accounting/os/sources | jq .
```

## 모니터링

### PromQL 예시

#### p95 latency (히스토그램)
```promql
histogram_quantile(0.95,
  sum by (le) (rate(http_request_duration_seconds_bucket{job="bff-accounting"}[5m]))
)
```

#### 5xx 비율
```promql
sum(rate(http_requests_total{job="bff-accounting", code=~"5.."}[10m]))
/
sum(rate(http_requests_total{job="bff-accounting"}[10m]))
```

#### 외부 동기화 지연(초)
```promql
max_over_time((time() - external_sync_last_ts_seconds{job="bff-accounting"} )[5m:1m])
```

### SLO 기준
- 가용성: 99.9%
- p95 latency: ≤ 300ms
- 5xx error rate: < 0.5% (10분 윈도)

### 알람
- `ExternalSyncStale`: 외부 동기화 지연 5분 초과 시 경보
- `BffHighErrorRate`: 5xx 에러율 > 5%
- `BffHighLatencyP95`: p95 레이턴시 > 0.5s

## 알려진 이슈/제약

1. **React Native 타입 오류**: `app-expo` 빌드 시 일부 타입 오류가 발생하지만 기능에는 영향 없음 (`|| true` 처리)
2. **EAS 빌드**: `EAS_TOKEN`이 없으면 Android 빌드가 스킵됨 (선택적)
3. **오프라인 큐**: SecureStorage 기반이므로 대용량 데이터에는 부적합

## 마이그레이션 가이드

### 데이터베이스
```bash
export DATABASE_URL="postgres://app:app@localhost:5432/app"
npm run db:migrate
```

적용되는 마이그레이션:
- 001_init.sql
- 002_audit.sql
- 003_external_ledger.sql (신규)
- 004_audit_idx.sql
- 005_os_summary_views.sql

### 환경 변수
```bash
# OS 정책 브릿지
OS_POLICY_BRIDGE_ENFORCE=true
OS_ROLE_MAP_JSON='{"viewer":"viewer","operator":"operator","auditor":"auditor","admin":"admin"}'

# 외부 어댑터
BANK_SBX_BASE=https://sandbox.example-bank.com
BANK_SBX_TOKEN=your-token
```

## 다음 단계

### R7-H: 파일럿 운영
- 1~2개 테넌트 대상 기능 플래그/allowlist 제한
- 모니터링 대시보드 구축
- 피드백 루프 설정

### R8: 정확도·규칙 고도화
- 골든셋 확대 (≥100~200건)
- 규칙/스코어 튜닝
- 모바일 CI 강화

