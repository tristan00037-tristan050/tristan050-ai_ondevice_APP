# 파일럿 환경 설정 가이드

## 개요

이 문서는 파일럿 운영을 위한 환경 설정 및 헬스체크 연동 가이드를 제공합니다.

---

## 파일럿용 환경 1세트 확정

### 기본 설정

#### DB
```
postgres://app:app@<host>:5432/app
```

#### BFF
```
http://<bff-host>:8081
```

#### 웹 (Backoffice)
```
http://<web-host>:5173
```

#### HUD (Expo/Web)
한 군데에서 대표님/고객에게 보여줄 **"데모용 URL"** 하나 정리

예:
- 로컬: `http://localhost:8081` (Expo Web)
- 스테이징: `https://demo-staging.example.com`
- 프로덕션: `https://demo.example.com`

#### 엔진 모드 설정 (R8-S2 신규)

**환경 변수**:
```bash
# HUD 앱 환경 변수
EXPO_PUBLIC_DEMO_MODE=live          # mock | live
EXPO_PUBLIC_ENGINE_MODE=local-llm  # mock | rule | local-llm | remote
```

**엔진 모드 설명**:
- `mock`: Mock 모드 (네트워크 호출 없음, 로컬 규칙 엔진)
- `rule`: 규칙 기반 엔진 (온디바이스 규칙 분류)
- `local-llm`: 온디바이스 LLM 엔진 (로컬 추론)
- `remote`: 원격 BFF 엔진 (서버 기반 추론)

**주의사항**:
- `EXPO_PUBLIC_DEMO_MODE=mock`일 때는 `EXPO_PUBLIC_ENGINE_MODE` 값과 관계없이 항상 mock/rule 엔진 사용
- 엔진 모드 변경 후 HUD 재시작 필요

---

## 헬스체크 연결

### 인프라 담당자 작업

#### 1. Liveness / Readiness Probe 설정

**Kubernetes 예시**:
```yaml
livenessProbe:
  httpGet:
    path: /healthz
    port: 8081
  initialDelaySeconds: 30
  periodSeconds: 10
  timeoutSeconds: 5
  failureThreshold: 3

readinessProbe:
  httpGet:
    path: /readyz
    port: 8081
  initialDelaySeconds: 10
  periodSeconds: 5
  timeoutSeconds: 3
  failureThreshold: 3
```

**Docker Compose 예시**:
```yaml
services:
  bff:
    healthcheck:
      test: ["CMD", "curl", "-f", "http://localhost:8081/healthz"]
      interval: 30s
      timeout: 10s
      retries: 3
      start_period: 40s
```

#### 2. 외부 인터넷 접근 제한

**Ingress/보안그룹 설정**:
- `/healthz`, `/readyz`는 **내부망/클러스터에서만 접근 가능**하도록 제한
- 외부 인터넷에서 직접 접근 불가능하도록 방화벽 규칙 설정

**예시 (Kubernetes Ingress)**:
```yaml
apiVersion: networking.k8s.io/v1
kind: Ingress
metadata:
  name: bff-accounting
  annotations:
    nginx.ingress.kubernetes.io/whitelist-source-range: "10.0.0.0/8,172.16.0.0/12,192.168.0.0/16"
spec:
  rules:
    - host: bff.example.com
      http:
        paths:
          - path: /healthz
            pathType: Exact
            backend:
              service:
                name: bff-accounting
                port:
                  number: 8081
          - path: /readyz
            pathType: Exact
            backend:
              service:
                name: bff-accounting
                port:
                  number: 8081
```

**예시 (AWS Security Group)**:
- 인바운드 규칙: 포트 8081은 내부 VPC CIDR에서만 허용
- `/healthz`, `/readyz`는 ALB Health Check에서만 접근 가능

---

## 헬스체크 엔드포인트 상세

### GET /healthz
**목적**: 단순 alive check

**응답**:
```json
{
  "status": "ok",
  "timestamp": "2025-12-08T01:00:00Z"
}
```

**사용처**:
- Kubernetes Liveness Probe
- Docker Health Check
- 모니터링 시스템 (Prometheus, Datadog 등)

---

### GET /readyz
**목적**: DB 연결 및 마이그레이션 상태 확인

