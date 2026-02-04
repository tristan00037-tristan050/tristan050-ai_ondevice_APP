#!/bin/bash
# BFF 롤백 스크립트
# 사용법: ./scripts/rollback.sh <tag-name>

set -e

TAG=${1:-""}
NAMESPACE=${2:-"accounting"}

# Helm 설치 확인
if ! command -v helm &> /dev/null; then
  echo "❌ 오류: Helm이 설치되어 있지 않습니다."
  echo ""
  echo "Helm 설치 방법:"
  echo "  macOS:"
  echo "    brew install helm"
  echo ""
  echo "  Linux:"
  echo "    curl https://raw.githubusercontent.com/helm/helm/main/scripts/get-helm-3 | bash"
  echo ""
  echo "  또는 수동 설치:"
  echo "    https://helm.sh/docs/intro/install/"
  echo ""
  echo "⚠️  Helm 없이도 kubectl로 직접 롤백할 수 있습니다:"
  echo "  ./scripts/rollback-kubectl.sh $TAG"
  exit 1
fi

# Kubernetes 클러스터 연결 확인
if ! kubectl cluster-info &> /dev/null; then
  echo "❌ 오류: Kubernetes 클러스터에 연결할 수 없습니다."
  echo ""
  echo "가능한 원인:"
  echo "  1. 로컬 클러스터가 실행되지 않음 (minikube, kind, Docker Desktop 등)"
  echo "  2. kubeconfig가 설정되지 않음"
  echo "  3. 원격 클러스터에 접근할 수 없음"
  echo ""
  echo "해결 방법:"
  echo "  1. 로컬 클러스터 시작:"
  echo "     minikube start"
  echo "     # 또는 Docker Desktop에서 Kubernetes 활성화"
  echo ""
  echo "  2. kubeconfig 확인:"
  echo "     kubectl config get-contexts"
  echo "     kubectl config use-context <context-name>"
  echo ""
  echo "  3. 원격 클러스터인 경우 kubeconfig 파일 확인:"
  echo "     echo \$KUBECONFIG"
  echo "     ls -la ~/.kube/config"
  echo ""
  echo "⚠️  로컬 개발 환경에서는 실제 클러스터가 필요하지 않을 수 있습니다."
  echo "    이 스크립트는 운영 환경에서 사용하도록 설계되었습니다."
  exit 1
fi

if [ -z "$TAG" ]; then
  echo "❌ 오류: 태그 이름이 필요합니다."
  echo ""
  echo "사용법:"
  echo "  ./scripts/rollback.sh <tag-name> [namespace]"
  echo ""
  echo "사용 가능한 태그:"
  git tag | grep -E "r[67]-" | sort -V | sed 's/^/  - /'
  echo ""
  echo "예시:"
  echo "  ./scripts/rollback.sh r6-s5-20251202"
  echo "  ./scripts/rollback.sh r7-final-20251203 accounting"
  exit 1
fi

# 태그 존재 확인
if ! git tag | grep -q "^${TAG}$"; then
  echo "❌ 오류: 태그 '$TAG'가 존재하지 않습니다."
  echo ""
  echo "사용 가능한 태그:"
  git tag | grep -E "r[67]-" | sort -V | sed 's/^/  - /'
  exit 1
fi

echo "🔄 롤백 시작: $TAG"
echo "   Namespace: $NAMESPACE"
echo ""

helm upgrade --install bff charts/bff-accounting \
  --set image.tag="$TAG" \
  --namespace "$NAMESPACE" \
  --wait --timeout 5m

echo ""
echo "✅ 롤백 완료: $TAG"
echo ""
echo "배포 상태 확인:"
echo "  kubectl get pods -n $NAMESPACE"
echo "  helm get values bff -n $NAMESPACE | grep image.tag"

