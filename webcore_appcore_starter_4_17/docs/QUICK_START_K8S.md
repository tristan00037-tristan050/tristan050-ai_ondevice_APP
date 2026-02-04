# Kubernetes 빠른 시작 가이드

프로덕션 배포를 위한 Kubernetes 클러스터 연결 가이드입니다.

## 🚀 빠른 시작

### 1. 현재 상태 확인

```bash
./scripts/setup-k8s.sh check
```

이 명령어는 현재 Kubernetes 연결 상태를 확인합니다.

---

## 📋 클러스터 연결 방법

### 옵션 1: Azure AKS (Azure Kubernetes Service)

```bash
# 1. Azure 로그인
az login

# 2. 클러스터 연결 (스크립트 사용)
./scripts/setup-k8s.sh azure <resource-group> <cluster-name>

# 또는 수동으로
az aks get-credentials --resource-group <resource-group> --name <cluster-name>
```

**예시**:
```bash
./scripts/setup-k8s.sh azure my-resource-group my-aks-cluster
```

---

### 옵션 2: AWS EKS (Elastic Kubernetes Service)

```bash
# 1. AWS 자격 증명 설정 (처음 한 번만)
aws configure

# 2. 클러스터 연결 (스크립트 사용)
./scripts/setup-k8s.sh aws <region> <cluster-name>

# 또는 수동으로
aws eks update-kubeconfig --region <region> --name <cluster-name>
```

**예시**:
```bash
./scripts/setup-k8s.sh aws us-east-1 my-eks-cluster
```

---

### 옵션 3: GCP GKE (Google Kubernetes Engine)

```bash
# 1. GCP 로그인
gcloud auth login

# 2. 클러스터 연결 (스크립트 사용)
./scripts/setup-k8s.sh gcp <cluster-name> <zone> <project-id>

# 또는 수동으로
gcloud container clusters get-credentials <cluster-name> --zone <zone> --project <project-id>
```

**예시**:
```bash
./scripts/setup-k8s.sh gcp my-gke-cluster us-central1-a my-project-id
```

---

### 옵션 4: 로컬 개발 (Minikube)

```bash
# Minikube 설치 (macOS)
brew install minikube

# 클러스터 시작 및 연결
./scripts/setup-k8s.sh local
```

---

### 옵션 5: Docker Desktop Kubernetes

```bash
# Docker Desktop에서 Kubernetes 활성화
# Settings → Kubernetes → Enable Kubernetes

# 연결
./scripts/setup-k8s.sh docker
```

---

### 옵션 6: Kubeconfig 파일 사용

기존 kubeconfig 파일이 있는 경우:

```bash
./scripts/setup-k8s.sh kubeconfig ~/.kube/config
```

또는 환경 변수로:

```bash
export KUBECONFIG=/path/to/kubeconfig
kubectl config current-context
```

---

## ✅ 연결 확인

연결 후 다음 명령어로 확인:

```bash
# 현재 컨텍스트 확인
kubectl config current-context

# 클러스터 정보 확인
kubectl cluster-info

# Namespace 목록 확인
kubectl get namespaces
```

**예상 결과**:
- 컨텍스트 이름이 표시됨 (예: `my-aks-cluster-admin`)
- 클러스터 URL이 표시됨 (예: `https://my-cluster.region.cloudprovider.com`)
- Namespace 목록이 표시됨

---

## 🔧 문제 해결

### 문제: "connection refused" 또는 "localhost:8080"

**원인**: kubectl이 로컬 클러스터에 연결하려고 시도

**해결**:
1. 클러스터 연결 스크립트 실행
2. 올바른 컨텍스트로 전환 확인

```bash
./scripts/setup-k8s.sh check
```

---

### 문제: "current-context is not set"

**원인**: kubectl 컨텍스트가 설정되지 않음

**해결**:
1. 클러스터 연결 스크립트 실행
2. 컨텍스트 목록 확인 후 전환

```bash
kubectl config get-contexts
kubectl config use-context <context-name>
```

---

### 문제: "az: command not found"

**원인**: Azure CLI가 설치되지 않음

**해결**:
```bash
# macOS
brew install azure-cli

# 또는
curl -sL https://aka.ms/InstallAzureCLIDeb | sudo bash
```

---

### 문제: "aws: command not found"

**원인**: AWS CLI가 설치되지 않음

**해결**:
```bash
# macOS
brew install awscli

# 또는
curl "https://awscli.amazonaws.com/awscli-exe-linux-x86_64.zip" -o "awscliv2.zip"
unzip awscliv2.zip
sudo ./aws/install
```

---

### 문제: "gcloud: command not found"

**원인**: Google Cloud SDK가 설치되지 않음

**해결**:
```bash
# macOS
brew install google-cloud-sdk

# 또는
curl https://sdk.cloud.google.com | bash
exec -l $SHELL
```

---

## 📝 다음 단계

클러스터 연결 후:

1. **Namespace 생성**:
   ```bash
   kubectl create namespace production
   ```

2. **Secret 생성**:
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

3. **배포 진행**: `docs/GO_LIVE_EXECUTION_PLAN.md` 참고

---

## 🎯 GitHub Actions를 통한 배포 (대안)

로컬에서 Kubernetes 클러스터에 연결할 수 없는 경우, GitHub Actions를 통해 배포할 수 있습니다:

1. GitHub 저장소 → Settings → Secrets and variables → Actions
2. 필요한 시크릿 추가 (DB_HOST, DB_PASSWORD, API_KEYS 등)
3. Actions 탭 → Deploy 워크플로우 → Run workflow
4. Environment: `production` 선택
5. 2인 승인 완료

자세한 내용은 `.github/workflows/deploy.yml` 참고

---

## 📚 참고 문서

- `docs/KUBERNETES_SETUP.md` - 상세 Kubernetes 설정 가이드
- `docs/GO_LIVE_EXECUTION_PLAN.md` - Go-Live 실행 계획
- `config/collector.env.sample` - 환경 변수 샘플


