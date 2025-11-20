# 관측성 대시보드 노트

Grafana 대시보드 구성 및 알림 규칙 권장 사항입니다.

## 📊 Grafana 대시보드 패널 권장

### 1. Collector 서비스 상태

**패널 1: 서비스 헬스**
- **메트릭**: `up{job="collector"}`
- **타입**: Stat
- **임계값**: 
  - Green: `== 1`
  - Red: `== 0`

**패널 2: 데이터베이스 연결 상태**
- **메트릭**: `collector_database_connected`
- **타입**: Stat
- **임계값**:
  - Green: `== 1`
  - Red: `== 0`

**패널 3: Pod 상태**
- **메트릭**: `kube_pod_status_phase{pod=~"collector-.*"}`
- **타입**: Table
- **표시**: Pod 이름, 상태, 재시작 횟수

---

### 2. API 성능

**패널 4: API 응답 시간 (평균)**
- **메트릭**: `collector_http_request_duration_seconds_avg{endpoint="/reports"}`
- **타입**: Time Series
- **단위**: seconds
- **임계값**: 
  - 경고: `> 0.2` (200ms)
  - 위험: `> 0.5` (500ms)

**패널 5: API 응답 시간 (95 백분위수)**
- **메트릭**: `histogram_quantile(0.95, collector_http_request_duration_seconds{endpoint="/reports"})`
- **타입**: Time Series
- **단위**: seconds

**패널 6: API 요청 수**
- **메트릭**: `rate(collector_http_request_duration_seconds_count[5m])`
- **타입**: Time Series
- **단위**: requests/second

**패널 7: API 에러율**
- **메트릭**: `rate(collector_http_errors_total[5m]) / rate(collector_http_request_duration_seconds_count[5m])`
- **타입**: Time Series
- **단위**: percentage
- **임계값**:
  - 경고: `> 0.01` (1%)
  - 위험: `> 0.05` (5%)

---

### 3. 리포트 수집

**패널 8: 리포트 수집률**
- **메트릭**: `rate(collector_reports_ingested_total[5m])`
- **타입**: Time Series
- **단위**: reports/second
- **레이블**: `tenant`

**패널 9: 리포트 수집 수 (누적)**
- **메트릭**: `collector_reports_ingested_total`
- **타입**: Time Series
- **단위**: count
- **레이블**: `tenant`

**패널 10: 서명 요청 수**
- **메트릭**: `rate(collector_sign_requests_total[5m])`
- **타입**: Time Series
- **단위**: requests/second
- **레이블**: `tenant`

**패널 11: 번들 다운로드 수**
- **메트릭**: `rate(collector_bundle_downloads_total[5m])`
- **타입**: Time Series
- **단위**: downloads/second
- **레이블**: `tenant`

---

### 4. Rate Limiting

**패널 12: Rate Limit 초과 수**
- **메트릭**: `rate(collector_http_errors_total{status="429"}[5m])`
- **타입**: Time Series
- **단위**: errors/second

**패널 13: Rate Limit 초과 비율**
- **메트릭**: `rate(collector_http_errors_total{status="429"}[5m]) / rate(collector_http_request_duration_seconds_count[5m])`
- **타입**: Time Series
- **단위**: percentage

---

### 5. 데이터베이스

**패널 14: 데이터베이스 연결 수**
- **메트릭**: `pg_stat_database_numbackends{datname="collector"}`
- **타입**: Stat
- **단위**: connections

**패널 15: 데이터베이스 크기**
- **메트릭**: `pg_database_size_bytes{datname="collector"}`
- **타입**: Time Series
- **단위**: bytes

**패널 16: 리포트 테이블 행 수**
- **메트릭**: `pg_stat_user_tables_n_tup_ins{relname="reports"} - pg_stat_user_tables_n_tup_del{relname="reports"}`
- **타입**: Time Series
- **단위**: rows

---

## 🔔 알림 규칙 권장

### Critical 알림 (PagerDuty)

**알림 1: 서비스 다운**
- **조건**: `up{job="collector"} == 0`
- **지속 시간**: 1분
- **액션**: PagerDuty 트리거

**알림 2: 데이터베이스 연결 실패**
- **조건**: `collector_database_connected == 0`
- **지속 시간**: 1분
- **액션**: PagerDuty 트리거