**응답 (정상)**:
```json
{
  "status": "ready",
  "database": "connected",
  "migrations": "up-to-date",
  "timestamp": "2025-12-08T01:00:00Z"
}
```

**응답 (DB 연결 실패)**:
```json
{
  "status": "not-ready",
  "database": "disconnected",
  "error": "connection refused",
  "timestamp": "2025-12-08T01:00:00Z"
}
```

**응답 (마이그레이션 미적용)**:
```json
{
  "status": "not-ready",
  "database": "connected",
  "migrations": "pending",
  "pending_migrations": ["010_new_feature.sql"],
  "timestamp": "2025-12-08T01:00:00Z"
}
```

**사용처**:
- Kubernetes Readiness Probe
- 배포 전 상태 확인
- 모니터링 시스템 (서비스 트래픽 라우팅 전 확인)

---

## 모니터링 연동

### Prometheus 예시

```yaml
scrape_configs:
  - job_name: 'bff-accounting'
    metrics_path: '/metrics'
    static_configs:
      - targets: ['bff-accounting:8081']
    relabel_configs:
      - source_labels: [__address__]
        target_label: instance
```

### Grafana 대시보드

**Health Check 패널**:
- `/healthz` 응답 시간
- `/readyz` 상태 (ready/not-ready)
- DB 연결 상태
- 마이그레이션 상태

---

## 배포 체크리스트

### 배포 전
- [ ] DB 마이그레이션 완료 (`npm run db:migrate`)
- [ ] `/healthz` 응답 확인
- [ ] `/readyz` 응답 확인 (DB 연결, 마이그레이션 상태)
- [ ] Liveness/Readiness Probe 설정 확인
- [ ] HUD 환경 변수 설정 확인 (`EXPO_PUBLIC_ENGINE_MODE`, `EXPO_PUBLIC_DEMO_MODE`)

### 배포 후
- [ ] Kubernetes Pod 상태 확인 (`kubectl get pods`)
- [ ] Health Check 로그 확인
- [ ] 모니터링 시스템 연동 확인
- [ ] 외부 접근 제한 확인 (보안그룹/Ingress)
- [ ] OS Dashboard Engine Mode 카드 확인 (primary_mode가 의도한 값인지)

## 파일럿 일일 점검 항목 (R8-S2 신규)

### OS Dashboard 점검
1. **Engine Mode 카드 확인**
   - OS Dashboard → Engine Mode 카드 접근
   - `primary_mode`가 의도한 값(예: `local-llm`)인지 확인
   - `counts` 분포가 정상적인지 확인 (예: `local-llm`이 대부분이어야 함)

2. **Audit/리포트에서 engine_mode 분포 주간 확인**
   - 주간 리포트에서 엔진 모드별 사용 횟수 확인
   - 예상과 다른 모드가 많이 사용되고 있는지 확인
   - 필요 시 환경 변수 재확인

### HUD 점검
1. **HUD 상단 상태바 확인**
   - `Engine: On-device LLM` 또는 `Engine: Rule` 표시 확인
   - `Engine: Error` 표시 시 환경 변수 및 네트워크 상태 확인

2. **엔진 모드 전환 테스트**
   - `EXPO_PUBLIC_ENGINE_MODE` 변경 후 HUD 재시작
   - 상태바에 올바른 엔진 모드 표시 확인

---

## 트러블슈팅

### `/healthz` 응답 없음
- BFF 서버가 실행 중인지 확인
- 포트 8081이 열려있는지 확인
- 방화벽 규칙 확인

### `/readyz`가 `not-ready` 반환
- DB 연결 문자열 확인 (`DATABASE_URL`)
- DB 서버가 실행 중인지 확인
- 마이그레이션 실행 여부 확인 (`npm run db:migrate`)

### 외부에서 `/healthz` 접근 가능 (보안 이슈)
- Ingress/보안그룹 설정 확인
- 방화벽 규칙 재확인
- 내부망 전용으로 제한

---

## 참고

- [Health Check 엔드포인트 구현](../packages/bff-accounting/src/routes/health.ts)
- [Kubernetes Health Checks](https://kubernetes.io/docs/tasks/configure-pod-container/configure-liveness-readiness-startup-probes/)
- [Docker Health Checks](https://docs.docker.com/engine/reference/builder/#healthcheck)


