# SLO & Alerts (BFF Accounting)

## SLO (Service Level Objectives)

- **가용성(Availability)**: 99.9%
- **오류율(Error rate)**: 5분 이동평균 1% 이하 (경고 5%, 치명 10%)
- **지연(Latency)**: p95 < 500ms (경고 500ms, 치명 1s)

## 경보 규칙(Helm Values로 관리)

- `.values.alerts.enabled=true`
- `highErrorRate`, `highLatencyP95` 값으로 조정

### PrometheusRule 리소스

- `BffHighErrorRate`: 5분간 5xx 오류율이 5% 초과 시 경고
- `BffHighLatencyP95`: p95 지연시간이 0.5초 초과 시 경고

## 대시보드

- `.values.dashboard.enabled=true` → Grafana 자동 인식
- ConfigMap으로 대시보드 JSON 제공
- 패널:
  - RPS (초당 요청 수)
  - 5xx 오류율
  - Latency p95

## Ingress 설정

- `.values.ingress.enabled=true`
- Nginx Ingress Controller 사용
- RPS 제한: 20 req/s
- Body size 제한: 2MB

## OpenTelemetry 트레이싱

- `OTEL_ENABLED=1`로 활성화
- OTLP HTTP Exporter 사용
- 기본 엔드포인트: `http://localhost:4318/v1/traces`
- 환경 변수로 커스터마이징 가능

