#!/usr/bin/env bash

set -euo pipefail

# 프로젝트 루트로 이동
ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

cd "$ROOT_DIR"

echo "=== [ops_local_up] 로컬 DB + BFF 기동 ==="

echo

echo "1) Docker 컨테이너(db, bff) 기동 중..."

docker compose up -d db bff

echo

echo "2) BFF health / ready 확인"

echo "- GET http://localhost:8081/health"

curl -sS -H "X-Tenant: default" -H "X-User-Role: operator" -H "X-User-Id: ops-script" \
  http://localhost:8081/health || echo "[경고] /health 호출 실패"

echo

echo "- GET http://localhost:8081/ready"

curl -sS -H "X-Tenant: default" -H "X-User-Role: operator" -H "X-User-Id: ops-script" \
  http://localhost:8081/ready || echo "[경고] /ready 호출 실패"

echo

echo "3) (선택) 리포트 실행"

export DATABASE_URL="${DATABASE_URL:-postgres://app:app@localhost:5432/app}"

echo "- 파일럿 지표 리포트 (report:pilot)"

npm run report:pilot || echo "[info] report:pilot 실행 실패 (초기 상태이거나 데이터가 없을 수 있습니다)"

echo

echo "- 어댑터 SLO 리포트 (report:adapter-slo)"

npm run report:adapter-slo || echo "[info] report:adapter-slo 실행 실패 (external_ledger_offset 비어 있을 수 있습니다)"

echo

echo "=== 완료 ==="

echo "운영팀은 아래 주소로 접속해서 상태를 확인하실 수 있습니다:"

echo "- API 헬스체크 : http://localhost:8081/health"

echo "- Ready 체크  : http://localhost:8081/ready"

echo

echo "백오피스 화면을 보시려면 (별도 터미널에서):"

echo "  npm run dev --workspace=@appcore/ops-console"

echo "  → 브라우저에서 dev 서버가 출력하는 http://localhost:xxxx 로 접속"

