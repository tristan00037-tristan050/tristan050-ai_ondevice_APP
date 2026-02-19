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

test -f "$patterns" || { echo "BLOCK: missing sensitive patterns"; exit 1; }
test -f "$banned" || { echo "BLOCK: missing banned keys"; exit 1; }

targets=()
for d in "docs/ops/reports" "docs/ops/PROOFS" "scripts"; do
  if [ -d "$d" ]; then targets+=("$d"); fi
done

# Files to scan for sensitive patterns: reports and PROOFS, excluding DoD key outputs and docs that mention patterns by name
sensitive_files=()
if [ -d "docs/ops/reports" ]; then
  while IFS= read -r f; do
    [[ -z "$f" ]] && continue
    case "$f" in
      *repo_contracts*|*archive*) continue ;;
      *) sensitive_files+=("$f") ;;
    esac
  done < <(find docs/ops/reports -type f 2>/dev/null || true)
fi
if [ -d "docs/ops/PROOFS" ]; then
  while IFS= read -r f; do
    [[ -z "$f" ]] && continue
    # Exclude .md that document forbidden patterns (e.g. "금지 키/패턴 스캔: ... _TOKEN=")
    [[ "$f" == *.md ]] && continue
    sensitive_files+=("$f")
  done < <(find docs/ops/PROOFS -type f 2>/dev/null || true)
fi

if [ "${#targets[@]}" -eq 0 ]; then
  echo "BLOCK: no scan targets found (docs/ops/reports, docs/ops/PROOFS, scripts)"
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
done < <(find "${targets[@]}" -type f 2>/dev/null)

LONG_LINE_BLOCK_V1_OK=1

# 2) Sensitive patterns (substring) — scan selected report/proof files (exclude DoD key names and pattern-doc .md)
if [ "${#sensitive_files[@]}" -gt 0 ]; then
  if grep -InF -f "$patterns" "${sensitive_files[@]}" >/dev/null 2>&1; then
    echo "BLOCK: sensitive pattern detected in logs/reports/proofs"
    exit 1
  fi
fi
SENSITIVE_PATTERN_BLOCK_V1_OK=1

# 3) Banned keys (JSON key declaration only) — reports and PROOFS only (scripts may have test fixtures with "text" etc.)
banned_targets=()
for d in "docs/ops/reports" "docs/ops/PROOFS"; do
  if [ -d "$d" ]; then banned_targets+=("$d"); fi
done
keys_re="$(paste -sd'|' "$banned")"
[ -n "$keys_re" ] || { echo "BLOCK: empty banned keys"; exit 1; }

if [ "${#banned_targets[@]}" -gt 0 ]; then
  if grep -RInE "\"(${keys_re})\"[[:space:]]*:" "${banned_targets[@]}" >/dev/null 2>&1; then
    echo "BLOCK: banned raw-like key declaration detected"
    exit 1
  fi
fi

NO_RAW_IN_LOGS_POLICY_V1_OK=1
NO_RAW_IN_REPORTS_SCAN_V1_OK=1
exit 0
