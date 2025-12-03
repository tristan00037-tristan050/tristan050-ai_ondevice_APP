# 배포 옵션 가이드

프로덕션 배포를 위한 두 가지 옵션을 제공합니다.

## 🎯 배포 옵션 비교

| 옵션 | 장점 | 단점 | 권장 대상 |
|------|------|------|----------|
| **GitHub Actions** | 자동화, CI/CD 통합, 승인 프로세스 | GitHub 설정 필요 | ✅ **권장** |
| **로컬 kubectl** | 직접 제어, 즉시 실행 | 클러스터 연결 필요, 수동 작업 | 클러스터 접근 가능한 경우 |

---

## 옵션 1: GitHub Actions를 통한 배포 (권장) ⭐

로컬에서 Kubernetes 클러스터에 연결할 수 없는 경우, GitHub Actions를 통해 자동 배포할 수 있습니다.

### 사전 준비

1. **GitHub Secrets 설정**
   - GitHub 저장소 → Settings → Secrets and variables → Actions
   - 다음 Secrets 추가:

   ```
   DB_HOST=postgres-service
   DB_PORT=5432
   DB_NAME=collector
   DB_USER=postgres
   DB_PASSWORD=<실제-비밀번호>
   API_KEYS=default:collector-key:admin,teamA:teamA-key:operator
   EXPORT_SIGN_SECRET=<실제-시크릿>
   ENCRYPTION_KEY=<실제-암호화-키>
   KUBE_CONFIG_PRODUCTION=<base64-encoded-kubeconfig>
   ```

2. **Kubeconfig 파일 준비** (선택사항)
   - 프로덕션 클러스터의 kubeconfig 파일을 base64로 인코딩:
   ```bash
   cat ~/.kube/config | base64
   ```
   - 결과를 `KUBE_CONFIG_PRODUCTION` Secret에 저장

### 배포 실행

1. **GitHub Actions 워크플로우 실행**
   - GitHub 저장소 → Actions 탭
   - "Deploy" 워크플로우 선택
   - "Run workflow" 클릭
   - Environment: `production` 선택
   - 2인 승인 완료 (Release Manager + SRE)

2. **배포 상태 확인**
   - Actions 탭에서 배포 진행 상황 확인
   - 각 단계의 로그 확인

3. **스모크 테스트**
   ```bash
   # 프로덕션 URL로 스모크 테스트
   COLLECTOR_URL=https://collector.production.com \
   API_KEY=$PROD_API_KEY \
   TENANT_ID=default \
   npm run smoke
   ```

### 장점

- ✅ 로컬 클러스터 연결 불필요
- ✅ 자동화된 배포 프로세스
- ✅ 승인 프로세스 내장
- ✅ 배포 이력 자동 기록
- ✅ 롤백 용이

---

## 옵션 2: 로컬 kubectl을 통한 배포

로컬에서 Kubernetes 클러스터에 직접 연결할 수 있는 경우.

### 사전 준비

1. **클러스터 연결**
   ```bash
   # 클러스터 정보 확인
   ./scripts/setup-k8s.sh check
   
   # 클러스터 연결 (예: Azure AKS)
   ./scripts/setup-k8s.sh azure <resource-group> <cluster-name>
   
   # 연결 확인
   kubectl config current-context
   kubectl cluster-info
   ```

2. **Namespace 생성**
   ```bash
   kubectl create namespace production
   ```

