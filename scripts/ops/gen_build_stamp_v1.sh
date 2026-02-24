#!/usr/bin/env bash
# PR-P0-DEPLOY-00: Generate .build_stamp.json (SSOT v1). Meta-only output; no raw sha.
# Run before verify_repo_contracts so DIST_FRESHNESS_POLICY_V1 always sees a matching stamp.
set -euo pipefail

REPO_ROOT="${REPO_ROOT:-$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)}"
cd "$REPO_ROOT"

build_stamp_v1_exit_code=1
build_stamp_v1_fail_class="unknown"
build_stamp_v1_fail_hint=""
build_stamp_path="webcore_appcore_starter_4_17/packages/bff-accounting/dist/.build_stamp.json"

cleanup() {
  echo "build_stamp_v1_exit_code=${build_stamp_v1_exit_code}"
  if [[ "$build_stamp_v1_exit_code" != "0" ]]; then
    echo "build_stamp_v1_fail_class=${build_stamp_v1_fail_class}"
    echo "build_stamp_v1_fail_hint=${build_stamp_v1_fail_hint}"
  fi
  echo "build_stamp_path=${build_stamp_path}"
  if [[ -n "${build_stamp_git_sha_len:-}" ]]; then
    echo "build_stamp_git_sha=<redacted> (len=${build_stamp_git_sha_len})"
  fi
}
trap cleanup EXIT

# tool: git
if ! command -v git >/dev/null 2>&1; then
  build_stamp_v1_fail_class="tool_missing"
  build_stamp_v1_fail_hint="git not found"
  exit 1
fi

# dist dir: create if missing (requires build:packages:server for full dist; we only need the stamp file path)
STAMP_DIR="${REPO_ROOT}/webcore_appcore_starter_4_17/packages/bff-accounting/dist"
if [[ ! -d "$(dirname "$STAMP_DIR")" ]]; then
  build_stamp_v1_fail_class="dist_dir_missing"
  build_stamp_v1_fail_hint="packages/bff-accounting not found; run from repo root"
  exit 1
fi
mkdir -p "$STAMP_DIR"

HEAD="$(git rev-parse HEAD 2>/dev/null)" || {
  build_stamp_v1_fail_class="tool_missing"
  build_stamp_v1_fail_hint="git rev-parse HEAD failed"
  exit 1
}
built_at_utc="$(date -u +"%Y-%m-%dT%H:%M:%SZ")"
workflow_name="${GITHUB_WORKFLOW:-local}"

# Write stamp (meta-only: do not log raw sha)
STAMP_FILE="${REPO_ROOT}/${build_stamp_path}"
if ! printf '%s\n' "{\"git_sha\":\"${HEAD}\",\"built_at_utc\":\"${built_at_utc}\",\"workflow_name\":\"${workflow_name}\"}" > "$STAMP_FILE"; then
  build_stamp_v1_fail_class="write_failed"
  build_stamp_v1_fail_hint="failed to write ${build_stamp_path}"
  exit 1
fi

build_stamp_v1_exit_code=0
build_stamp_git_sha_len="${#HEAD}"
echo "BUILD_STAMP_GENERATION_SSOT_V1_OK=1"
exit 0
