# GitHub Actions 배포 설정 가이드

GitHub Actions를 통한 프로덕션 배포 설정 가이드입니다.

## 🚀 빠른 시작

### 1. GitHub Secrets 설정

GitHub 저장소 → **Settings** → **Secrets and variables** → **Actions** → **New repository secret**

다음 Secrets를 추가하세요:

#### 필수 Secrets (프로덕션)

```
DB_HOST=postgres-service
DB_PORT=5432
DB_NAME=collector
DB_USER=postgres
DB_PASSWORD=<실제-비밀번호>
API_KEYS=default:collector-key:admin,teamA:teamA-key:operator
EXPORT_SIGN_SECRET=<실제-시크릿>
ENCRYPTION_KEY=<실제-암호화-키>
```

#### 선택적 Secrets (Kubernetes 배포 시)

```
KUBE_CONFIG_PRODUCTION=<base64-encoded-kubeconfig>
```

**Kubeconfig 인코딩 방법**:
```bash
cat ~/.kube/config | base64
```

#### Staging Secrets (선택사항)

```
DB_HOST_STAGING=postgres-staging
DB_PORT_STAGING=5432
DB_NAME_STAGING=collector
DB_USER_STAGING=postgres
DB_PASSWORD_STAGING=<staging-비밀번호>
API_KEYS_STAGING=default:staging-key:admin
EXPORT_SIGN_SECRET_STAGING=<staging-시크릿>
ENCRYPTION_KEY_STAGING=<staging-암호화-키>
KUBE_CONFIG_STAGING=<base64-encoded-staging-kubeconfig>
```

---

### 2. GitHub Actions 워크플로우 확인

1. GitHub 저장소 → **Actions** 탭
2. 왼쪽 사이드바에서 **"Deploy to Production"** 워크플로우 확인
3. 워크플로우가 보이지 않으면:
   - `.github/workflows/deploy.yml` 파일이 저장소에 커밋되어 있는지 확인
   - 브랜치가 `main` 또는 `master`인지 확인

---

### 3. 배포 실행

#### 방법 1: 수동 트리거 (권장)

1. GitHub 저장소 → **Actions** 탭
2. 왼쪽 사이드바에서 **"Deploy to Production"** 선택
3. **"Run workflow"** 버튼 클릭
4. 입력 필드 설정:
   - **Environment**: `production` 또는 `staging` 선택
   - **Version**: 버전 태그 (예: `5.4.0`) 또는 `latest` 유지
5. **"Run workflow"** 클릭
6. **2인 승인** (Production 환경의 경우)

#### 방법 2: 태그를 통한 자동 배포

```bash
# 로컬에서 태그 생성 및 푸시
git tag v5.4.0
git push origin v5.4.0
```

태그가 푸시되면 자동으로 Production 배포가 시작됩니다.

---

## 📋 워크플로우 단계

### 1. Build and Push Docker Images

- Collector, BFF, Ops Console 이미지 빌드
- GitHub Container Registry (ghcr.io)에 푸시
- 이미지 태그: `latest`, `staging`, `production`, 버전 태그

### 2. Deploy to Staging (선택사항)

- Staging 환경에 배포
- `KUBE_CONFIG_STAGING` Secret이 설정된 경우에만 실행

### 3. Deploy to Production

- Production 환경에 배포
- **2인 승인 필요** (GitHub Environment 설정)
- `KUBE_CONFIG_PRODUCTION` Secret이 설정된 경우에만 실행

---

## 🔧 GitHub Environment 설정 (Production 승인)

Production 배포에 승인 프로세스를 추가하려면:

1. GitHub 저장소 → **Settings** → **Environments**
2. **"New environment"** 클릭
3. 이름: `production`
4. **"Required reviewers"** 추가:
   - Release Manager
   - SRE/플랫폼 담당자
5. **"Save protection rules"** 클릭

이제 Production 배포 시 2인 승인이 필요합니다.

---

## 🐳 Docker 이미지 확인

배포 후 이미지가 올바르게 빌드되었는지 확인:

