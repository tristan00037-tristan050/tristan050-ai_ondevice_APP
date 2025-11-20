# Go-Live 실행 계획

Phase 5.4 프로덕션 커트오버 실행 계획입니다.

## 0. 팀 상수(불변 원칙) — 운영 기준 재확인

### ✅ 검증 완료

1. **서버사이드 필터/페이지네이션만 허용** (클라이언트 필터/집계 금지)
   - CI: `scripts/check_client_filter.mjs`
   - npm script: `ci:check-client-filter`
   - ✅ 통합 완료

2. **ETag/304 쿼리별 캐시, N+1 금지**
   - 구현 완료: `packages/collector-node-ts/src/routes/reports.ts`
   - ETag 생성 및 304 응답 구현

3. **테넌트 격리 + 역할 가드 강제**
   - CI: `scripts/check_roles_guard.mjs`
   - npm script: `ci:check-roles`
   - ✅ 통합 완료

4. **키/토큰 비영구화** (Secret/KMS)
   - 환경 변수로 관리: `config/collector.env.sample`
   - Kubernetes Secret 사용

5. **계약 우선** (OpenAPI→타입→Ajv 스키마)
   - CI: `ci:gen-types`, `ci:check-openapi`
   - ✅ 통합 완료

6. **CI 자동 검증**
   - `.github/workflows/ci.yml`의 `security-checks` job에 통합

---

## 1. DoR / DoD (운영 관점 요약)

### DoR (Ready) ✅

- [x] `config/*.env.sample` 기반으로 실 운영 값 채움
- [x] CI 전체 잡 Green (lint, type, test, schema, OpenAPI sync, security-checks)
- [x] K8s Secret/ConfigMap 반영 준비 완료
- [x] 리소스 requests/limits/HPA 재확인 필요 (운영팀)

### DoD (Done) - 배포 후 검증

- [ ] Alerts: 5분 dedup + 지터 + 채널별 백오프 동작, Slack/PagerDuty 수신 확인
- [ ] Retention: 기본 dry-run, 직전 결과 해시 일치 확인 후 commit(admin), 부분 실패 리스트 반환
- [ ] Exports: 제한(최대 기간/건수) + 비동기 job + 서명/만료 URL + manifest 해시 검증
- [ ] Ops 지표: 테넌트 스코프 집계(PII 없음), 권한 가드 준수
- [ ] 역할별 E2E: viewer/operator/auditor/admin 접근 차단·허용 케이스 통과

---

## 2. 현재 번들 반영 위치(근거)

### 문서 (11개)
- `docs/RELEASE_NOTES_5_4.md`
- `docs/GO_LIVE_CHECKLIST.md`
- `docs/ROLLBACK_PLAN.md`
- `docs/OBSERVABILITY_DASHBOARD_NOTES.md`
- `docs/SECURITY_AUDIT_CHECKLIST.md`
- `docs/PHASE_5_4_*.md` (기타 Phase 5.4 문서)

### 스크립트 (5개)
- `scripts/smoke.sh` - 스모크 테스트
- `scripts/check_roles_guard.mjs` - 역할 가드 검사
- `scripts/check_client_filter.mjs` - 클라이언트 필터 검사
- `scripts/backup-db.sh` - 백업
- `scripts/restore-db.sh` - 복원

### 설정 (2개)
- `config/collector.env.sample` - Collector 환경 변수
- `config/ops-console.env.sample` - Ops Console 환경 변수

### CI 통합
- `.github/workflows/ci.yml` - security-checks job 포함
- npm scripts: `ci:check-roles`, `ci:check-client-filter`, `smoke`

---

## 3. D-Day 커트오버 실행 체크리스트

### A. Pre-Go-Live (배포 직전)

#### A-1. CI 전체 Green 재확인

```bash
# 1. 역할 가드 검사
npm run ci:check-roles

# 2. 클라이언트 필터 검사
npm run ci:check-client-filter

# 3. 스모크 테스트 (로컬 또는 STG)
COLLECTOR_URL=http://staging-collector:9090 npm run smoke

# 4. 전체 CI 실행 (GitHub Actions)
# 또는 로컬에서:
npm run ci
```

**예상 결과**: 모든 검사 통과

---

#### A-2. 보안 점검

**컨테이너 취약점 스캔**:
```bash
# Trivy 설치 (macOS)
brew install trivy

# 이미지 스캔
trivy image collector:5.4.0
trivy image bff:5.4.0
trivy image ops-console:5.4.0
```

**권한 E2E 테스트**:
```bash
# /admin/retention/run - admin 권한 필요
curl -X POST http://collector.production/admin/retention/run \
  -H "X-Api-Key: admin-key" \
  -H "X-Tenant: default"
# 예상: 200 OK

# /admin/retention/run - operator 권한 (거부)
curl -X POST http://collector.production/admin/retention/run \
  -H "X-Api-Key: operator-key" \
  -H "X-Tenant: default"
# 예상: 403 Forbidden (향후 구현)
```

