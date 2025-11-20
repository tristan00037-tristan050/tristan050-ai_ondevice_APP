#!/bin/bash
# OpenAPI 타입 자동 재생성 스크립트
# BFF/Collector → App 타입 생성
# Usage: ./generate-types.sh [--check-only]

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
CHECK_ONLY="${1:-}"

# OpenAPI 스펙 경로 (예시 - 실제 경로에 맞게 수정 필요)
BFF_OPENAPI="${BFF_OPENAPI:-$ROOT_DIR/../packages/bff-node-ts/docs/openapi.yaml}"
COLLECTOR_OPENAPI="${COLLECTOR_OPENAPI:-$ROOT_DIR/../packages/collector-node-ts/docs/openapi.yaml}"

# 타입 출력 디렉토리
TYPES_DIR="${TYPES_DIR:-$ROOT_DIR/../packages/app-expo/src/types/generated}"

# 타입 생성 도구 (openapi-typescript 사용 예시)
if ! command -v openapi-typescript &> /dev/null; then
  echo "❌ openapi-typescript가 설치되지 않았습니다."
  echo "   npm install -g openapi-typescript 또는 npm install -D openapi-typescript"
  exit 1
fi

echo "🔧 OpenAPI 타입 생성 중..."

mkdir -p "$TYPES_DIR"

# BFF 타입 생성
if [ -f "$BFF_OPENAPI" ]; then
  echo "  📝 BFF 타입 생성: $BFF_OPENAPI"
  openapi-typescript "$BFF_OPENAPI" -o "$TYPES_DIR/bff-types.ts" || {
    echo "❌ BFF 타입 생성 실패"
    exit 1
  }
else
  echo "⚠️  BFF OpenAPI 스펙을 찾을 수 없습니다: $BFF_OPENAPI"
fi

# Collector 타입 생성
if [ -f "$COLLECTOR_OPENAPI" ]; then
  echo "  📝 Collector 타입 생성: $COLLECTOR_OPENAPI"
  openapi-typescript "$COLLECTOR_OPENAPI" -o "$TYPES_DIR/collector-types.ts" || {
    echo "❌ Collector 타입 생성 실패"
    exit 1
  }
else
  echo "⚠️  Collector OpenAPI 스펙을 찾을 수 없습니다: $COLLECTOR_OPENAPI"
fi

echo "✅ 타입 생성 완료"

# --check-only 모드: git diff로 변경사항 확인
if [ "$CHECK_ONLY" = "--check-only" ]; then
  echo "🔍 타입 변경사항 확인 중..."
  
  if ! git diff --exit-code "$TYPES_DIR"/*.ts 2>/dev/null; then
    echo "❌ 타입 파일에 변경사항이 있습니다."
    echo "   다음 명령으로 타입을 재생성하세요:"
    echo "   ./scripts/generate-types.sh"
    exit 1
  fi
  
  echo "✅ 타입 파일이 최신 상태입니다."
fi