1. GitHub 저장소 → **Packages** 탭
2. 다음 패키지 확인:
   - `collector`
   - `bff`
   - `ops-console`

또는 명령어로:

```bash
# GitHub Container Registry 로그인
echo $GITHUB_TOKEN | docker login ghcr.io -u USERNAME --password-stdin

# 이미지 확인
docker pull ghcr.io/USERNAME/collector:latest
docker pull ghcr.io/USERNAME/bff:latest
docker pull ghcr.io/USERNAME/ops-console:latest
```

---

## 🚨 문제 해결

### 문제: "Deploy to Production" 워크플로우가 보이지 않음

**해결**:
1. `.github/workflows/deploy.yml` 파일이 저장소에 있는지 확인
2. 파일이 `main` 또는 `master` 브랜치에 있는지 확인
3. GitHub Actions가 활성화되어 있는지 확인:
   - Settings → Actions → General
   - "Allow all actions and reusable workflows" 선택

### 문제: "KUBE_CONFIG_PRODUCTION not found"

**해결**:
- Kubernetes 배포가 필요 없는 경우: Secret을 설정하지 않으면 배포 단계가 건너뜀
- Kubernetes 배포가 필요한 경우: `KUBE_CONFIG_PRODUCTION` Secret 추가

### 문제: "Permission denied" 또는 "Unauthorized"

**해결**:
1. GitHub Token 권한 확인
2. Packages 권한 확인:
   - Settings → Actions → General
   - "Read and write permissions" 선택

### 문제: Docker 이미지 빌드 실패

**해결**:
1. Dockerfile 경로 확인
2. 빌드 컨텍스트 확인
3. 의존성 설치 확인

---

## 📊 배포 상태 확인

### GitHub Actions에서 확인

1. **Actions** 탭 → 최근 워크플로우 실행
2. 각 단계의 로그 확인:
   - ✅ 초록색: 성공
   - ❌ 빨간색: 실패
   - ⏸️ 노란색: 진행 중 또는 승인 대기

### Kubernetes에서 확인 (KUBE_CONFIG 설정 시)

```bash
# Pod 상태 확인
kubectl get pods -n production -l app=collector

# 배포 상태 확인
kubectl rollout status deployment/collector -n production

# 로그 확인
kubectl logs -n production -l app=collector --tail=100
```

---

## 🔄 롤백

배포 실패 시:

### 방법 1: GitHub Actions에서 롤백

1. **Actions** 탭 → 실패한 워크플로우
2. **"Re-run failed jobs"** 클릭
3. 또는 이전 성공한 워크플로우 재실행

### 방법 2: Kubernetes에서 롤백

```bash
# 이전 버전으로 롤백
kubectl rollout undo deployment/collector -n production

# 롤백 상태 확인
kubectl rollout status deployment/collector -n production
```

---

## 📚 참고 문서

- `docs/DEPLOYMENT_OPTIONS.md` - 배포 옵션 가이드
- `docs/GO_LIVE_EXECUTION_PLAN.md` - Go-Live 실행 계획
- `.github/workflows/deploy.yml` - 배포 워크플로우 파일

---

## ✅ 체크리스트

배포 전 확인:

- [ ] GitHub Secrets 설정 완료
- [ ] KUBE_CONFIG_PRODUCTION 설정 (Kubernetes 배포 시)
- [ ] GitHub Environment 설정 (Production 승인)
- [ ] `.github/workflows/deploy.yml` 파일 커밋
- [ ] Actions 탭에서 워크플로우 확인
- [ ] Docker 이미지 빌드 테스트 (로컬)

배포 후 확인:

- [ ] 워크플로우 실행 성공
- [ ] Docker 이미지 푸시 확인 (Packages 탭)
- [ ] Kubernetes 배포 확인 (KUBE_CONFIG 설정 시)
- [ ] 스모크 테스트 통과
- [ ] 헬스 체크 통과

---

**다음 단계**: GitHub Secrets 설정 후 배포 워크플로우를 실행하세요!


