# 롤백 가이드

## 개요

BFF Accounting 서비스를 이전 버전으로 롤백하는 방법을 안내합니다.

## 사전 요구사항

### 1. Kubernetes 클러스터 접근
- 운영 환경의 Kubernetes 클러스터에 접근 가능해야 합니다
- `kubectl` 또는 `helm` 명령어로 클러스터에 연결할 수 있어야 합니다

### 2. 필요한 도구
- **Helm** (권장): `brew install helm`
- 또는 **kubectl**: `brew install kubectl`

### 3. 클러스터 연결 확인
```bash
# 클러스터 연결 확인
kubectl cluster-info

# 현재 컨텍스트 확인
kubectl config current-context

# 사용 가능한 컨텍스트 목록
kubectl config get-contexts
```

## 롤백 방법

### 방법 1: Helm 스크립트 사용 (권장)

```bash
# 사용 가능한 태그 확인
git tag | grep -E "r[67]-" | sort -V

# 롤백 실행
./scripts/rollback.sh <tag-name>

# 예시
./scripts/rollback.sh r6-s5-20251202
```

### 방법 2: kubectl 스크립트 사용

```bash
# 롤백 실행
./scripts/rollback-kubectl.sh <tag-name>

# 예시
./scripts/rollback-kubectl.sh r6-s5-20251202
```

### 방법 3: 직접 Helm 명령어

```bash
helm upgrade --install bff charts/bff-accounting \
  --set image.tag=<tag-name> \
  --namespace accounting \
  --wait --timeout 5m
```

### 방법 4: 직접 kubectl 명령어

```bash
kubectl set image deployment/bff-accounting \
  bff-accounting=ghcr.io/tristan00037-tristan050/tristan050-ai_ondevice_APP/bff-accounting:<tag-name> \
  -n accounting
```

## 사용 가능한 태그

```bash
# 태그 목록 확인
git tag | grep -E "r[67]-" | sort -V
```

현재 사용 가능한 태그:
- `r6-s4-20251202`
- `r6-s5-20251202`
- `r7-final-20251203` (현재)

## 롤백 후 확인

### 1. Pod 상태 확인
```bash
kubectl get pods -n accounting
```

### 2. 배포된 이미지 태그 확인
```bash
# Helm 사용 시
helm get values bff -n accounting | grep image.tag

# kubectl 사용 시
kubectl get deployment bff-accounting -n accounting \
  -o jsonpath='{.spec.template.spec.containers[0].image}'
```

### 3. 헬스 체크
```bash
# 서비스 URL이 있다면
curl -s https://<domain>/health
curl -s https://<domain>/ready
```

## 문제 해결

### 오류: "kubernetes cluster unreachable"

**원인**: Kubernetes 클러스터에 연결할 수 없음

**해결 방법**:
1. 로컬 클러스터 시작:
   ```bash
   minikube start
   # 또는 Docker Desktop에서 Kubernetes 활성화
   ```

2. kubeconfig 확인:
   ```bash
   kubectl config get-contexts
   kubectl config use-context <context-name>
   ```

3. 원격 클러스터인 경우 kubeconfig 파일 확인:
   ```bash
   echo $KUBECONFIG
   ls -la ~/.kube/config
   ```

### 오류: "Deployment를 찾을 수 없습니다"

**원인**: 지정한 namespace에 Deployment가 없음

**해결 방법**:
1. Deployment 이름 확인:
   ```bash
   kubectl get deployments -n accounting
   ```

2. 올바른 namespace 사용:
   ```bash
   ./scripts/rollback-kubectl.sh r6-s5-20251202 <correct-namespace>
   ```

3. Deployment 이름이 다른 경우 스크립트 수정 필요

### 오류: "Helm이 설치되어 있지 않습니다"

**해결 방법**:
```bash
# macOS
brew install helm

# Linux
curl https://raw.githubusercontent.com/helm/helm/main/scripts/get-helm-3 | bash
```

### 오류: "kubectl이 설치되어 있지 않습니다"

**해결 방법**:
```bash
# macOS
brew install kubectl

# 또는 공식 문서 참조
# https://kubernetes.io/docs/tasks/tools/
```

## 로컬 개발 환경

로컬 개발 환경에서는 Kubernetes 클러스터가 없을 수 있습니다. 이는 정상입니다.

롤백 스크립트는 **운영 환경(Kubernetes 클러스터)**에서 실행해야 합니다.

로컬에서 테스트하려면:
1. minikube 시작: `minikube start`
2. 또는 Docker Desktop에서 Kubernetes 활성화
3. 또는 원격 클러스터의 kubeconfig 설정

## 주의사항

1. **롤백 전 백업**: 롤백 전에 현재 상태를 확인하고 필요시 백업하세요
2. **데이터 호환성**: 이전 버전으로 롤백 시 데이터베이스 스키마 호환성을 확인하세요
3. **서비스 중단**: 롤백 중 일시적인 서비스 중단이 발생할 수 있습니다
4. **롤아웃 시간**: 롤백이 완료될 때까지 기다리세요 (기본 5분 타임아웃)

## 추가 리소스

- [Helm 공식 문서](https://helm.sh/docs/)
- [kubectl 공식 문서](https://kubernetes.io/docs/reference/kubectl/)
- [Kubernetes 롤백 가이드](https://kubernetes.io/docs/concepts/workloads/controllers/deployment/#rolling-back-a-deployment)

