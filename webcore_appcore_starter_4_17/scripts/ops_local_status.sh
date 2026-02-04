#!/usr/bin/env bash

set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

cd "$ROOT_DIR"

echo "=== [ops_local_status] 로컬 상태 점검 ==="

echo

echo "[1] BFF health / ready"

echo "- /health"

curl -sS -H "X-Tenant: default" -H "X-User-Role: operator" -H "X-User-Id: ops-script" \
  http://localhost:8081/health || echo "[경고] /health 호출 실패"

echo

echo "- /ready"

curl -sS -H "X-Tenant: default" -H "X-User-Role: operator" -H "X-User-Id: ops-script" \
  http://localhost:8081/ready || echo "[경고] /ready 호출 실패"

echo

echo "[2] 파일럿 지표 리포트 (요약)"

export DATABASE_URL="${DATABASE_URL:-postgres://app:app@localhost:5432/app}"

npm run report:pilot || echo "[info] report:pilot 실행 실패 (데이터가 없을 수 있습니다)"

echo

echo "[3] 어댑터 SLO 리포트 (요약)"

npm run report:adapter-slo || echo "[info] report:adapter-slo 실행 실패 (external_ledger_offset 비어 있을 수 있습니다)"

echo

echo "=== 상태 점검 완료 ==="

