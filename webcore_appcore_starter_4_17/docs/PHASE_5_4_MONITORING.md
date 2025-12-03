# Phase 5.4 모니터링/관측성 강화

Phase 5.4 모니터링 및 관측성 강화 작업 완료 문서입니다.

## 📋 구현 완료 항목

### 1. Prometheus 메트릭 수집

**파일**: `packages/collector-node-ts/src/metrics/prometheus.ts`

**구현 사항**:
- 간단한 메트릭 수집기 (카운터, 게이지, 히스토그램)
- Prometheus 형식 내보내기 (`/metrics` 엔드포인트)
- 리포트 수집률, API 응답 시간, 에러율 추적
- 서명 요청 수, 번들 다운로드 수 추적
- 데이터베이스 연결 상태 모니터링

**메트릭 종류**:

1. **카운터 (Counter)**
   - `collector_reports_ingested_total{tenant="..."}` - 리포트 수집 수
   - `collector_http_errors_total{endpoint="...", status="..."}` - HTTP 에러 수
   - `collector_sign_requests_total{tenant="..."}` - 서명 요청 수
   - `collector_bundle_downloads_total{tenant="..."}` - 번들 다운로드 수

2. **게이지 (Gauge)**
   - `collector_database_connected` - 데이터베이스 연결 상태 (0 또는 1)
   - `collector_reports_active{tenant="..."}` - 활성 리포트 수

3. **히스토그램 (Histogram)**
   - `collector_http_request_duration_seconds{endpoint="...", status="..."}` - API 응답 시간
     - `_avg` - 평균 응답 시간
     - `_count` - 요청 수

**엔드포인트**: `GET /metrics`

**응답 형식**:
```
collector_reports_ingested_total{tenant="default"} 5
collector_http_request_duration_seconds_avg{endpoint="/reports",status="200"} 0.123
collector_http_request_duration_seconds_count{endpoint="/reports",status="200"} 10
collector_database_connected 1
```

## 🚀 사용 방법

### 메트릭 엔드포인트 접근

```bash
# Prometheus 메트릭 조회
curl http://localhost:9090/metrics
```

### Prometheus 서버 연동

`prometheus.yml` 설정 예시:

```yaml
scrape_configs:
  - job_name: 'collector'
    static_configs:
      - targets: ['localhost:9090']
    metrics_path: '/metrics'
    scrape_interval: 15s
```

## 📊 모니터링 대시보드 (Grafana 예시)

### 주요 메트릭

1. **리포트 수집률**
   - `rate(collector_reports_ingested_total[5m])` - 분당 리포트 수집 수

2. **API 응답 시간**
   - `collector_http_request_duration_seconds_avg` - 평균 응답 시간
   - `histogram_quantile(0.95, collector_http_request_duration_seconds)` - 95 백분위수

3. **에러율**
   - `rate(collector_http_errors_total[5m])` - 분당 에러 수
   - `rate(collector_http_errors_total[5m]) / rate(collector_http_request_duration_seconds_count[5m])` - 에러율

4. **데이터베이스 상태**
   - `collector_database_connected` - 연결 상태 (1 = 연결됨, 0 = 연결 안 됨)

5. **서명/번들 활동**
   - `rate(collector_sign_requests_total[5m])` - 분당 서명 요청 수
   - `rate(collector_bundle_downloads_total[5m])` - 분당 번들 다운로드 수

## 🔧 향후 개선 사항

### 권장 사항

1. **prom-client 라이브러리 사용**
   - 현재는 간단한 메트릭 수집기를 사용하지만, 프로덕션에서는 `prom-client` 사용 권장
   - 더 정확한 히스토그램 버킷, 레이블 관리 등

2. **구조화된 로깅**
   - Winston/Pino 로거 통합
   - 로그 레벨 관리 (debug, info, warn, error)
   - 로그 집계 및 검색 (ELK Stack 또는 CloudWatch)

3. **분산 트레이싱**
   - OpenTelemetry 통합
   - 요청 추적 (요청 ID 기반)
   - 성능 병목 지점 식별

4. **헬스 체크 강화**
   - 데이터베이스 연결 상태 확인 (✅ 완료)
   - 외부 서비스 의존성 확인
   - 상세 헬스 체크 엔드포인트 (`/health/detailed`)

## 📚 참고 문서

- `docs/PHASE_5_4_KICKOFF.md` - Phase 5.4 킥오프 문서
- `packages/collector-node-ts/src/metrics/prometheus.ts` - 메트릭 수집기 구현
- `packages/collector-node-ts/src/index.ts` - 메트릭 엔드포인트 통합

## 🧪 테스트

### 메트릭 수집 확인

```bash
# 1. 리포트 인제스트
curl -X POST http://localhost:9090/ingest/qc \
  -H "X-Api-Key: collector-key" \
  -H "X-Tenant: default" \
  -H "Content-Type: application/json" \
  -d '{"status": {"api": "pass"}}'

# 2. 메트릭 조회
curl http://localhost:9090/metrics | grep collector_reports_ingested_total
```

### Prometheus 연동 테스트

```bash
# Prometheus 서버에서 타겟 확인
# http://localhost:9090/metrics 엔드포인트가 정상적으로 스크랩되는지 확인
```

---

**버전**: Phase 5.4 모니터링 v1
**날짜**: 2025-01-XX
**상태**: ✅ 기본 메트릭 수집 완료


