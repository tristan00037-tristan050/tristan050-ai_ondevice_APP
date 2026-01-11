#!/usr/bin/env bash
#v/null)" || { echo "FAIL: not a git repository" >&2; exit 2; }
cd "${ROOT}/webcore_appcore_starter_4_17"

CONFIG_DIR="config"
TH="${CONFIG_RISK_THRESHOLD:-20}"
BASE_BRANCH="${BASE_BRANCH:-origin/main}"

echo "== Config Diff Risk Score Gate =="
echo "BASE_BRANCH=${BASE_BRANCH}"
echo "CONFIG_RISK_THRESHOLD=${TH}"

git fetch -q "${BASE_BRANCH%%/*}" "${BASE_BRANCH#*/}" 2>/dev/null || {
  echo "WARN: failed to fetch ${BASE_BRANCH}, using HEAD~1" >&2
  BASE_BRANCH="HEAD~1"
}

CHANGED="$(git diff --name-only "${BASE_BRANCH}...HEAD" -- "${CONFIG_DIR}" 2>/dev/null || true)"
if [ -z "${CHANGED}" ]; then
  echo "PASS: no config files changed"
  echo "RISK_SCORE=0"
  echo "RISK_FLAGS=[]"
  exit 0
fi

COUNT="$(printf "%s\n" "${CHANGED}" | sed "/^$/d" | wc -l | tr -d " ")"
echo "CHANGED_CONFIG_FILES=$(echo "${CHANGED}" | tr "\n" " ")"
echo "RISK_SCORE=${COUNT}"
echo "RISK_FLAGS=[\"CONFIG_FILES_CHANGED:${COUNT}\"]"

if [ "${COUNT}" -gt "${TH}" ]; then
  echo "FAIL: CONFIG_RISK_SCORE_EXCEEDED" >&2
  exit 1
fi

echo "PASS: Risk Score (${COUNT}) within threshold (${TH})"
