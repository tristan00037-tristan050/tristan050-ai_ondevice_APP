# Phase 5.4 운영 자동화

Phase 5.4 운영 자동화 작업 완료 문서입니다.

## 📋 구현 완료 항목

### 1. CI/CD 파이프라인 강화

**파일**: 
- `.github/workflows/ci.yml` - CI 파이프라인
- `.github/workflows/deploy.yml` - 배포 파이프라인
- `.github/workflows/backup.yml` - 백업 자동화

**구현 사항**:
- 자동 테스트 (Lint, TypeScript, Schema Validation)
- OpenAPI 타입 동기화 검증
- 자동 빌드 (모든 패키지)
- 자동 배포 (스테이징/프로덕션)
- 롤백 자동화 (태그 기반)
- 데이터베이스 백업 자동화 (매일 UTC 02:00)

**CI 파이프라인 단계**:
1. **Lint and TypeScript Check**: ESLint 및 TypeScript 타입 체크
2. **Schema Validation**: Ajv 기반 스키마 검증
3. **OpenAPI Type Sync**: OpenAPI 타입 생성 및 동기화 확인
4. **Build**: 모든 패키지 빌드
5. **Test**: 테스트 실행 (있는 경우)

**배포 파이프라인**:
- **Staging**: `main` 브랜치 푸시 시 자동 배포
- **Production**: 태그 푸시 (`v*`) 또는 수동 트리거 시 배포

---

### 2. Docker 컨테이너화

**파일**:
- `packages/collector-node-ts/Dockerfile` - Collector Dockerfile
- `packages/bff-node-ts/Dockerfile` - BFF Dockerfile
- `packages/ops-console/Dockerfile` - Ops Console Dockerfile
- `docker-compose.yml` - 로컬 개발용 Docker Compose

**구현 사항**:
- 멀티 스테이지 빌드 (빌더 + 프로덕션)
- 최적화된 이미지 크기 (Alpine Linux)
- 헬스 체크 포함
- 환경 변수 주입
- 보안 모범 사례 적용

**Docker Compose 구성**:
- PostgreSQL 데이터베이스
- Collector 서비스
- BFF 서비스
- Ops Console (Nginx)

**사용 방법**:
```bash
# 전체 스택 실행
docker-compose up -d

# 특정 서비스만 실행
docker-compose up -d postgres collector

# 로그 확인
docker-compose logs -f collector

# 중지
docker-compose down
```

---

### 3. Kubernetes 배포 매니페스트

**파일**:
- `k8s/collector-deployment.yaml` - Collector Deployment 및 Service
- `k8s/collector-hpa.yaml` - Horizontal Pod Autoscaler
- `k8s/collector-secret.yaml.example` - Secret 예시

**구현 사항**:
- Deployment (3 replicas)
- Service (LoadBalancer)
- Horizontal Pod Autoscaler (CPU/Memory 기반)
- Liveness/Readiness Probes
- Resource Limits/Requests
- Secret 관리

**배포 방법**:
```bash
# Secret 생성
kubectl create secret generic collector-secrets \
  --from-literal=db-host=postgres-service \
  --from-literal=db-password=your-password \
  --from-literal=api-keys="default:collector-key"

# 배포
kubectl apply -f k8s/collector-deployment.yaml
kubectl apply -f k8s/collector-hpa.yaml

# 상태 확인
kubectl get pods -l app=collector
kubectl get hpa collector-hpa
```

---

### 4. 백업 자동화

**파일**:
- `scripts/backup-db.sh` - 데이터베이스 백업 스크립트
- `scripts/restore-db.sh` - 데이터베이스 복원 스크립트
- `.github/workflows/backup.yml` - 자동 백업 워크플로우

**구현 사항**:
- PostgreSQL 백업 (pg_dump + gzip)
- 백업 파일 무결성 검증
- 보존 정책 (기본 30일)
- 자동 정리 (오래된 백업 삭제)
- GitHub Actions 자동 백업 (매일 UTC 02:00)

