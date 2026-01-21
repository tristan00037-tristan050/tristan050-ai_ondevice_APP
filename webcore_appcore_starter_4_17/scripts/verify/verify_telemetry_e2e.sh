#!/usr/bin/env bash
set -euo pipefail

# Telemetry E2E Verification (fail-closed)
# Evidence sealing script for telemetry meta-only schema guard and ingest verification
# Uses npm only for test execution

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "$ROOT"

# Initialize evidence flags
TELEM_META_ONLY_SCHEMA_GUARD_OK=0
TELEM_REJECT_RAW_OK=0
TELEM_INGEST_OK=0

cleanup() {
  echo "TELEM_META_ONLY_SCHEMA_GUARD_OK=${TELEM_META_ONLY_SCHEMA_GUARD_OK}"
  echo "TELEM_REJECT_RAW_OK=${TELEM_REJECT_RAW_OK}"
  echo "TELEM_INGEST_OK=${TELEM_INGEST_OK}"
  
  if [[ "$TELEM_META_ONLY_SCHEMA_GUARD_OK" -eq 1 ]] && \
     [[ "$TELEM_REJECT_RAW_OK" -eq 1 ]] && \
     [[ "$TELEM_INGEST_OK" -eq 1 ]]; then
    exit 0
  else
    exit 1
  fi
}

trap cleanup EXIT

# Determine telemetry directory
if [[ -d "${ROOT}/webcore_appcore_starter_4_17" ]]; then
  TELEMETRY_DIR="${ROOT}/webcore_appcore_starter_4_17/backend/telemetry"
else
  TELEMETRY_DIR="${ROOT}/backend/telemetry"
fi

# Evidence-contamination guard (fail-closed)
# Scan ALL telemetry test files, not just one file.
TESTS_DIR="${TELEMETRY_DIR}/tests"

PAT_1="OK=1"
PAT_2="TELEM_META_ONLY_SCHEMA_GUARD_OK=1"
PAT_3="TELEM_REJECT_RAW_OK=1"
PAT_4="TELEM_INGEST_OK=1"

if [[ -d "$TESTS_DIR" ]]; then
  if command -v rg >/dev/null 2>&1; then
    HITS="$(rg -n --glob='*.test.ts' -e "$PAT_1" -e "$PAT_2" -e "$PAT_3" -e "$PAT_4" "$TESTS_DIR" 2>/dev/null || true)"
    if [[ -n "$HITS" ]]; then
      echo "FAIL: evidence-string contamination detected in telemetry tests:"
      echo "$HITS"
      exit 1
    fi
  elif command -v grep >/dev/null 2>&1; then
    HITS="$(grep -RIn --include='*.test.ts' -e "$PAT_1" -e "$PAT_2" -e "$PAT_3" -e "$PAT_4" "$TESTS_DIR" 2>/dev/null || true)"
    if [[ -n "$HITS" ]]; then
      echo "FAIL: evidence-string contamination detected in telemetry tests:"
      echo "$HITS"
      exit 1
    fi
  fi
else
  echo "FAIL: telemetry tests directory not found: $TESTS_DIR"
  exit 1
fi

# Check Node.js and npm availability
command -v node >/dev/null 2>&1 || { echo "FAIL: node not found"; exit 1; }
command -v npm >/dev/null 2>&1 || { echo "FAIL: npm not found"; exit 1; }

# Run tests using npm only (telemetry package only)
if [[ ! -d "$TELEMETRY_DIR" ]]; then
  echo "FAIL: telemetry directory not found: $TELEMETRY_DIR"
  exit 1
fi

# Install dependencies
# First install control_plane dependencies (telemetry depends on it)
CONTROL_PLANE_DIR="${ROOT}/webcore_appcore_starter_4_17/backend/control_plane"
if [[ -d "$CONTROL_PLANE_DIR" ]]; then
  if [[ -f "${CONTROL_PLANE_DIR}/package-lock.json" ]]; then
    npm --prefix "$CONTROL_PLANE_DIR" ci
  else
    npm --prefix "$CONTROL_PLANE_DIR" install
  fi
fi

# Then install telemetry dependencies
if [[ -f "${TELEMETRY_DIR}/package-lock.json" ]]; then
  npm --prefix "$TELEMETRY_DIR" ci
else
  npm --prefix "$TELEMETRY_DIR" install
fi

# Run tests
if npm --prefix "$TELEMETRY_DIR" test; then
  TELEM_META_ONLY_SCHEMA_GUARD_OK=1
  TELEM_REJECT_RAW_OK=1
  TELEM_INGEST_OK=1
  exit 0
else
  exit 1
fi

