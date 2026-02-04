#!/bin/bash
# 회계 OpenAPI 타입 생성 스크립트
# accounting.openapi.yaml → TypeScript 타입 생성

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
OPENAPI_FILE="$ROOT_DIR/contracts/accounting.openapi.yaml"
OUTPUT_DIR="$ROOT_DIR/packages/bff-accounting/src/types"

echo "📝 회계 OpenAPI 타입 생성 중..."

# openapi-typescript 설치 확인
if ! command -v openapi-typescript &> /dev/null; then
  echo "⚠️  openapi-typescript가 설치되지 않았습니다."
  echo "   npm install -g openapi-typescript 또는 npm install --save-dev openapi-typescript"
  exit 1
fi

# 출력 디렉토리 생성
mkdir -p "$OUTPUT_DIR"

# 타입 생성
openapi-typescript "$OPENAPI_FILE" -o "$OUTPUT_DIR/accounting.ts"

echo "✅ 타입 생성 완료: $OUTPUT_DIR/accounting.ts"