3. **Secret 생성**
   ```bash
   # 환경 변수 설정
   export DB_HOST=postgres-service
   export DB_PORT=5432
   export DB_NAME=collector
   export DB_USER=postgres
   export DB_PASSWORD=your-secure-password
   export API_KEYS="default:collector-key:admin"
   export EXPORT_SIGN_SECRET=your-secure-sign-secret
   export ENCRYPTION_KEY=your-encryption-key
   
   # Secret 생성
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

### 배포 실행

1. **Docker 이미지 빌드 및 푸시**
   ```bash
   # 이미지 빌드
   docker build -t collector:5.4.0 -f packages/collector-node-ts/Dockerfile .
   docker build -t bff:5.4.0 -f packages/bff-node-ts/Dockerfile .
   docker build -t ops-console:5.4.0 -f packages/ops-console/Dockerfile .
   
   # 이미지 태그 (레지스트리에 맞게)
   docker tag collector:5.4.0 <registry>/collector:5.4.0
   docker tag bff:5.4.0 <registry>/bff:5.4.0
   docker tag ops-console:5.4.0 <registry>/ops-console:5.4.0
   
   # 이미지 푸시
   docker push <registry>/collector:5.4.0
   docker push <registry>/bff:5.4.0
   docker push <registry>/ops-console:5.4.0
   ```

2. **Kubernetes 배포**
   ```bash
   # Deployment 적용
   kubectl apply -f k8s/collector-deployment.yaml -n production
   kubectl apply -f k8s/collector-hpa.yaml -n production
   
   # 배포 상태 확인
   kubectl rollout status deployment/collector -n production
   
   # Pod 상태 확인
   kubectl get pods -n production -l app=collector
   ```

3. **스모크 테스트**
   ```bash
   COLLECTOR_URL=https://collector.production.com \
   API_KEY=$PROD_API_KEY \
   TENANT_ID=default \
   npm run smoke
   ```

---

## 🚨 현재 상황: 클러스터 미연결

현재 상태:
- ❌ Kubernetes 클러스터 미연결
- ❌ 컨텍스트 미설정
- ❌ 로컬 클러스터 없음

### 권장 조치

**옵션 1 (권장)**: GitHub Actions를 통한 배포
- 로컬 클러스터 연결 불필요
- 자동화된 배포 프로세스
- 승인 프로세스 내장

**옵션 2**: 프로덕션 클러스터 정보 확인 후 연결
- 클러스터 정보 필요 (클라우드/리전/이름)
- 클러스터 관리자 권한 필요
- 연결 스크립트 사용: `./scripts/setup-k8s.sh <provider> ...`

---

## 📋 배포 체크리스트

### 공통 체크리스트

- [ ] 환경 변수 설정 완료 (`config/*.env.sample` 참고)
- [ ] CI 전체 Green 확인
- [ ] 보안 점검 완료 (Trivy, 권한 E2E)
- [ ] 백업 리허설 완료 (STG)

### GitHub Actions 배포

- [ ] GitHub Secrets 설정 완료
- [ ] Kubeconfig 준비 (선택사항)
- [ ] 배포 워크플로우 실행
- [ ] 2인 승인 완료
- [ ] 배포 상태 확인
- [ ] 스모크 테스트 통과

### 로컬 kubectl 배포

- [ ] 클러스터 연결 확인
- [ ] Namespace 생성
- [ ] Secret 생성
- [ ] Docker 이미지 빌드 및 푸시
- [ ] Kubernetes 배포
- [ ] 배포 상태 확인
- [ ] 스모크 테스트 통과

---

## 🔄 롤백 절차

배포 실패 시:

### GitHub Actions 배포

1. Actions 탭 → 최근 배포 워크플로우
2. "Re-run failed jobs" 또는 이전 버전으로 롤백
3. 또는 수동으로 이전 버전 배포

### 로컬 kubectl 배포

```bash
# 이전 버전으로 롤백
kubectl rollout undo deployment/collector -n production

# 롤백 상태 확인
kubectl rollout status deployment/collector -n production
```

자세한 내용은 `docs/ROLLBACK_PLAN.md` 참고

---

## 📚 참고 문서

- `docs/GO_LIVE_EXECUTION_PLAN.md` - Go-Live 실행 계획
- `docs/QUICK_START_K8S.md` - Kubernetes 빠른 시작
- `docs/KUBERNETES_SETUP.md` - Kubernetes 설정 가이드
- `docs/ROLLBACK_PLAN.md` - 롤백 플랜
- `.github/workflows/deploy.yml` - 배포 워크플로우

---

## 💡 다음 단계

**현재 상황**: Kubernetes 클러스터 미연결

**권장 조치**:
1. **GitHub Actions 배포** (옵션 1) - 가장 간단하고 안전
2. 또는 **프로덕션 클러스터 정보 확인** 후 연결 (옵션 2)

프로덕션 클러스터 정보를 알려주시면 연결 방법을 안내하겠습니다.


