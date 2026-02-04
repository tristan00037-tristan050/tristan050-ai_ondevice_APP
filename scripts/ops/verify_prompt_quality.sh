#!/usr/bin/env bash
set -euo pipefail

# meta-only 출력 계약
# PROMPT_LINT_OK=1|0
# PROMPT_LINT_ERROR_COUNT=<n>
# PROMPT_LINT_ERROR=<path> reason_code=<...>

BASE_SHA="${PROMPT_LINT_BASE_SHA:-}"
HEAD_SHA="${PROMPT_LINT_HEAD_SHA:-}"

# 검사 대상(SSOT 경로)
TARGETS=(
  ".cursor/rules"
  "docs/ops/cursor_prompts"
  "docs/ops/contracts"
)

# README는 "설명 문서" 성격이 강할 수 있어 기본 제외(원하면 제거 가능)
is_exempt() {
  local f="$1"
  case "$f" in
    */README.md) return 0 ;;
  esac
  return 1
}

# 파일 목록 수집: PR에서는 diff 기반(변경된 파일만), 그 외에는 전체 스캔
collect_files() {
  if [[ -n "$BASE_SHA" && -n "$HEAD_SHA" ]]; then
    git diff --name-only "$BASE_SHA" "$HEAD_SHA" -- "${TARGETS[@]}" 2>/dev/null || true
  else
    find "${TARGETS[@]}" -type f \( -name "*.md" -o -name "*.mdc" \) 2>/dev/null || true
  fi
}

# 섹션(헤더) 존재 체크: 다국어/표기 흔들림을 고려해 키워드 기반
has_heading() {
  local f="$1"
  local re="$2"
  grep -Eiq '^[[:space:]]{0,3}#{1,6}[[:space:]]+'"$re" "$f"
}

# 스탬프(메타) 존재 체크
has_stamp() {
  local f="$1"
  local key="$2"
  grep -Eiq '^[[:space:]]*'"$key"':[[:space:]]*\S+' "$f"
}

# References 섹션이 "비어있지 않은지" 최소 확인(헤더만 있고 내용 0 방지)
references_nonempty() {
  local f="$1"
  awk '
    BEGIN{inref=0; c=0}
    /^[[:space:]]{0,3}#{1,6}[[:space:]]+/{ 
      if (inref==1) { exit }
    }
    /^[[:space:]]{0,3}#{1,6}[[:space:]]+(References|참고|근거)/{ inref=1; next }
    {
      if (inref==1) {
        # 헤더/공백만 제외하고, 최소 1줄 "실제 참고 항목"이 있으면 OK
        if ($0 ~ /[^[:space:]]/ && $0 !~ /^[[:space:]]*#/ ) c++
      }
    }
    END{ if (c>0) exit 0; else exit 1 }
  ' "$f"
}

ERRORS=()

add_error() {
  local path="$1"
  local code="$2"
  ERRORS+=("${path} reason_code=${code}")
}

check_one() {
  local f="$1"

  # 확장자 제한(원치 않으면 완화)
  if [[ ! "$f" =~ \.(md|mdc)$ ]]; then
    add_error "$f" "PROMPT_UNSUPPORTED_EXT"
    return
  fi

  # "박사급 프롬프트" 최소 구성요건(섹션 존재)
  has_heading "$f" "(Problem|문제|목적)"            || add_error "$f" "PROMPT_MISSING_PROBLEM"
  has_heading "$f" "(Scope|범위)"                  || add_error "$f" "PROMPT_MISSING_SCOPE"
  has_heading "$f" "(Invariants|불변식)"           || add_error "$f" "PROMPT_MISSING_INVARIANTS"
  has_heading "$f" "(DoD|Definition of Done|완료)" || add_error "$f" "PROMPT_MISSING_DOD"
  has_heading "$f" "(Failure|FMEA|실패)"           || add_error "$f" "PROMPT_MISSING_FMEA"
  has_heading "$f" "(Reason[_ -]?Codes|리즌코드|reason_code)" || add_error "$f" "PROMPT_MISSING_REASON_CODES"
  has_heading "$f" "(Rollback|되돌리기|복구)"       || add_error "$f" "PROMPT_MISSING_ROLLBACK"
  has_heading "$f" "(References|참고|근거)"         || add_error "$f" "PROMPT_MISSING_REFERENCES"

  # References 내용 비어있음 차단
  if has_heading "$f" "(References|참고|근거)"; then
    references_nonempty "$f" || add_error "$f" "PROMPT_EMPTY_REFERENCES"
  fi

  # 메타 스탬프(감사/책임/리뷰 주기) — "항시 박사급"을 유지하는 운영 장치
  has_stamp "$f" "Prompt-Version"  || add_error "$f" "PROMPT_MISSING_STAMP_VERSION"
  has_stamp "$f" "Owner"           || add_error "$f" "PROMPT_MISSING_STAMP_OWNER"
  has_stamp "$f" "Last-Reviewed"   || add_error "$f" "PROMPT_MISSING_STAMP_LAST_REVIEWED"
}

mapfile -t FILES < <(collect_files)

# 안정적(결정론적) 출력: 정렬 고정
IFS=$'\n' FILES=($(printf "%s\n" "${FILES[@]}" | sed '/^$/d' | sort -u))
unset IFS

for f in "${FILES[@]}"; do
  is_exempt "$f" && continue
  [[ -f "$f" ]] || continue
  check_one "$f"
done

# 에러 출력도 결정론적으로 정렬
if [[ "${#ERRORS[@]}" -eq 0 ]]; then
  echo "PROMPT_LINT_OK=1"
  echo "PROMPT_LINT_ERROR_COUNT=0"
  exit 0
fi

IFS=$'\n' SORTED=($(printf "%s\n" "${ERRORS[@]}" | sort))
unset IFS

for e in "${SORTED[@]}"; do
  echo "PROMPT_LINT_ERROR=${e}"
done
echo "PROMPT_LINT_OK=0"
echo "PROMPT_LINT_ERROR_COUNT=${#SORTED[@]}"
exit 1

