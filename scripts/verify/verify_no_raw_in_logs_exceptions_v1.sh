#!/usr/bin/env bash
set -euo pipefail

NO_RAW_IN_LOGS_POLICY_V1_OK=0
NO_RAW_IN_REPORTS_SCAN_V1_OK=0
SENSITIVE_PATTERN_BLOCK_V1_OK=0
LONG_LINE_BLOCK_V1_OK=0

trap 'echo "NO_RAW_IN_LOGS_POLICY_V1_OK=${NO_RAW_IN_LOGS_POLICY_V1_OK}";
      echo "NO_RAW_IN_REPORTS_SCAN_V1_OK=${NO_RAW_IN_REPORTS_SCAN_V1_OK}";
      echo "SENSITIVE_PATTERN_BLOCK_V1_OK=${SENSITIVE_PATTERN_BLOCK_V1_OK}";
      echo "LONG_LINE_BLOCK_V1_OK=${LONG_LINE_BLOCK_V1_OK}"' EXIT

policy="docs/ops/contracts/NO_RAW_IN_LOGS_POLICY_V1.md"
patterns="docs/ops/contracts/PROOF_SENSITIVE_PATTERNS_V1.txt"
banned="docs/ops/contracts/META_ONLY_BANNED_KEYS_V1.txt"

test -f "$policy" || { echo "BLOCK: missing policy"; exit 1; }
grep -q "NO_RAW_IN_LOGS_POLICY_V1_TOKEN=1" "$policy" || { echo "BLOCK: missing policy token"; exit 1; }

test -f "$patterns" || { echo "BLOCK: missing sensitive patterns SSOT"; exit 1; }
test -f "$banned" || { echo "BLOCK: missing banned keys SSOT"; exit 1; }

# P2 Fix: fail-closed if sensitive-pattern SSOT is empty (or only blank/comment lines)
if ! grep -Eq '^[[:space:]]*[^#[:space:]].+' "$patterns"; then
  echo "BLOCK: sensitive-pattern SSOT is empty"
  exit 1
fi

# Targets that exist
reports_dir="docs/ops/reports"
proofs_dir="docs/ops/PROOFS"
scripts_dir="scripts"

# P2 Fix: restrict report exclusions to exact intended paths only
# - We only exclude:
#   - docs/ops/reports/archive/**
#   - docs/ops/reports/repo_contracts_latest.*
# Everything else under docs/ops/reports is scanned.
report_files=()
if [ -d "$reports_dir" ]; then
  while IFS= read -r f; do
    # exclude archive dir exactly
    case "$f" in
      "$reports_dir/archive/"* ) continue ;;
    esac
    # exclude exact repo_contracts_latest.* only
    base="$(basename "$f")"
    if [[ "$base" == repo_contracts_latest.json || "$base" == repo_contracts_latest.md ]]; then
      continue
    fi
    report_files+=("$f")
  done < <(find "$reports_dir" -type f 2>/dev/null || true)
fi

proof_files=()
if [ -d "$proofs_dir" ]; then
  # P1 Fix: include *.md (proof artifacts are markdown in this repo)
  while IFS= read -r f; do
    proof_files+=("$f")
  done < <(find "$proofs_dir" -type f 2>/dev/null || true)
fi

# Long-line scan: reports + PROOFS + scripts (as you already do)
long_targets=()
[ -d "$reports_dir" ] && long_targets+=("$reports_dir")
[ -d "$proofs_dir" ] && long_targets+=("$proofs_dir")
[ -d "$scripts_dir" ] && long_targets+=("$scripts_dir")

if [ "${#long_targets[@]}" -eq 0 ]; then
  echo "BLOCK: no scan targets found"
  exit 1
fi

# 1) Long-line block (>2000)
while IFS= read -r f; do
  [[ -z "$f" ]] && continue
  if awk 'length($0) > 2000 { exit 10 }' "$f"; then
    :
  else
    echo "BLOCK: long line (>2000) detected in $f"
    exit 1
  fi
done < <(find "${long_targets[@]}" -type f 2>/dev/null)

LONG_LINE_BLOCK_V1_OK=1

# 2) Sensitive patterns: scan reports (filtered) + PROOFS (all files incl md)
# Fail-closed if there are no files to scan at all (prevents silent disable)
sens_files=()
for f in "${report_files[@]}"; do sens_files+=("$f"); done
for f in "${proof_files[@]}"; do sens_files+=("$f"); done

if [ "${#sens_files[@]}" -eq 0 ]; then
  echo "BLOCK: no files selected for sensitive scan"
  exit 1
fi

if grep -InF -f "$patterns" "${sens_files[@]}" >/dev/null 2>&1; then
  echo "BLOCK: sensitive pattern detected in reports/proofs"
  exit 1
fi
SENSITIVE_PATTERN_BLOCK_V1_OK=1

# 3) Banned keys: JSON key declaration only, scan reports + PROOFS
keys_re="$(paste -sd'|' "$banned")"
[ -n "$keys_re" ] || { echo "BLOCK: empty banned keys"; exit 1; }

ban_files=()
for f in "${report_files[@]}"; do ban_files+=("$f"); done
for f in "${proof_files[@]}"; do ban_files+=("$f"); done

if [ "${#ban_files[@]}" -eq 0 ]; then
  echo "BLOCK: no files selected for banned-key scan"
  exit 1
fi

if grep -InE "\"(${keys_re})\"[[:space:]]*:" "${ban_files[@]}" >/dev/null 2>&1; then
  echo "BLOCK: banned raw-like key declaration detected"
  exit 1
fi

NO_RAW_IN_LOGS_POLICY_V1_OK=1
NO_RAW_IN_REPORTS_SCAN_V1_OK=1
exit 0
