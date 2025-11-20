#!/bin/bash
# Kubernetes 클러스터 연결 스크립트
# 사용법: ./scripts/setup-k8s.sh <provider> [options]

set -e

PROVIDER="${1:-help}"

case "$PROVIDER" in
  azure|aks)
    echo "Azure AKS 연결 중..."
    if [ -z "$2" ] || [ -z "$3" ]; then
      echo "사용법: ./scripts/setup-k8s.sh azure <resource-group> <cluster-name>"
      exit 1
    fi
    RESOURCE_GROUP="$2"
    CLUSTER_NAME="$3"
    
    echo "Azure에 로그인 중..."
    az login
    
    echo "AKS 클러스터 자격 증명 가져오는 중..."
    az aks get-credentials --resource-group "$RESOURCE_GROUP" --name "$CLUSTER_NAME"
    
    echo "연결 확인 중..."
    kubectl config current-context
    kubectl cluster-info
    ;;
    
  aws|eks)
    echo "AWS EKS 연결 중..."
    if [ -z "$2" ] || [ -z "$3" ]; then
      echo "사용법: ./scripts/setup-k8s.sh aws <region> <cluster-name>"
      exit 1
    fi
    REGION="$2"
    CLUSTER_NAME="$3"
    
    echo "AWS 자격 증명 확인 중..."
    aws sts get-caller-identity || {
      echo "AWS 자격 증명이 설정되지 않았습니다. 'aws configure'를 실행하세요."
      exit 1
    }
    
    echo "EKS 클러스터 자격 증명 가져오는 중..."
    aws eks update-kubeconfig --region "$REGION" --name "$CLUSTER_NAME"
    
    echo "연결 확인 중..."
    kubectl config current-context
    kubectl cluster-info
    ;;
    
  gcp|gke)
    echo "GCP GKE 연결 중..."
    if [ -z "$2" ] || [ -z "$3" ] || [ -z "$4" ]; then
      echo "사용법: ./scripts/setup-k8s.sh gcp <cluster-name> <zone> <project-id>"
      exit 1
    fi
    CLUSTER_NAME="$2"
    ZONE="$3"
    PROJECT_ID="$4"
    
    echo "GCP에 로그인 중..."
    gcloud auth login
    
    echo "GKE 클러스터 자격 증명 가져오는 중..."
    gcloud container clusters get-credentials "$CLUSTER_NAME" --zone "$ZONE" --project "$PROJECT_ID"
    
    echo "연결 확인 중..."
    kubectl config current-context
    kubectl cluster-info
    ;;
    
  local|minikube)
    echo "로컬 Minikube 설정 중..."
    if ! command -v minikube &> /dev/null; then
      echo "Minikube가 설치되지 않았습니다."
      echo "설치: brew install minikube (macOS)"
      exit 1
    fi
    
    echo "Minikube 시작 중..."
    minikube start
    
    echo "컨텍스트 전환 중..."
    kubectl config use-context minikube
    
    echo "연결 확인 중..."
    kubectl config current-context
    kubectl cluster-info
    ;;
    
  docker)
    echo "Docker Desktop Kubernetes 설정 중..."
    if ! docker info &> /dev/null; then
      echo "Docker Desktop이 실행되지 않았습니다."
      exit 1
    fi
    
    echo "컨텍스트 전환 중..."
    kubectl config use-context docker-desktop
    
    echo "연결 확인 중..."
    kubectl config current-context
    kubectl cluster-info || {
      echo "Docker Desktop에서 Kubernetes가 활성화되지 않았습니다."
      echo "Settings → Kubernetes → Enable Kubernetes"
      exit 1
    }
    ;;
    
  kubeconfig)
    if [ -z "$2" ]; then
      echo "사용법: ./scripts/setup-k8s.sh kubeconfig <path-to-kubeconfig>"
      exit 1
    fi
    KUBECONFIG_PATH="$2"
    
    if [ ! -f "$KUBECONFIG_PATH" ]; then
      echo "Kubeconfig 파일을 찾을 수 없습니다: $KUBECONFIG_PATH"
      exit 1
    fi
    
    echo "Kubeconfig 파일 사용 중..."
    export KUBECONFIG="$KUBECONFIG_PATH"
    
    echo "연결 확인 중..."
    kubectl config current-context
    kubectl cluster-info
    ;;
    
  check)
    echo "현재 Kubernetes 연결 상태 확인 중..."
    echo ""
    echo "=== 현재 컨텍스트 ==="
    kubectl config current-context || echo "컨텍스트가 설정되지 않았습니다."
    echo ""
    echo "=== 사용 가능한 컨텍스트 ==="
    kubectl config get-contexts
    echo ""
    echo "=== 클러스터 정보 ==="
    kubectl cluster-info 2>&1 || echo "클러스터에 연결할 수 없습니다."
    echo ""
    echo "=== Namespace 목록 ==="
    kubectl get namespaces 2>&1 || echo "클러스터에 연결할 수 없습니다."
    ;;
    
  help|*)
    echo "Kubernetes 클러스터 연결 스크립트"
    echo ""
    echo "사용법:"
    echo "  ./scripts/setup-k8s.sh <provider> [options]"
    echo ""
    echo "프로바이더:"
    echo "  azure <resource-group> <cluster-name>  - Azure AKS 연결"
    echo "  aws <region> <cluster-name>             - AWS EKS 연결"
    echo "  gcp <cluster-name> <zone> <project-id> - GCP GKE 연결"
    echo "  local                                   - Minikube 로컬 클러스터"
    echo "  docker                                  - Docker Desktop Kubernetes"
    echo "  kubeconfig <path>                      - Kubeconfig 파일 사용"
    echo "  check                                   - 현재 연결 상태 확인"
    echo ""
    echo "예시:"
    echo "  ./scripts/setup-k8s.sh azure my-rg my-cluster"
    echo "  ./scripts/setup-k8s.sh aws us-east-1 my-eks-cluster"
    echo "  ./scripts/setup-k8s.sh gcp my-gke-cluster us-central1-a my-project"
    echo "  ./scripts/setup-k8s.sh local"
    echo "  ./scripts/setup-k8s.sh docker"
    echo "  ./scripts/setup-k8s.sh kubeconfig ~/.kube/config"
    echo "  ./scripts/setup-k8s.sh check"
    ;;
esac

