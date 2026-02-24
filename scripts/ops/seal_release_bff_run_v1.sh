#!/usr/bin/env bash
# PR-P0-DEPLOY-07: Seal release-bff run result (meta-only). No secrets/logs.
set -euo pipefail

REPO_ROOT="${REPO_ROOT:-$(cd "$(dirname "$0")/../.." && pwd)}"
RELEASE_TAG="${RELEASE_TAG:-}"
RUN_URL="${RUN_URL:-}"
HEAD_SHA="${HEAD_SHA:-}"
RELEASE_BFF_RESULT="${RELEASE_BFF_RESULT:-success}"
RELEASE_BFF_REASON_CODE="${RELEASE_BFF_REASON_CODE:-<none>}"

release_bff_seal_exit_code=1
sealed_report_path=""

emit() {
  echo "release_bff_seal_exit_code=${release_bff_seal_exit_code:-1}"
  echo "release_bff_tag=${RELEASE_TAG:-}"
  echo "release_bff_run_url=${RUN_URL:-}"
  echo "release_bff_head_sha=${HEAD_SHA:-}"
  echo "release_bff_result=${RELEASE_BFF_RESULT:-failed}"
  echo "release_bff_reason_code=${RELEASE_BFF_REASON_CODE:-<none>}"
  echo "sealed_report_path=${sealed_report_path:-}"
}

if [[ -z "$RELEASE_TAG" ]] || [[ -z "$RUN_URL" ]] || [[ -z "$HEAD_SHA" ]]; then
  RELEASE_BFF_RESULT="failed"
  RELEASE_BFF_REASON_CODE="missing_input"
  emit
  exit 1
fi

# YYYY-MM-DD from today (or env)
SEAL_DATE="${SEAL_DATE:-$(date -u +%Y-%m-%d 2>/dev/null || date +%Y-%m-%d)}"
REPORT_DIR="$REPO_ROOT/docs/DEPLOY_RUNS"
REPORT_FILE="$REPORT_DIR/${SEAL_DATE}.md"
sealed_report_path="docs/DEPLOY_RUNS/${SEAL_DATE}.md"

mkdir -p "$REPORT_DIR"

# Write meta-only report (no secrets, no log dumps)
{
  echo "# Release BFF run (sealed) — $SEAL_DATE"
  echo ""
  echo "| Key | Value |"
  echo "|-----|-------|"
  echo "| release_bff_tag | \`${RELEASE_TAG}\` |"
  echo "| release_bff_run_url | <${RUN_URL}> |"
  echo "| release_bff_head_sha | \`${HEAD_SHA}\` |"
  echo "| release_bff_result | ${RELEASE_BFF_RESULT} |"
  echo "| release_bff_reason_code | ${RELEASE_BFF_REASON_CODE} |"
  echo ""
  echo "<!-- meta-only, sealed by seal_release_bff_run_v1.sh -->"
} > "$REPORT_FILE"

release_bff_seal_exit_code=0
emit
exit 0
