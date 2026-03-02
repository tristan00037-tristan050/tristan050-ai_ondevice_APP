#!/usr/bin/env bash
set -euo pipefail

META_ONLY_OUTPUT_GUARD_V1_OK=0
finish(){ echo "META_ONLY_OUTPUT_GUARD_V1_OK=${META_ONLY_OUTPUT_GUARD_V1_OK}"; }
trap finish EXIT

ROOT="$(git rev-parse --show-toplevel)"
cd "$ROOT"

# PATH_SCOPE SSOT read (P17-P0-09: 경로 드리프트 방지)
PATH_SCOPE_SSOT="docs/ops/contracts/PATH_SCOPE_SSOT_V1.txt"
test -f "$PATH_SCOPE_SSOT" || { echo "ERROR_CODE=PATH_SCOPE_SSOT_MISSING"; exit 1; }
echo "PATH_SCOPE_SSOT_READ_OK=1"

# 스캔 범위(오탐 최소화를 위해 경로를 제한)
SCAN_PATHS=(
  "scripts/verify"
  "scripts/ops"
  "tools/exec_mode"
  "docs/ops"
)

# 최소 금지 패턴(원문/비밀/스택성 텍스트 차단)
DENY_RE='(Traceback|Exception:|stack trace|BEGIN [A-Z ]*PRIVATE KEY|_TOKEN=|_PASSWORD=|DATABASE_URL=)'

# .sh 포함 스캔. docs/ops/contracts 제외. 자기 자신·주석·정의라인 제외 후 금지 패턴만 탐지
scan_grep() {
  local pat="$1"
  local dir="$2"

  find "$dir" -type f \
    ! -path "*/contracts/*" \
    2>/dev/null | while IFS= read -r f; do

    # 1) 자기 자신 및 시크릿 스키마 검증기는 제외(검사용 패턴/정규식 문자열 때문에 오탐 방지)
    case "$f" in
      */scripts/verify/verify_meta_only_output_guard_v1.sh) continue ;;
      scripts/verify/verify_bff_secret_schema_v1.sh) continue ;;
      *verify_bff_secret_schema_v1.sh) continue ;;
    esac

    # 2) 텍스트 파일만(바이너리 스킵)
    # 3) 주석/정의라인/검사용 grep 호출 라인 제외 후 패턴 탐지
    if grep -nE "$pat" "$f" --binary-files=without-match 2>/dev/null \
      | grep -vE '^[0-9]+:[[:space:]]*#' \
      | grep -vE '^[0-9]+:[[:space:]]*(DENY_RE=|DENY_PAT=|deny_[^=]*=|PATTERN=|TOKEN_ALLOWLIST=)' \
      | grep -vE '^[0-9]+:.*grep.*_TOKEN=.*1' \
      | grep -vE '^[0-9]+:.*(grep|rg)[[:space:]]' \
| grep -vE '^[0-9]+:.*echo[[:space:]].*(BLOCK|missing|OK)' \
      | grep -vE '^[0-9]+:.*\"(_TOKEN|_PASSWORD|DATABASE_URL|PRIVATE KEY)=' \
      | grep -vE '^[0-9]+:.*\".*PRIVATE KEY\"' \
      | grep -vE '^[0-9]+:.*--set[[:space:]]' \
      | grep -vE '^[0-9]+:.*[[:space:]]-e[[:space:]]' \
      | grep -vE '^[0-9]+:.*except[[:space:]]+Exception' \
      | grep -q .; then
      echo "$f"
      return 0
    fi
  done
  return 1
}

for p in "${SCAN_PATHS[@]}"; do
  [ -e "$p" ] || continue
  hit_file="$(scan_grep "$DENY_RE" "$p" || true)"
  if [ -n "$hit_file" ]; then
    echo "ERROR_CODE=DENY_PATTERN_FOUND"
    echo "HIT_PATH=${hit_file}"
    exit 1
  fi
done

META_ONLY_OUTPUT_GUARD_V1_OK=1
exit 0
