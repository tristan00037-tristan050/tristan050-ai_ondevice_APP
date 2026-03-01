#!/usr/bin/env bash
set -euo pipefail

META_ONLY_OUTPUT_GUARD_V1_OK=0
finish(){ echo "META_ONLY_OUTPUT_GUARD_V1_OK=${META_ONLY_OUTPUT_GUARD_V1_OK}"; }
trap finish EXIT

ROOT="$(git rev-parse --show-toplevel)"
cd "$ROOT"

# 스캔 범위(오탐 최소화를 위해 경로를 제한)
SCAN_PATHS=(
  "scripts/verify"
  "scripts/ops"
  "tools/exec_mode"
  "docs/ops"
)

# 최소 금지 패턴(원문/비밀/스택성 텍스트 차단)
DENY_RE='(Traceback|Exception:|stack trace|BEGIN [A-Z ]*PRIVATE KEY|_TOKEN=|_PASSWORD=|DATABASE_URL=)'

# grep 폴백. .sh 제외(검사용 패턴 포함). docs/ops/contracts 제외(정책 SSOT의 *_TOKEN=1 허용)
scan_grep() {
  local pat="$1"
  local dir="$2"
  find "$dir" -type f ! -name "*.sh" ! -path "*/contracts/*" 2>/dev/null | while IFS= read -r f; do
    [ -f "$f" ] && grep -In --binary-files=without-match -E "$pat" "$f" 2>/dev/null || true
  done
}

hits=0
for p in "${SCAN_PATHS[@]}"; do
  [ -e "$p" ] || continue
  out="$(scan_grep "$DENY_RE" "$p")"
  if [ -n "$out" ]; then
    # meta-only: 어느 파일의 어떤 패턴이 걸렸는지만 최소 정보로
    echo "ERROR_CODE=DENY_PATTERN_FOUND"
    echo "HIT_PATH=${p}"
    hits=1
    break
  fi
done

[ "$hits" = "0" ] || exit 1

META_ONLY_OUTPUT_GUARD_V1_OK=1
exit 0