**알림 3: 에러율 급증**
- **조건**: `rate(collector_http_errors_total[5m]) / rate(collector_http_request_duration_seconds_count[5m]) > 0.1`
- **지속 시간**: 5분
- **액션**: PagerDuty 트리거

**알림 4: 응답 시간 급증**
- **조건**: `collector_http_request_duration_seconds_avg{endpoint="/reports"} > 1`
- **지속 시간**: 5분
- **액션**: PagerDuty 트리거

---

### Warning 알림 (Slack)

**알림 5: 에러율 증가**
- **조건**: `rate(collector_http_errors_total[5m]) / rate(collector_http_request_duration_seconds_count[5m]) > 0.05`
- **지속 시간**: 10분
- **액션**: Slack 알림

**알림 6: 응답 시간 증가**
- **조건**: `collector_http_request_duration_seconds_avg{endpoint="/reports"} > 0.5`
- **지속 시간**: 10분
- **액션**: Slack 알림

**알림 7: Rate Limit 초과 증가**
- **조건**: `rate(collector_http_errors_total{status="429"}[5m]) > 10`
- **지속 시간**: 5분
- **액션**: Slack 알림

**알림 8: 리포트 수집률 감소**
- **조건**: `rate(collector_reports_ingested_total[5m]) < 0.1`
- **지속 시간**: 15분
- **액션**: Slack 알림

**알림 9: 데이터베이스 크기 증가**
- **조건**: `increase(pg_database_size_bytes{datname="collector"}[1h]) > 1073741824` (1GB)
- **지속 시간**: 즉시
- **액션**: Slack 알림

---

### Info 알림 (Slack)

**알림 10: 배포 완료**
- **조건**: `kube_deployment_status_replicas_updated{deployment="collector"} != kube_deployment_status_replicas_available{deployment="collector"}`
- **지속 시간**: 0분 (즉시)
- **액션**: Slack 알림

---

## 📈 BlockAlert 임계값 권장

### BLOCK 급증 알림

**알림 11: BLOCK 급증 (24시간)**
- **메트릭**: 타임라인 API의 `block` 카운트 증가율
- **조건**: 
  - 현재 24h BLOCK 수 > 이전 24h BLOCK 수 * 1.5 (50% 증가)
  - 또는 현재 24h BLOCK 수 > 100
- **지속 시간**: 5분
- **액션**: Slack 알림 (운영팀 합의 필요)

**알림 12: BLOCK 급증 (1시간)**
- **메트릭**: 타임라인 API의 `block` 카운트 증가율
- **조건**: 
  - 현재 1h BLOCK 수 > 이전 1h BLOCK 수 * 2.0 (100% 증가)
  - 또는 현재 1h BLOCK 수 > 20
- **지속 시간**: 즉시
- **액션**: PagerDuty 트리거 (운영팀 합의 필요)

**운영팀 합의 필요 사항**:
- BLOCK 급증 임계값 (50%, 100% 등)
- BLOCK 절대값 임계값 (100, 20 등)
- 알림 레벨 (Warning vs Critical)
- 알림 수신자

---

## 🔧 Prometheus 설정 예시

```yaml
# prometheus.yml
scrape_configs:
  - job_name: 'collector'
    static_configs:
      - targets: ['collector.production:9090']
    metrics_path: '/metrics'
    scrape_interval: 15s
    scrape_timeout: 10s
```

---

## 📊 대시보드 JSON 임포트

Grafana 대시보드 JSON은 별도 파일로 제공됩니다:
- `grafana/collector-dashboard.json` (예정)

---

## 🚀 대시보드 구성 순서

1. **Prometheus 데이터 소스 추가**
   - URL: `http://prometheus:9090`
   - Access: Server (default)

2. **대시보드 임포트**
   - Grafana UI → Dashboards → Import
   - JSON 파일 업로드 또는 ID 입력

3. **알림 채널 설정**
   - Slack Webhook URL 설정
   - PagerDuty Integration Key 설정

4. **알림 규칙 생성**
   - Alerting → Alert rules → New alert rule
   - 위 권장 알림 규칙 추가

---

## 📚 참고 문서

- `docs/PHASE_5_4_MONITORING.md` - 모니터링 가이드
- `packages/collector-node-ts/src/metrics/prometheus.ts` - 메트릭 구현

---

**대시보드 구성 담당자**: DevOps 팀
**알림 규칙 승인**: 운영팀 리더

