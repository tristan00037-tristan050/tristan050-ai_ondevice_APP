#!/usr/bin/env bash
# P0-02: SSOT change contract v1. When autodecision SSOT files change, prove producer emit + presence.
# Meta-only, fail-closed, 원문0.
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "$REPO_ROOT"

AUTODECISION_SSOT_CHANGE_CONTRACT_OK=0
ERROR_CODE=""

REQUIRED_KEYS_SSOT="$REPO_ROOT/docs/ops/contracts/AUTODECISION_REQUIRED_KEYS_V1.txt"
REPO_REPORT="$REPO_ROOT/docs/ops/reports/repo_contracts_latest.json"
AUTODECISION_JSON="$REPO_ROOT/docs/ops/reports/autodecision_latest.json"

# Base ref for diff (CI: GITHUB_BASE_REF, local: main)
BASE_REF="${GITHUB_BASE_REF:-main}"
# Ensure we have origin/base for diff (fetch-depth: 0 in CI)
if ! git rev-parse "origin/${BASE_REF}" >/dev/null 2>&1; then
  ERROR_CODE="BASE_REF_UNKNOWN"
  echo "AUTODECISION_SSOT_CHANGE_CONTRACT_OK=0"
  echo "ERROR_CODE=${ERROR_CODE}"
  exit 1
fi

# SSOT change detection (any AUTODECISION SSOT under docs/ops/contracts)
changed=""
if git diff --name-only "origin/${BASE_REF}...HEAD" 2>/dev/null | grep -qE "^docs/ops/contracts/AUTODECISION_.*\.txt$"; then
  changed=1
fi

if [[ -z "$changed" ]]; then
  echo "AUTODECISION_SSOT_CHANGE_CONTRACT_OK=1"
  echo "ERROR_CODE=SKIP"
  exit 0
fi

# SSOT changed: run producer, then verify required keys presence and autodecision count
bash scripts/ops/gen_repo_guard_report_v1.sh

if [[ ! -f "$REPO_REPORT" ]] || [[ ! -s "$REPO_REPORT" ]]; then
  ERROR_CODE="REPO_REPORT_MISSING"
  echo "AUTODECISION_SSOT_CHANGE_CONTRACT_OK=0"
  echo "ERROR_CODE=${ERROR_CODE}"
  exit 1
fi

# Load required keys (one per line, # skip)
required_keys=()
while IFS= read -r line; do
  line="${line%%#*}"
  line="${line#"${line%%[![:space:]]*}"}"
  line="${line%"${line##*[![:space:]]}"}"
  [[ -z "$line" ]] && continue
  [[ "$line" =~ ^[A-Z0-9_]+$ ]] || continue
  required_keys+=( "$line" )
done < "$REQUIRED_KEYS_SSOT"

# Each required key must exist in repo report with value "0" or "1"
# Use absolute path so Node resolves the same file gen_repo_guard_report wrote
for k in "${required_keys[@]}"; do
  val=$(node -e "
    const fs = require('fs');
    const p = process.argv[1];
    const data = fs.readFileSync(p, 'utf8');
    const r = JSON.parse(data);
    const v = r && r.keys && r.keys[process.argv[2]];
    process.stdout.write(v !== undefined && v !== null ? String(v) : '');
  " "$REPO_REPORT" "$k" 2>/dev/null || true)
  if [[ "$val" != "0" ]] && [[ "$val" != "1" ]]; then
    ERROR_CODE="REQUIRED_KEY_INVALID"
    echo "AUTODECISION_SSOT_CHANGE_CONTRACT_OK=0"
    echo "ERROR_CODE=${ERROR_CODE}"
    exit 1
  fi
done

bash scripts/verify/verify_autodecision_from_reports_v1.sh

# autodecision_missing_required_keys_count must be 0
missing=$(node -e "
  const r = require(process.argv[1]);
  const n = r && typeof r.autodecision_missing_required_keys_count === 'number'
    ? r.autodecision_missing_required_keys_count : -1;
  process.stdout.write(String(n));
" "$AUTODECISION_JSON" 2>/dev/null || true)

if [[ "$missing" != "0" ]]; then
  ERROR_CODE="MISSING_REQUIRED_COUNT_NONZERO"
  echo "AUTODECISION_SSOT_CHANGE_CONTRACT_OK=0"
  echo "ERROR_CODE=${ERROR_CODE}"
  exit 1
fi

echo "AUTODECISION_SSOT_CHANGE_CONTRACT_OK=1"
exit 0
