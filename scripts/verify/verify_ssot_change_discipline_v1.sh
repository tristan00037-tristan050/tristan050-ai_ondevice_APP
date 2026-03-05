#!/usr/bin/env bash
set -euo pipefail

BASE_REF="${BASE_REF:-origin/main}"
SSOT="docs/ssot/SSOT_V1.md"
CHANGELOG="docs/ssot/CHANGELOG.md"
ADR_DIR="docs/ssot/DECISIONS"

# base ref 없으면 무조건 실패(통과 금지)
git rev-parse --verify "$BASE_REF" >/dev/null 2>&1 || {
  echo "ERROR_CODE=BASE_REF_UNAVAILABLE"
  echo "HIT_REF=$BASE_REF"
  exit 1
}

# SSOT가 바뀌었는지 확인
SSOT_CHANGED=0
git diff --name-only "$BASE_REF...HEAD" -- "$SSOT" | grep -q . && SSOT_CHANGED=1 || true

# SSOT가 안 바뀌면 그냥 통과
if [[ "$SSOT_CHANGED" -eq 0 ]]; then
  echo "SSOT_CHANGE_DISCIPLINE_V1_OK=1"
  exit 0
fi

# SSOT가 바뀌면 CHANGELOG도 반드시 바뀌어야 함
git diff --name-only "$BASE_REF...HEAD" -- "$CHANGELOG" | grep -q . || {
  echo "ERROR_CODE=SSOT_CHANGED_WITHOUT_CHANGELOG"
  echo "HIT_PATH=$CHANGELOG"
  exit 1
}

# SSOT가 바뀌면 ADR도 최소 1개 바뀌어야 함
git diff --name-only "$BASE_REF...HEAD" -- "$ADR_DIR" | grep -q . || {
  echo "ERROR_CODE=SSOT_CHANGED_WITHOUT_ADR"
  echo "HIT_PATH=$ADR_DIR"
  exit 1
}

echo "SSOT_CHANGE_DISCIPLINE_V1_OK=1"
