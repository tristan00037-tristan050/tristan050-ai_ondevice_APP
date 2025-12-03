# Kubernetes 설정 가이드

프로덕션 배포 전 Kubernetes 클러스터 연결 및 설정 가이드입니다.

## 🔍 문제 진단

### 에러 메시지
```
error: failed to create secret Post "http://localhost:8080/api/v1/namespaces/production/secrets...": 
dial tcp [::1]:8080: connect: connection refused
```

**원인**: kubectl이 로컬 Kubernetes 클러스터(`localhost:8080`)에 연결하려고 시도했지만, 실제 프로덕션 클러스터에 연결되지 않았습니다.

---

## ✅ 해결 방법

### 1. Kubernetes 클러스터 연결 확인

```bash
# 현재 컨텍스트 확인
kubectl config current-context

# 사용 가능한 컨텍스트 목록
kubectl config get-contexts

# 클러스터 정보 확인
kubectl cluster-info
```

**예상 결과**:
- 프로덕션 클러스터 URL이 표시되어야 함 (예: `https://production-k8s.example.com`)
- `localhost:8080`이 아닌 실제 클러스터 엔드포인트

---

### 2. 프로덕션 클러스터 컨텍스트 설정

#### 옵션 A: 기존 컨텍스트 사용

```bash
# 프로덕션 컨텍스트로 전환
kubectl config use-context production

# 확인
kubectl config current-context
```

#### 옵션 B: 새 클러스터 연결 (Azure AKS 예시)

```bash
# Azure AKS 연결
az aks get-credentials --resource-group <resource-group> --name <cluster-name>

# 확인
kubectl config current-context
```

#### 옵션 C: 새 클러스터 연결 (AWS EKS 예시)

```bash
# AWS EKS 연결
aws eks update-kubeconfig --region <region> --name <cluster-name>

# 확인
kubectl config current-context
```

#### 옵션 D: 새 클러스터 연결 (GCP GKE 예시)

```bash
# GCP GKE 연결
gcloud container clusters get-credentials <cluster-name> --zone <zone> --project <project-id>

# 확인
kubectl config current-context
```

---

### 3. Namespace 확인 및 생성

```bash
# Namespace 목록 확인
kubectl get namespaces

# production namespace가 없으면 생성
kubectl create namespace production

# 확인
kubectl get namespaces | grep production
```

---

### 4. Secret 생성 (재시도)

프로덕션 클러스터에 연결된 후:

```bash
# 환경 변수 설정 (실제 값으로 교체)
export DB_HOST=postgres-service
export DB_PORT=5432
export DB_NAME=collector
export DB_USER=postgres
export DB_PASSWORD=your-secure-password
export API_KEYS="default:collector-key:admin,teamA:teamA-key:operator"
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

# 확인
kubectl get secrets -n production | grep collector-secrets
```

---

### 5. ConfigMap 생성 (Ops Console)

```bash
# 환경 변수 설정
export VITE_COLLECTOR_URL=https://collector.production.com
export VITE_API_KEY=collector-key
export VITE_TENANT=default
export VITE_PERMISSION=download

# ConfigMap 생성
kubectl create configmap ops-console-config \
  --from-literal=VITE_COLLECTOR_URL=$VITE_COLLECTOR_URL \
  --from-literal=VITE_API_KEY=$VITE_API_KEY \
  --from-literal=VITE_TENANT=$VITE_TENANT \
  --from-literal=VITE_PERMISSION=$VITE_PERMISSION \
  -n production

# 확인
kubectl get configmaps -n production | grep ops-console-config
```

---

## 🔧 로컬 개발 환경 (선택사항)

로컬에서 테스트하려면:

### Minikube 사용

```bash
# Minikube 시작
minikube start

# 컨텍스트 확인
kubectl config use-context minikube

# Namespace 생성
kubectl create namespace production
```

### Docker Desktop Kubernetes 사용

```bash
# Docker Desktop에서 Kubernetes 활성화
# Settings → Kubernetes → Enable Kubernetes

# 컨텍스트 확인
kubectl config use-context docker-desktop

# Namespace 생성
kubectl create namespace production
```

---

## 📋 체크리스트

배포 전 확인:

- [ ] `kubectl config current-context`가 프로덕션 클러스터를 가리킴
- [ ] `kubectl cluster-info`가 실제 클러스터 URL을 표시
- [ ] `kubectl get namespaces`에 `production` namespace 존재
- [ ] `kubectl get secrets -n production`에 `collector-secrets` 존재
- [ ] `kubectl get configmaps -n production`에 `ops-console-config` 존재 (Ops Console 사용 시)

---

## 🚨 문제 해결

### 문제: "connection refused"

**해결**:
1. 클러스터가 실행 중인지 확인
2. 올바른 컨텍스트로 전환
3. 네트워크 연결 확인
4. 클러스터 인증 정보 확인

### 문제: "namespace not found"

**해결**:
```bash
kubectl create namespace production
```

### 문제: "secret already exists"

**해결**:
```bash
# 기존 Secret 삭제 후 재생성
kubectl delete secret collector-secrets -n production
kubectl create secret generic collector-secrets ...
```

---

## 📚 참고 문서

- `docs/GO_LIVE_EXECUTION_PLAN.md` - Go-Live 실행 계획
- `config/collector.env.sample` - Collector 환경 변수 샘플
- `config/ops-console.env.sample` - Ops Console 환경 변수 샘플

---

**다음 단계**: Kubernetes 클러스터 연결 후 `docs/GO_LIVE_EXECUTION_PLAN.md`의 배포 절차를 진행하세요.