**사용 방법**:
```bash
# 수동 백업
./scripts/backup-db.sh

# 복원
./scripts/restore-db.sh ./backups/collector_20250101_120000.sql.gz
```

**환경 변수**:
```bash
DB_HOST=localhost
DB_PORT=5432
DB_NAME=collector
DB_USER=postgres
DB_PASSWORD=postgres
BACKUP_DIR=./backups
RETENTION_DAYS=30
```

---

### 5. 알림 시스템

**파일**: `packages/collector-node-ts/src/utils/notifications.ts`

**구현 사항**:
- Slack 웹훅 알림
- PagerDuty 통합 (Critical 이벤트)
- 에러 알림
- 성능 저하 알림
- 용량 임계값 알림
- 데이터베이스 연결 실패 알림
- Rate Limit 초과 알림

**알림 레벨**:
- `info`: 정보성 알림
- `warning`: 경고 알림
- `error`: 에러 알림
- `critical`: 긴급 알림 (PagerDuty 트리거)

**환경 변수**:
```bash
SLACK_WEBHOOK_URL=https://hooks.slack.com/services/...
EMAIL_RECIPIENTS=admin@example.com,ops@example.com
PAGERDUTY_INTEGRATION_KEY=your-pagerduty-key
```

**사용 예시**:
```typescript
import { notifyError, notifyPerformanceDegradation, notifyCapacityThreshold } from './utils/notifications.js';

// 에러 알림
await notifyError('Database Error', 'Failed to connect to database', { error: 'Connection timeout' });

// 성능 저하 알림
await notifyPerformanceDegradation('response_time', 200, 350);

// 용량 임계값 알림
await notifyCapacityThreshold('database_size', 0.85, 0.9);
```

---

## 🚀 사용 방법

### Docker Compose로 로컬 실행

```bash
# 전체 스택 실행
docker-compose up -d

# 데이터베이스 초기화
docker-compose exec collector npm run migrate:init

# 로그 확인
docker-compose logs -f

# 중지 및 정리
docker-compose down -v
```

### Kubernetes 배포

```bash
# 1. Secret 생성
kubectl create secret generic collector-secrets \
  --from-file=k8s/collector-secret.yaml

# 2. 배포
kubectl apply -f k8s/collector-deployment.yaml
kubectl apply -f k8s/collector-hpa.yaml

# 3. 상태 확인
kubectl get pods -l app=collector
kubectl get svc collector-service
kubectl get hpa collector-hpa
```

### 백업 및 복원

```bash
# 백업
export DB_PASSWORD=your-password
./scripts/backup-db.sh

# 복원
./scripts/restore-db.sh ./backups/collector_20250101_120000.sql.gz
```

---

## 🔧 향후 개선 사항

### CI/CD 개선

1. **통합 테스트**: E2E 테스트 자동화
2. **성능 테스트**: 부하 테스트 자동화
3. **보안 스캔**: 취약점 스캔 자동화
4. **카나리 배포**: 점진적 배포 전략

### 인프라 개선

1. **Service Mesh**: Istio 통합
2. **모니터링 스택**: Prometheus + Grafana 통합
3. **로깅 스택**: ELK Stack 통합
4. **분산 추적**: Jaeger 통합

### 백업 개선

1. **S3 업로드**: AWS S3 또는 다른 객체 스토리지에 백업 업로드
2. **증분 백업**: 전체 백업 + 증분 백업
3. **백업 검증**: 자동 복원 테스트

### 알림 개선

1. **이메일 알림**: SMTP 통합
2. **알림 라우팅**: 알림 레벨별 라우팅
3. **알림 집계**: 중복 알림 방지

---

## 📚 참고 문서

- `docs/PHASE_5_4_KICKOFF.md` - Phase 5.4 킥오프 문서
- `.github/workflows/` - CI/CD 워크플로우
- `k8s/` - Kubernetes 매니페스트
- `scripts/` - 백업/복원 스크립트
- `docker-compose.yml` - Docker Compose 설정

---

**버전**: Phase 5.4 운영 자동화 v1
**날짜**: 2025-01-XX
**상태**: ✅ 기본 운영 자동화 완료

