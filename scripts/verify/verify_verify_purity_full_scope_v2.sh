#!/usr/bin/env bash
# P17-P0-07: VERIFY_PURITY_FULL_SCOPE_V2 — scripts/verify/** 내 설치/다운로드/빌드 1줄이라도 있으면 BLOCK (재발 0)
set -euo pipefail

VERIFY_PURITY_FULL_SCOPE_V2_OK=0
finish() { echo "VERIFY_PURITY_FULL_SCOPE_V2_OK=${VERIFY_PURITY_FULL_SCOPE_V2_OK}"; }
trap finish EXIT

ROOT="$(git rev-parse --show-toplevel)"
cd "$ROOT"

SCAN_DIR="scripts/verify"
[[ -d "$SCAN_DIR" ]] || { echo "ERROR_CODE=SCAN_DIR_MISSING"; exit 1; }

# 금지 패턴 (설치/다운로드/빌드) — allowlist 없음, 1건이라도 BLOCK
BAD_PATTERNS=(
  'npm\s+(ci|install)'
  'pnpm\s+(i|install)'
  'yarn\s+(install|add)'
  'playwright\s+install'
  'apt-get\s'
  'apk\s+add'
  'brew\s+install'
  'curl\s+https?://'
  'wget\s+https?://'
  'git\s+clone'
  'pip\s+install'
  'python\s+-m\s+pip'
  'python3\s+-m\s+pip'
  'cargo\s+build'
  'go\s+build'
  'make\s'
)

FAIL=0
while IFS= read -r -d '' file; do
  # 자기 자신 및 금지 패턴 나열 스크립트 제외 (패턴 문서화로만 사용)
  [[ "$file" == "$SCAN_DIR/verify_verify_purity_full_scope_v2.sh" ]] && continue
  [[ "$file" == "$SCAN_DIR/verify_verify_purity_no_install.sh" ]] && continue
  for pattern in "${BAD_PATTERNS[@]}"; do
    # Exclude comment lines and echo lines (grep -n outputs "LINENO:content")
    if grep -nE "$pattern" "$file" 2>/dev/null | grep -vE '^[0-9]+:[[:space:]]*#' | grep -vE '^[0-9]+:[[:space:]]*echo' >/dev/null 2>&1; then
      echo "ERROR_CODE=FORBIDDEN_PATTERN"
      echo "FILE=$file"
      echo "PATTERN=$pattern"
      FAIL=1
      exit 1
    fi
  done
done < <(find "$SCAN_DIR" -type f \( -name "*.sh" -o -name "*.mjs" -o -name "*.py" \) -print0 2>/dev/null || true)

VERIFY_PURITY_FULL_SCOPE_V2_OK=1
exit 0
