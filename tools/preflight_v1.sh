#!/usr/bin/env bash
set -euo pipefail

# PREFLIGHT_ONE_SHOT_V1
# - 목적: 로컬/CI 동일 실행 경험
# - 주의: 이 스크립트는 "준비" 스크립트입니다. (빌드/부트/스탬프 생성 가능)
# - 금지: DoD 키 출력 금지, 민감정보 출력 금지

repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$repo_root"

# 1) Node 버전(예: 20.x) 확인 (프로젝트 규칙에 맞게 수정)
node_major="$(node -p 'process.versions.node.split(".")[0]')"
if [[ "$node_major" != "20" ]]; then
  echo "BLOCK: node major must be 20 (got $node_major)"
  exit 1
fi

# 2) lock 해시 계산(패키지 매니저에 따라 한 가지를 선택)
lock_hash="missing"
if [[ -f package-lock.json ]]; then
  lock_hash="$(shasum -a 256 package-lock.json | awk '{print $1}')"
elif [[ -f pnpm-lock.yaml ]]; then
  lock_hash="$(shasum -a 256 pnpm-lock.yaml | awk '{print $1}')"
elif [[ -f yarn.lock ]]; then
  lock_hash="$(shasum -a 256 yarn.lock | awk '{print $1}')"
fi

# 3) git head
git_head="$(git rev-parse HEAD)"

# 4) dist 준비(프로젝트에 맞게 커맨드 조정)
# 예시:
# npm ci
# npm run build
# 또는 pnpm i --frozen-lockfile
# pnpm build
#
# 여기서는 "프로젝트 실커맨드가 무엇인지"를 문서에서 확정할 수 없어서 비워둡니다.
# 팀 표준 커맨드로 교체하세요.
echo "INFO: preflight_v1.sh placeholder - fill build commands for your repo" >/dev/null

# 5) stamp 생성(비교 대상 필드 고정)
mkdir -p dist
built_at_utc="$(date -u +"%Y-%m-%dT%H:%M:%SZ")"

cat > dist/.build_stamp.json <<EOF
{
  "git_head": "${git_head}",
  "lock_hash": "${lock_hash}",
  "node_major": ${node_major},
  "workflow_name": "local-preflight",
  "built_at_utc": "${built_at_utc}"
}
EOF

# 끝. (키 출력 없음)
exit 0

