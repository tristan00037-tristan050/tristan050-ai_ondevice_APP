#!/usr/bin/env bash
set -euo pipefail

fail() { echo "FAIL: $*" >&2; exit 1; }

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "$ROOT"

# Meta-only verifier for S7 Retriever Quality artifacts.
# Scope is intentionally limited to retriever-quality outputs (docs/ops/r10-s7-retriever-*).
# This avoids false positives from non-S7 docs while enforcing "no raw doc text / no PII" in outputs.

DOCS_OPS_DIR="docs/ops"

# Targets (only S7 retriever quality artifacts)
# - reports/proofs/logs produced by S7 scripts
# - golden set may include synthetic queries, but must not contain PII-like patterns
TARGET_GLOBS=(
  "$DOCS_OPS_DIR/r10-s7-retriever-"*.json"
  "$DOCS_OPS_DIR/r10-s7-retriever-"*.jsonl"
  "$DOCS_OPS_DIR/r10-s7-retriever-"*.log"
  "$DOCS_OPS_DIR/r10-s7-retriever-quality-"*.json"
  "$DOCS_OPS_DIR/r10-s7-retriever-quality-"*.log"
)

# Collect existing files
FILES=()
for g in "${TARGET_GLOBS[@]}"; do
  for f in $g; do
    [ -f "$f" ] && FILES+=("$f")
  done
done

if [ "${#FILES[@]}" -eq 0 ]; then
  echo "OK: meta-only verifier - no S7 retriever artifacts found, nothing to scan"
  exit 0
fi

# Forbidden JSON keys that imply raw text/content leakage (case-insensitive).
# NOTE: Do NOT block "query" because the golden set uses synthetic queries.
FORBIDDEN_JSON_KEYS_REGEX='\"(text|content|snippet|passage|raw|prompt|completion|message|document|context)\"[[:space:]]*:'

# PII-like patterns (best-effort; deterministic; no network)
EMAIL_REGEX='[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}'
# Generic phone-like (international + KR-ish), conservative (reduces false positives)
PHONE_REGEX='(\+?[0-9]{1,3}[- ]?)?([0-9]{2,4}[- ]?){2,4}[0-9]{3,4}'
# Korean RRNs (######-#######) pattern
KRRN_REGEX='[0-9]{6}-[1-4][0-9]{6}'
# URLs (raw links often imply accidental content dumps)
URL_REGEX='https?://[^[:space:]]+'

# Scan
for f in "${FILES[@]}"; do
  # 1) Block raw-content-like JSON keys (for json/jsonl; harmless on log too)
  if rg -n -i "$FORBIDDEN_JSON_KEYS_REGEX" "$f" >/dev/null 2>&1; then
    rg -n -i "$FORBIDDEN_JSON_KEYS_REGEX" "$f" | head -n 20 >&2 || true
    fail "meta-only violation: forbidden raw-content-like key in $f"
  fi

  # 2) Block PII-ish patterns
  if rg -n -e "$EMAIL_REGEX" -e "$KRRN_REGEX" -e "$URL_REGEX" "$f" >/dev/null 2>&1; then
    rg -n -e "$EMAIL_REGEX" -e "$KRRN_REGEX" -e "$URL_REGEX" "$f" | head -n 20 >&2 || true
    fail "meta-only violation: PII/url-like pattern in $f"
  fi

  # 3) Phone pattern: only enforce on logs/reports (not on jsonl golden set to reduce false positives)
  case "$f" in
    *.log|*.json)
      if rg -n -e "$PHONE_REGEX" "$f" >/dev/null 2>&1; then
        rg -n -e "$PHONE_REGEX" "$f" | head -n 20 >&2 || true
        fail "meta-only violation: phone-like pattern in $f"
      fi
    ;;
  esac
done

FILE_COUNT="${#FILES[@]}"
FILE_COUNT="${#FILES[@]}"
echo "OK: meta-only verifier passed - ${FILE_COUNT} files scanned"
