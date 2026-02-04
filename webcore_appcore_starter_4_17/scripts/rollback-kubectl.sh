#!/bin/bash
# BFF 롤백 스크립트 (kubectl 버전 - Helm 없이 사용 가능)
# 사용법: ./scripts/rollback-kubectl.sh <tag-name> [namespace] [image-repo]

set -e

TAG=${1:-""}
NAMESPACE=${2:-"accounting"}
IMAGE_REPO=${3:-"ghcr.io/tristan00037-tristan050/tristan050-ai_ondevice_APP/bff-accounting"}

# kubectl 설치 확인
if ! command -v kubectl &> /dev/null; then
  echo "❌ 오류: kubectl이 설치되어 있지 않습니다."
  echo ""
  echo "kubectl 설치 방법:"
  echo "  macOS:"
  echo "    brew install kubectl"
  echo ""
  echo "  또는:"
  echo "    https://kubernetes.io/docs/tasks/tools/"
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
  echo "  ./scripts/rollback-kubectl.sh <tag-name> [namespace] [image-repo]"
  echo ""
  echo "사용 가능한 태그:"
  git tag | grep -E "r[67]-" | sort -V | sed 's/^/  - /'
  echo ""
  echo "예시:"
  echo "  ./scripts/rollback-kubectl.sh r6-s5-20251202"
  echo "  ./scripts/rollback-kubectl.sh r7-final-20251203 accounting"
  echo "  ./scripts/rollback-kubectl.sh r6-s5-20251202 accounting ghcr.io/OWNER/REPO/bff-accounting"
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

FULL_IMAGE="${IMAGE_REPO}:${TAG}"

echo "🔄 롤백 시작: $TAG"
echo "   Namespace: $NAMESPACE"
echo "   Image: $FULL_IMAGE"
echo ""

# Deployment 이름 확인 (일반적으로 bff-accounting 또는 bff)
DEPLOYMENT_NAME="bff-accounting"
if ! kubectl get deployment "$DEPLOYMENT_NAME" -n "$NAMESPACE" &> /dev/null; then
  # bff-accounting이 없으면 bff 시도
  DEPLOYMENT_NAME="bff"
  if ! kubectl get deployment "$DEPLOYMENT_NAME" -n "$NAMESPACE" &> /dev/null; then
    echo "❌ 오류: Deployment를 찾을 수 없습니다."
    echo ""
    echo "사용 가능한 Deployment:"
    kubectl get deployments -n "$NAMESPACE" 2>/dev/null || echo "  (namespace '$NAMESPACE'에 접근할 수 없습니다)"
    exit 1
  fi
fi

echo "📦 Deployment: $DEPLOYMENT_NAME"
echo ""

# 이미지 업데이트
kubectl set image "deployment/$DEPLOYMENT_NAME" \
  "$DEPLOYMENT_NAME=$FULL_IMAGE" \
  -n "$NAMESPACE"

echo ""
echo "⏳ 롤아웃 상태 확인 중..."
kubectl rollout status "deployment/$DEPLOYMENT_NAME" -n "$NAMESPACE" --timeout=5m

echo ""
echo "✅ 롤백 완료: $TAG"
echo ""
echo "배포 상태 확인:"
echo "  kubectl get pods -n $NAMESPACE"
echo "  kubectl get deployment $DEPLOYMENT_NAME -n $NAMESPACE -o jsonpath='{.spec.template.spec.containers[0].image}'"
echo ""

