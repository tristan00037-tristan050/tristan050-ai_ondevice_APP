# R7-H 파일럿 배포 체크리스트

## 배포 전 확인사항

### 1. 로컬 환경 (개발자 머신)

#### ✅ 할 수 있는 작업
- [x] 코드 커밋 및 푸시
- [x] 태그 생성 및 푸시
- [x] 로컬 BFF 실행 및 테스트
- [x] 검증 스크립트 실행

#### ❌ 할 수 없는 작업
- [ ] Helm 배포 (Kubernetes 클러스터 필요)
- [ ] 운영 환경 직접 배포

### 2. 운영 환경 (Kubernetes 클러스터)

#### 사전 요구사항
- [ ] Kubernetes 클러스터 접근 권한
- [ ] kubeconfig 설정 완료
- [ ] Helm 설치 및 설정
- [ ] GHCR 접근 권한 (이미지 pull)

#### 배포 절차

##### Step 1: 클러스터 연결 확인
```bash
# 클러스터 연결 확인
kubectl cluster-info

# 현재 컨텍스트 확인
kubectl config current-context

# namespace 확인
kubectl get namespace accounting
```

##### Step 2: 이미지 확인
```bash
# GHCR에서 이미지 확인
# 태그: r7-h-pilot-20251203
# 이미지: ghcr.io/tristan00037-tristan050/tristan050-ai_ondevice_APP/bff-accounting:r7-h-pilot-20251203
```

##### Step 3: Helm 배포
```bash
# 파일럿 테넌트 설정과 함께 배포
helm upgrade --install bff charts/bff-accounting \
  --set env.OS_TENANT_ALLOWLIST_JSON='["default","pilot-a"]' \
  --set image.tag=r7-h-pilot-20251203 \
  --set image.repository=ghcr.io/tristan00037-tristan050/tristan050-ai_ondevice_APP/bff-accounting \
  --namespace accounting \
  --wait --timeout 5m
```

##### Step 4: 배포 확인
```bash
# Pod 상태 확인
kubectl get pods -n accounting

# Deployment 상태 확인
kubectl get deployment bff-accounting -n accounting

# 로그 확인
kubectl logs -n accounting deployment/bff-accounting --tail=50
```

##### Step 5: 검증
```bash
# 헬스 체크
kubectl port-forward -n accounting deployment/bff-accounting 8081:8081 &
./scripts/verify_pilot_gating.sh http://localhost:8081
```

## 로컬 테스트 (Kubernetes 없이)

### BFF 로컬 실행

```bash
# 환경변수 설정
export OS_TENANT_ALLOWLIST_JSON='["default","pilot-a"]'
export USE_PG=1
export DATABASE_URL="postgres://app:app@localhost:5432/app"

# 빌드 및 실행
cd packages/bff-accounting
npm run build
node dist/index.js
```

### 검증 스크립트 실행

```bash
# BFF가 localhost:8081에서 실행 중일 때
./scripts/verify_pilot_gating.sh http://localhost:8081
```

## 배포 옵션

### 옵션 1: GitHub Actions 자동 배포 (권장)

1. 태그 푸시
   ```bash
   git push origin r7-h-pilot-20251203
   ```

2. GitHub Actions가 자동으로:
   - Docker 이미지 빌드
   - GHCR에 퍼블리시
   - Helm 배포 (kubeconfig가 설정된 경우)

### 옵션 2: 수동 Helm 배포

운영 환경에서 직접 Helm 명령어 실행 (위 Step 3 참조)

### 옵션 3: 로컬 테스트만

Kubernetes 없이 로컬에서 BFF 실행 및 테스트

## 문제 해결

### 오류: "kubernetes cluster unreachable"

**원인**: 로컬 환경에 Kubernetes 클러스터가 없음

**해결**:
- 로컬 테스트: BFF를 직접 실행하여 테스트
- 운영 배포: 운영 환경(Kubernetes 클러스터)에서 Helm 배포

### 오류: "image pull failed"

**원인**: GHCR 이미지가 아직 퍼블리시되지 않음

**해결**:
1. GitHub Actions 워크플로우 완료 확인
2. GHCR에서 이미지 존재 확인
3. 이미지 pull 권한 확인

### 오류: "namespace not found"

**원인**: `accounting` namespace가 없음

**해결**:
```bash
kubectl create namespace accounting
```

## 배포 후 검증

### 1. 헬스 체크
```bash
curl http://<bff-url>/health
curl http://<bff-url>/ready
```

### 2. 파일럿 게이팅 검증
```bash
./scripts/verify_pilot_gating.sh http://<bff-url>
```

### 3. 로그 확인
```bash
kubectl logs -n accounting deployment/bff-accounting | grep TENANT_NOT_ENABLED
```

### 4. 메트릭 확인
```bash
curl http://<bff-url>/metrics | grep http_requests_total
```

### 5. 외부 Adapter 동기화 상태 체크

- [ ] `external_sync_last_ts_seconds` 지표 확인  
      → 각 소스별 마지막 동기화 시간 지연이 **5분 이내인지** 확인

- [ ] `external_sync_errors_total` 지표 확인  
      → 최근 1일 기준 오류율이 **5% 이하인지** 확인

- [ ] `ExternalSyncStale` 알람 여부 확인  
      → 알람 발생 시, **10분 이내 해소**되지 않으면 P1 이슈로 분류

## 롤백 절차

문제 발생 시 이전 버전으로 롤백:

```bash
./scripts/rollback.sh r7-final-20251203
```

또는:

```bash
helm upgrade --install bff charts/bff-accounting \
  --set image.tag=r7-final-20251203 \
  --namespace accounting
```

