#!/usr/bin/env bash
set -euo pipefail

VERIFY_PURITY_FULL_SCOPE_OK=0
VERIFY_PURITY_ALLOWLIST_SSOT_OK=0

cleanup() {
  echo "VERIFY_PURITY_FULL_SCOPE_OK=${VERIFY_PURITY_FULL_SCOPE_OK}"
  echo "VERIFY_PURITY_ALLOWLIST_SSOT_OK=${VERIFY_PURITY_ALLOWLIST_SSOT_OK}"
  if [[ "${VERIFY_PURITY_FULL_SCOPE_OK}" == "1" ]] && \
     [[ "${VERIFY_PURITY_ALLOWLIST_SSOT_OK}" == "1" ]]; then
    exit 0
  fi
  exit 1
}
trap cleanup EXIT

ROOT="$(git rev-parse --show-toplevel)"
cd "$ROOT"

# 스캔 대상 폴더 2곳
SCAN_DIRS=(
  "scripts/verify"
  "webcore_appcore_starter_4_17/scripts/verify"
)

# SSOT allowlist 파일
ALLOWLIST="docs/ops/contracts/VERIFY_PURITY_ALLOWLIST_V1.txt"

# 1) allowlist 파일 존재 확인 (fail-closed)
test -s "$ALLOWLIST" || { echo "BLOCK: missing allowlist SSOT: $ALLOWLIST"; exit 1; }
VERIFY_PURITY_ALLOWLIST_SSOT_OK=1

# 2) allowlist에서 예외 파일 경로 읽기 (주석/빈 줄 제외)
ALLOWED_FILES=()
if [[ -s "$ALLOWLIST" ]]; then
  while IFS= read -r line; do
    # 주석/빈 줄 제외
    [[ -z "$line" ]] && continue
    [[ "$line" =~ ^[[:space:]]*# ]] && continue
    # 정확한 파일 경로만 허용 (공백 제거)
    line="${line#"${line%%[![:space:]]*}"}"  # trim leading
    line="${line%"${line##*[![:space:]]}"}"  # trim trailing
    [[ -n "$line" ]] && ALLOWED_FILES+=("$line")
  done < "$ALLOWLIST"
fi

# 3) 금지 패턴 (설치/다운로드/네트워크)
BAD_PATTERNS=(
  'npm\s+(ci|install)'
  'pnpm\s+(i|install)'
  'yarn\s+(install|add)'
  'playwright\s+install'
  'apt-get'
  'apk\s+add'
  'brew\s+install'
  'curl\s+https?://'
  'wget\s+https?://'
  'git\s+clone'
  'pip\s+install'
  'python\s+-m\s+pip'
  'python3\s+-m\s+pip'
)

# 4) allowlist에 있는 파일인지 확인
is_allowed() {
  local file="$1"
  if [[ ${#ALLOWED_FILES[@]} -eq 0 ]]; then
    return 1
  fi
  for allowed in "${ALLOWED_FILES[@]}"; do
    if [[ "$file" == "$allowed" ]]; then
      return 0
    fi
  done
  return 1
}

# 5) 각 스캔 대상 폴더에서 금지 패턴 탐지
FAIL=0
for dir in "${SCAN_DIRS[@]}"; do
  [[ -d "$dir" ]] || continue

  # 디렉터리 내 모든 .sh 파일 찾기
  while IFS= read -r -d '' file; do
    # 자기 자신은 스캔에서 제외
    [[ "$file" == "scripts/verify/verify_verify_purity_full_scope.sh" ]] && continue
    # allowlist에 있으면 스킵
    if is_allowed "$file"; then
      continue
    fi

    # 각 금지 패턴 검사
    for pattern in "${BAD_PATTERNS[@]}"; do
      # 주석/echo 제외 (실제 실행 명령만 차단)
      if grep -nE "$pattern" "$file" | grep -vE '^\s*#' | grep -vE 'echo' >/dev/null 2>&1; then
        echo "BLOCK: forbidden pattern in $file: $pattern"
        # 위반 파일 경로 + 금지 토큰 종류만 출력 (라인 내용 덤프 금지)
        grep -nE "$pattern" "$file" | grep -vE '^\s*#' | grep -vE 'echo' | head -5 | sed 's/:.*$/: [REDACTED]/'
        FAIL=1
      fi
    done
  done < <(find "$dir" -type f -name "*.sh" -print0 2>/dev/null || true)
done

if [[ "$FAIL" -ne 0 ]]; then
  exit 1
fi

VERIFY_PURITY_FULL_SCOPE_OK=1
exit 0
