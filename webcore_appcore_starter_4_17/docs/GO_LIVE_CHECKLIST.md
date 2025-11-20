# Go-Live 체크리스트

Phase 5.4 프로덕션 배포 전 10분 스모크 체크리스트입니다.

## ⏱️ 10분 스모크 체크리스트

### 1. 인프라 준비 (2분)

- [ ] 데이터베이스 연결 확인
  ```bash
  psql -h $DB_HOST -U $DB_USER -d $DB_NAME -c "SELECT 1"
  ```
- [ ] Kubernetes 클러스터 접근 가능
  ```bash
  kubectl cluster-info
  kubectl get nodes
  ```
- [ ] Docker Registry 접근 가능
  ```bash
  docker login $REGISTRY_URL
  ```
- [ ] 환경 변수 설정 확인
  ```bash
  env | grep -E "DB_|API_|EXPORT_|ENCRYPTION_|SLACK_|PAGERDUTY_"
  ```

### 2. 배포 실행 (3분)

- [ ] CI/CD 파이프라인 통과 확인
  - GitHub Actions에서 최신 커밋의 CI 상태 확인
- [ ] Docker 이미지 빌드 및 푸시
  ```bash
  docker build -t collector:5.4.0 -f packages/collector-node-ts/Dockerfile .
  docker push collector:5.4.0
  ```
- [ ] Kubernetes 배포
  ```bash
  kubectl apply -f k8s/collector-deployment.yaml
  kubectl rollout status deployment/collector
  ```

### 3. 스모크 테스트 (5분)

#### 3.1 헬스 체크

```bash
# Collector 헬스 체크
curl http://collector.production/health
# 예상 응답: {"status":"ok","service":"collector","database":"connected"}

# BFF 헬스 체크
curl http://bff.production/health
# 예상 응답: {"status":"ok","service":"bff"}

# Ops Console 접근
curl -I http://ops-console.production
# 예상 응답: HTTP/1.1 200 OK
```

#### 3.2 인제스트 테스트

```bash
# 리포트 인제스트
curl -X POST http://collector.production/ingest/qc \
  -H "X-Api-Key: $API_KEY" \
  -H "X-Tenant: $TENANT_ID" \
  -H "Content-Type: application/json" \
  -d '{
    "status": {"api": "pass", "jwks": "pass"},
    "policy": {"policy_version": "v1.0.0"},
    "diff": {},
    "notes": []
  }'
# 예상 응답: {"id":"report-...","status":"ingested"}
```

#### 3.3 리포트 조회 테스트

```bash
# 리포트 목록 조회
curl http://collector.production/reports \
  -H "X-Api-Key: $API_KEY" \
  -H "X-Tenant: $TENANT_ID"
# 예상 응답: {"reports":[...],"pagination":{...}}

# 리포트 상세 조회
REPORT_ID=$(curl -s http://collector.production/reports \
  -H "X-Api-Key: $API_KEY" \
  -H "X-Tenant: $TENANT_ID" | jq -r '.reports[0].id')

curl http://collector.production/reports/$REPORT_ID \
  -H "X-Api-Key: $API_KEY" \
  -H "X-Tenant: $TENANT_ID"
# 예상 응답: {"id":"...","report":{...}}
```

#### 3.4 서명 및 번들 다운로드 테스트

```bash
# 리포트 서명
SIGN_RESPONSE=$(curl -s -X POST http://collector.production/reports/$REPORT_ID/sign \
  -H "X-Api-Key: $API_KEY" \
  -H "X-Tenant: $TENANT_ID")

TOKEN=$(echo $SIGN_RESPONSE | jq -r '.token')

# 번들 다운로드
curl "http://collector.production/reports/$REPORT_ID/bundle.zip?token=$TOKEN" \
  -H "X-Api-Key: $API_KEY" \
  -H "X-Tenant: $TENANT_ID" \
  -o /tmp/bundle.zip

# 번들 검증
unzip -l /tmp/bundle.zip
# 예상 출력: qc_report.json, qc_report.md 포함
```

#### 3.5 타임라인 테스트

```bash
# 타임라인 조회
curl "http://collector.production/timeline?window_h=24" \
  -H "X-Api-Key: $API_KEY" \
  -H "X-Tenant: $TENANT_ID"
# 예상 응답: {"window_h":24,"buckets":[...]}
```

#### 3.6 메트릭 테스트

```bash
# Prometheus 메트릭 조회
curl http://collector.production/metrics | grep collector_
# 예상 출력: 메트릭 목록
```

### 4. 역할/권한 E2E 테스트 (선택사항)

**참고**: 현재 구현에서는 역할 가드가 선택사항입니다. 향후 구현 시 다음 테스트를 수행하세요.

- [ ] Viewer 역할: 리포트 조회만 가능
- [ ] Operator 역할: 리포트 조회 + 서명 가능
- [ ] Auditor 역할: 리포트 조회 + 감사 로그 조회 가능
- [ ] Admin 역할: 모든 권한 (Retention 실행 포함)

---

## 🚨 장애 대응

### 데이터베이스 연결 실패

```bash
# 데이터베이스 연결 확인
kubectl exec -it deployment/collector -- node -e "
  const { Pool } = require('pg');
  const pool = new Pool({
    host: process.env.DB_HOST,
    port: process.env.DB_PORT,
    database: process.env.DB_NAME,
    user: process.env.DB_USER,
    password: process.env.DB_PASSWORD,
  });
  pool.query('SELECT 1').then(() => console.log('OK')).catch(e => console.error(e));
"
```

### Pod 상태 확인

```bash
# Pod 상태 확인
kubectl get pods -l app=collector

# Pod 로그 확인
kubectl logs -l app=collector --tail=100

# Pod 이벤트 확인
kubectl describe pod -l app=collector
```

### 롤백 실행

```bash
# 이전 버전으로 롤백
kubectl rollout undo deployment/collector

# 롤백 상태 확인
kubectl rollout status deployment/collector
```

---

## ✅ Go-Live 승인 기준

다음 조건을 모두 만족해야 프로덕션 배포를 승인할 수 있습니다:

- [ ] 모든 스모크 테스트 통과
- [ ] 데이터베이스 연결 정상
- [ ] 헬스 체크 정상
- [ ] 인제스트/조회/서명/다운로드 플로우 정상
- [ ] 메트릭 수집 정상
- [ ] 알림 시스템 동작 확인 (선택사항)
- [ ] 백업 스크립트 실행 가능
- [ ] 롤백 플랜 검증 완료

---

## 📝 체크리스트 실행

```bash
# 스모크 테스트 스크립트 실행
./scripts/smoke.sh

# 또는 수동으로 각 단계 실행
# 1. 인프라 준비
# 2. 배포 실행
# 3. 스모크 테스트
```

---

**예상 소요 시간**: 10분
**담당자**: DevOps 팀
**승인자**: 기술 리더

