#!/usr/bin/env bash
# Policy Diff Risk Score Gate (Policy-as-Code v1)
# 정책 파일 변경 감지 및 Risk Score 산출 (meta-only)
# 임계치 초과 시 exit 1로 차단

set -euo pipefail

ROOT="$(git rev-parse --show-toplevel 2>/dev/null)" || {
  echo "FAIL: not a git repository" >&2
  exit 2
}

cd "${ROOT}/webcore_appcore_starter_4_17"

# 기본 임계치 (환경 변수로 오버라이드 가능)
RISK_THRESHOLD="${RISK_THRESHOLD:-20}"

# base 브랜치 (환경 변수 또는 기본값)
BASE_BRANCH="${BASE_BRANCH:-origin/main}"

# 정책 파일 디렉토리
POLICY_DIR="policy"

# Python 스크립트 경로
CALC_SCRIPT="scripts/ops/calc_policy_diff_risk.py"

echo "== Policy Diff Risk Score Gate =="
echo "BASE_BRANCH=${BASE_BRANCH}"
echo "RISK_THRESHOLD=${RISK_THRESHOLD}"

# base 브랜치 fetch
git fetch -q "${BASE_BRANCH%%/*}" "${BASE_BRANCH#*/}" 2>/dev/null || {
  echo "WARN: failed to fetch ${BASE_BRANCH}, using HEAD~1" >&2
  BASE_BRANCH="HEAD~1"
}

# 정책 파일 변경 감지
CHANGED_POLICIES=$(git diff --name-only "${BASE_BRANCH}...HEAD" -- "${POLICY_DIR}/*.yaml" 2>/dev/null || true)

if [ -z "${CHANGED_POLICIES}" ]; then
  echo "PASS: no policy files changed"
  echo "RISK_SCORE=0"
  echo "RISK_FLAGS=[]"
  exit 0
fi

echo "CHANGED_POLICIES=$(echo "${CHANGED_POLICIES}" | tr '\n' ' ')"

# 각 변경된 정책 파일에 대해 Risk Score 계산
TOTAL_RISK_SCORE=0
ALL_RISK_FLAGS=()

while IFS= read -r policy_file; do
  if [ -z "${policy_file}" ]; then
    continue
  fi
  
  echo ""
  echo "== Analyzing: ${policy_file} =="
  
  # base 브랜치와 현재 브랜치의 파일 경로
  OLD_FILE=$(mktemp)
  NEW_FILE=$(mktemp)
  
  # base 브랜치 버전
  git show "${BASE_BRANCH}:${policy_file}" > "${OLD_FILE}" 2>/dev/null || {
    echo "WARN: ${policy_file} not found in ${BASE_BRANCH}, treating as new file" >&2
    echo "" > "${OLD_FILE}"
  }
  
  # 현재 브랜치 버전
  if [ -f "${policy_file}" ]; then
    cp "${policy_file}" "${NEW_FILE}"
  else
    echo "WARN: ${policy_file} not found in current branch" >&2
    echo "" > "${NEW_FILE}"
  fi
  
  # Risk Score 계산
  RESULT=$(python3 "${CALC_SCRIPT}" "${OLD_FILE}" "${NEW_FILE}" 2>&1)
  
  if [ $? -ne 0 ]; then
    echo "FAIL: error calculating risk for ${policy_file}" >&2
    echo "${RESULT}" >&2
    rm -f "${OLD_FILE}" "${NEW_FILE}"
    exit 1
  fi
  
  # JSON 파싱
  RISK_SCORE=$(echo "${RESULT}" | python3 -c "import sys, json; d=json.load(sys.stdin); print(d.get('RISK_SCORE', 0))")
  RISK_FLAGS_JSON=$(echo "${RESULT}" | python3 -c "import sys, json; d=json.load(sys.stdin); import json; print(json.dumps(d.get('RISK_FLAGS', [])))")
  
  echo "RISK_SCORE=${RISK_SCORE}"
  echo "RISK_FLAGS=${RISK_FLAGS_JSON}"
  
  TOTAL_RISK_SCORE=$((TOTAL_RISK_SCORE + RISK_SCORE))
  
  # Flags 파싱 및 추가
  FLAGS_COUNT=$(echo "${RISK_FLAGS_JSON}" | python3 -c "import sys, json; print(len(json.load(sys.stdin)))")
  if [ "${FLAGS_COUNT}" -gt 0 ]; then
    while IFS= read -r flag; do
      if [ -n "${flag}" ]; then
        ALL_RISK_FLAGS+=("${flag}")
      fi
    done < <(echo "${RISK_FLAGS_JSON}" | python3 -c "import sys, json; [print(f) for f in json.load(sys.stdin)]")
  fi
  
  rm -f "${OLD_FILE}" "${NEW_FILE}"
done <<< "${CHANGED_POLICIES}"

echo ""
echo "== Summary =="
echo "TOTAL_RISK_SCORE=${TOTAL_RISK_SCORE}"
echo "RISK_THRESHOLD=${RISK_THRESHOLD}"

# Meta-only 출력 (본문 0)
if [ ${#ALL_RISK_FLAGS[@]} -eq 0 ]; then
  RISK_FLAGS_OUTPUT="[]"
else
  RISK_FLAGS_OUTPUT=$(printf '%s\n' "${ALL_RISK_FLAGS[@]}" | python3 -c "import sys, json; flags=[l.strip() for l in sys.stdin if l.strip()]; print(json.dumps(flags))")
fi

echo "RISK_FLAGS=${RISK_FLAGS_OUTPUT}"

# 임계치 초과 시 차단
if [ "${TOTAL_RISK_SCORE}" -gt "${RISK_THRESHOLD}" ]; then
  echo ""
  echo "FAIL: Risk Score (${TOTAL_RISK_SCORE}) exceeds threshold (${RISK_THRESHOLD})" >&2
  echo "Decision Owner approval required for policy changes." >&2
  exit 1
fi

echo "PASS: Risk Score (${TOTAL_RISK_SCORE}) within threshold (${RISK_THRESHOLD})"
exit 0