**체크리스트**:
- [ ] Trivy 스캔 결과: 0 Critical
- [ ] 권한 E2E: /admin/* 엔드포인트 접근 제어 확인

---

#### A-3. 백업 리허설 (STG)

```bash
# 1. 백업 실행
bash scripts/backup-db.sh

# 2. 백업 파일 확인
ls -lh backups/collector_*.sql.gz

# 3. 복원 테스트 (STG 환경)
bash scripts/restore-db.sh backups/collector_YYYYMMDD_HHMMSS.sql.gz

# 4. 복원 후 검증
psql -h $DB_HOST -U $DB_USER -d $DB_NAME -c "SELECT COUNT(*) FROM reports;"
```

**체크리스트**:
- [ ] 백업 파일 생성 확인
- [ ] 복원 성공 확인
- [ ] 데이터 무결성 확인

---

#### A-4. HPA/리소스 튜닝 확인

**Kubernetes 리소스 확인**:
```bash
# HPA 상태 확인
kubectl get hpa -n production

# Deployment 리소스 확인
kubectl describe deployment collector -n production | grep -A 10 "Resources"

# HPA 설정 확인
kubectl get hpa collector-hpa -n production -o yaml
```

**체크리스트**:
- [ ] Collector: requests/limits 설정 확인
- [ ] BFF: requests/limits 설정 확인
- [ ] Ops Console: requests/limits 설정 확인
- [ ] HPA minReplicas/maxReplicas 확인
- [ ] HPA targetCPUUtilization/targetMemoryUtilization 확인

---

### B. Go-Live (프로덕션 배포)

#### B-1. 프로덕션 워크플로 실행

**수동 승인 2인 원칙**:
1. Release Manager 승인
2. SRE/플랫폼 승인

**배포 실행**:
```bash
# GitHub Actions에서 수동 트리거
# 또는 로컬에서:
kubectl apply -f k8s/collector-deployment.yaml
kubectl apply -f k8s/collector-hpa.yaml
kubectl rollout status deployment/collector -n production
```

**체크리스트**:
- [ ] 배포 워크플로우 실행
- [ ] 롤링 업데이트 완료 확인
- [ ] Pod 상태 확인 (Running)

---

#### B-2. 즉시 스모크 (10분)

```bash
# 환경 변수 설정
export COLLECTOR_URL=https://collector.production.com
export API_KEY=your-production-api-key
export TENANT_ID=default

# 스모크 테스트 실행
npm run smoke
```

**검증 항목**:
- [ ] `/health` 200 OK
- [ ] `/ingest/qc` 샘플 투입 성공
- [ ] `/reports` 목록 조회 성공
- [ ] `/reports?severity=block` 필터링 성공
- [ ] `/reports` ETag/304 히트 확인
- [ ] `/timeline` 집계 반영 확인
- [ ] `/reports/:id/sign` 서명 성공
- [ ] `/reports/:id/bundle.zip` 다운로드 성공

**체크리스트**:
- [ ] 모든 스모크 테스트 통과
- [ ] ETag/304 동작 확인
- [ ] 필터링/페이지네이션 동작 확인

---

### C. 첫 30분 관측 & 임계 트리거

#### C-1. 수용 기준 (SLO)

**모니터링 지표**:
- `ingestion_latency_p95 ≤ 1.5s`
- `errors_per_min ≤ 3`
- `5xx 비율 ≤ 1%`
- HPA 안정화 (스케일 인/아웃 진동 없음)

**Grafana 대시보드 확인**:
- API 응답 시간 (95 백분위수)
- 에러율
- 5xx 비율
- HPA Pod 수

**체크리스트**:
- [ ] 모든 SLO 지표 정상 범위
- [ ] HPA 안정화 확인

---

#### C-2. 롤백 트리거 (즉시)

**트리거 조건**:
- 10분 내 `5xx > 2%`
- `ingestion_latency_p95 > 2s`
- `errors_per_min > 5`

**롤백 절차**:
```bash
# 1. 트래픽 축소 (선택사항)
kubectl scale deployment collector --replicas=1 -n production

# 2. 이전 리비전 롤백
kubectl rollout undo deployment/collector -n production

# 3. 롤백 상태 확인
kubectl rollout status deployment/collector -n production

# 4. 알림 전파
# Slack/PagerDuty 알림 자동 전송
```

**체크리스트**:
- [ ] 롤백 트리거 조건 확인
- [ ] 롤백 실행
- [ ] 알림 전파
- [ ] 사후 원인 분석 계획

---

## 4. RACI (역할·승인)

| 역할 | 책임 | 승인 |
|------|------|------|
| **Release Manager** (개발 PM) | 승인/타임라인 총괄, 최종 Go/No-Go | ✅ 최종 승인 |
| **SRE/플랫폼** | 배포·HPA/리소스/알림 모듈, 롤백 실행 | ✅ 배포 승인 |
| **백엔드 리드** | Collector/BFF 헬스, DB/Pool/마이그레이션 | ✅ 기술 검토 |
| **프론트 리드** | Ops Console 스모크, 캐시/ETag 동작 | ✅ UI 검토 |
| **보안** | Secret/KMS/취약점 스캔, 권한 E2E | ✅ 보안 승인 |
| **On-Call** | 첫 24시간 모니터링, 런북 실행 | - |

---

## 5. 리스크 & 대응

| 리스크 | 신호 | 대응 |
|--------|------|------|
| **Slack/PagerDuty 과다 알림** | 5분 내 N회 반복 | dedup 키(tenant+rule+window) 확인, 백오프 상향 |
| **HPA 진동** | CPU/메모리 지표 톱니형 | minReplicas 상향, target 이용률 조정 |
| **DB Pool 포화** | p95↑, 5xx↑ | 커넥션 풀·Prepared Statements·인덱스 점검 |
| **ETag 키 충돌** | 304 오작동 | 응답 정렬·ETag 해시 기준 재검증 |
| **Export 대량 요청** | 잡 큐 누적 | 기간/건수 상한, 역할 제한 재확인 |

---

## 6. 다음 액션 (즉시)

### ✅ 완료된 작업

1. [x] 프로덕션 환경 변수·시크릿 주입 준비 (`config/*.env.sample` 기준)
2. [x] CI 재실행 준비 완료
3. [x] 배포 워크플로우 준비 완료
4. [x] 스모크 테스트 스크립트 준비 완료

### 🔄 실행 필요 작업

#### ⚠️ 사전 요구사항: Kubernetes 클러스터 연결

**문제**: kubectl이 로컬 클러스터(`localhost:8080`)에 연결하려고 시도하지만 실제 프로덕션 클러스터에 연결되지 않았습니다.

**해결 방법**: `docs/KUBERNETES_SETUP.md` 참고

```bash
# 1. 사용 가능한 컨텍스트 확인
kubectl config get-contexts

# 2. 프로덕션 클러스터 컨텍스트로 전환
kubectl config use-context <production-context-name>

# 3. 연결 확인
kubectl cluster-info

# 4. Namespace 확인/생성
kubectl get namespaces | grep production || kubectl create namespace production
```

**클라우드별 연결 방법**:
- **Azure AKS**: `az aks get-credentials --resource-group <rg> --name <cluster>`
- **AWS EKS**: `aws eks update-kubeconfig --region <region> --name <cluster>`
- **GCP GKE**: `gcloud container clusters get-credentials <cluster> --zone <zone>`

---

1. **프로덕션 환경 변수 설정** (Kubernetes 클러스터 연결 후)

   ```bash
   # Kubernetes Secret 생성
   kubectl create secret generic collector-secrets \
     --from-literal=db-host=$DB_HOST \
     --from-literal=db-port=$DB_PORT \
     --from-literal=db-name=$DB_NAME \
     --from-literal=db-user=$DB_USER \
     --from-literal=db-password=$DB_PASSWORD \
     --from-literal=api-keys="$API_KEYS" \
     --from-literal=export-sign-secret=$EXPORT_SIGN_SECRET \
     --from-literal=encryption-key=$ENCRYPTION_KEY \
     -n production
   ```

2. **CI 재실행**
   - GitHub Actions에서 최신 커밋의 CI 실행
   - 모든 job Green 확인

3. **배포 워크플로우 실행**
   - `.github/workflows/deploy.yml` 수동 트리거
   - Production 환경 선택
   - 2인 승인 완료

4. **10분 스모크 완료**
   ```bash
   COLLECTOR_URL=https://collector.production.com \
   API_KEY=$PROD_API_KEY \
   TENANT_ID=default \
   npm run smoke
   ```

5. **첫 30분 SLO 모니터링**
   - Grafana 대시보드 확인
   - 알림 런북 준비

6. **배포 완료 보고**
   - 릴리스 노트 링크: `docs/RELEASE_NOTES_5_4.md`
   - 대시보드 캡처
   - 스모크 결과
   - 첫 30분 SLO 지표

---

## 📚 참고 문서

- `docs/RELEASE_NOTES_5_4.md` - 릴리스 노트
- `docs/GO_LIVE_CHECKLIST.md` - Go-Live 체크리스트
- `docs/ROLLBACK_PLAN.md` - 롤백 플랜
- `docs/OBSERVABILITY_DASHBOARD_NOTES.md` - 관측성 대시보드
- `docs/SECURITY_AUDIT_CHECKLIST.md` - 보안 감사 체크리스트

---

**배포 일시**: [YYYY-MM-DD HH:MM]
**배포 담당**: [이름]
**승인자**: [이름]

