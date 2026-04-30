#!/usr/bin/env bash
# scripts/ci/fetch_test_fixtures.sh
# ==================================
# CI에서 대용량 테스트 픽스처를 GitHub Releases 또는 Naver Cloud에서 다운로드.
# 레포에는 1 MB 미만 축소판만 커밋됨.
#
# 사용법:
#   bash scripts/ci/fetch_test_fixtures.sh
#
# 환경변수 (선택):
#   FIXTURES_SKIP=1   — 이미 존재하면 건너뜀 (캐시 활용)
set -euo pipefail

FIXTURES_DIR="tests/fixtures/large"
mkdir -p "${FIXTURES_DIR}"

# 현재 대용량 픽스처 없음 (2026-04-30 기준)
# 추가 시 아래 형식으로 작성:
#
# fetch_if_missing() {
#   local url="$1"
#   local dest="$2"
#   if [[ "${FIXTURES_SKIP:-0}" == "1" && -f "${dest}" ]]; then
#     echo "[SKIP] ${dest} 이미 존재함"
#     return
#   fi
#   echo "[FETCH] ${dest}"
#   curl -fsSL -o "${dest}" "${url}"
# }
#
# fetch_if_missing \
#   "https://github.com/tristan00037-tristan050/tristan050-ai_ondevice_APP/releases/download/test-fixtures-v1/big_sample.pdf" \
#   "${FIXTURES_DIR}/big_sample.pdf"

echo "fetch_test_fixtures: 현재 대용량 픽스처 없음 — 건너뜀"
