#!/usr/bin/env bash
set -euo pipefail

PATH_SCOPE_ENFORCED_V2_OK=0
trap 'echo "PATH_SCOPE_ENFORCED_V2_OK=${PATH_SCOPE_ENFORCED_V2_OK}"' EXIT

SSOT_PATH="docs/ops/contracts/PATH_SCOPE_SSOT_V1.json"
test -f "$SSOT_PATH" || { echo "BLOCK: missing PATH_SCOPE SSOT ($SSOT_PATH)"; exit 1; }

# path-scope 전용 verify만 검사 (현재 레포 정책)
scanners=()
while IFS= read -r f; do
  [[ -n "$f" ]] && scanners+=("$f")
done < <(find scripts/verify -maxdepth 1 -type f -name 'verify_*' 2>/dev/null \
  | grep -E 'path_scope|path-scope' || true)

# 검사할 대상이 없으면 fail-closed (의미 없는 가드 방지)
if [[ "${#scanners[@]}" -eq 0 ]]; then
  echo "BLOCK: no path-scope verify scripts found to enforce"
  exit 1
fi

# "토큰 존재"가 아니라 "실제 SSOT 사용"을 강제:
# (A) 비주석 라인에서 SSOT 전체 경로가 등장해야 함
# (B) 비주석 라인에서 SSOT를 읽는 패턴이 있어야 함 (cat/jq/node/python 중 하나)
#
# 허용 read 패턴(예):
# - cat "$SSOT_PATH"
# - jq ... "$SSOT_PATH"
# - node ... "$SSOT_PATH"   또는 node -e '...' "$SSOT_PATH"
# - python ... "$SSOT_PATH"
#
# 주석 우회 차단: 라인 시작이 # 인 줄은 무시
require_ref_re="docs/ops/contracts/PATH_SCOPE_SSOT_V1\\.json"
require_read_re="(cat|jq|node|python).*PATH_SCOPE_SSOT_V1\\.json|PATH_SCOPE_SSOT_V1\\.json.*(cat|jq|node|python)"

for f in "${scanners[@]}"; do
  [[ "$f" == "scripts/verify/verify_path_scope_enforced_v2.sh" ]] && continue
  # P17-P0-09: read-required v1 uses PATH_SCOPE_SSOT_V1.txt; enforced v2 checks .json consumers only
  [[ "$f" == "scripts/verify/verify_path_scope_read_required_v1.sh" ]] && continue

  # (A) 실제 경로 참조(비주석)
  if ! grep -v '^[[:space:]]*#' "$f" | grep -qE "$require_ref_re"; then
    echo "BLOCK: path-scope verify does not reference SSOT path in code (non-comment): $f"
    exit 1
  fi

  # (B) 실제로 읽는(read) 패턴(비주석)
  # - 단순 문자열만 넣고 안 읽는 우회 차단
  if ! grep -v '^[[:space:]]*#' "$f" | grep -qE "$require_read_re"; then
    echo "BLOCK: path-scope verify does not read SSOT (cat/jq/node/python) in code (non-comment): $f"
    exit 1
  fi
done

PATH_SCOPE_ENFORCED_V2_OK=1
exit 0
