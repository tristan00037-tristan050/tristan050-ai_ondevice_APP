#!/usr/bin/env bash
set -euo pipefail

fail() { echo "FAIL: $*" >&2; exit 1; }

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "$ROOT"

DOCS_OPS_DIR="docs/ops"

# Scope is intentionally limited to S7 retriever-quality artifacts only.
# This prevents false positives from unrelated docs while enforcing meta-only for outputs.
# NOTE: schema.json files are excluded (they legitimately contain JSON Schema URLs)
FILES=()
while IFS= read -r line; do
  [ -n "$line" ] && [[ "$line" != *.schema.json ]] && FILES+=("$line")
done < <(
  find "$DOCS_OPS_DIR" -maxdepth 1 -type f \( \
    -name 'r10-s7-retriever-*.json' -o \
    -name 'r10-s7-retriever-*.jsonl' -o \
    -name 'r10-s7-retriever-*.log' -o \
    -name 'r10-s7-retriever-quality-*.json' -o \
    -name 'r10-s7-retriever-quality-*.log' \
  \) 2>/dev/null | sort
)

if [ "${#FILES[@]}" -eq 0 ]; then
  echo "OK: meta-only verifier (no S7 retriever artifacts found; nothing to scan)"
  exit 0
fi

# Forbidden keys that imply raw text/content leakage (case-insensitive).
FORBIDDEN_JSON_KEYS_REGEX='\"(text|content|snippet|passage|raw|prompt|completion|message|document|context)\"[[:space:]]*:'

# PII-ish patterns (best-effort, deterministic; no network)
EMAIL_REGEX='[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}'
KRRN_REGEX='[0-9]{6}-[1-4][0-9]{6}'
URL_REGEX='https?://[^[:space:]]+'
PHONE_REGEX='(\+?[0-9]{1,3}[- ]?)?([0-9]{2,4}[- ]?){2,4}[0-9]{3,4}'

# File-type-specific rules
for f in "${FILES[@]}"; do
  case "$f" in
    # Goldenset JSONL: query allowed (synthetic), PII forbidden, raw-content keys forbidden
    *.jsonl)
      # 1) Forbidden JSON keys (raw-content-like)
      if rg -n -i "$FORBIDDEN_JSON_KEYS_REGEX" "$f" >/dev/null 2>&1; then
        rg -n -i "$FORBIDDEN_JSON_KEYS_REGEX" "$f" | head -n 20 >&2 || true
        fail "meta-only violation: forbidden raw-content-like key in $f"
      fi
      # 2) PII patterns (email, RRN, URL)
      if rg -n -e "$EMAIL_REGEX" -e "$KRRN_REGEX" -e "$URL_REGEX" "$f" >/dev/null 2>&1; then
        rg -n -e "$EMAIL_REGEX" -e "$KRRN_REGEX" -e "$URL_REGEX" "$f" | head -n 20 >&2 || true
        fail "meta-only violation: PII/url-like pattern in $f"
      fi
      # query key is allowed in goldenset (synthetic queries only)
      ;;
    
    # Phase0 report JSON: query forbidden, raw-content keys forbidden, PII forbidden
    *phase0-report.json)
      # 1) Query key is forbidden in reports
      if rg -n '"query"' "$f" >/dev/null 2>&1; then
        rg -n '"query"' "$f" | head -n 20 >&2 || true
        fail "meta-only violation: query key found in report $f"
      fi
      # 2) Forbidden JSON keys (raw-content-like)
      if rg -n -i "$FORBIDDEN_JSON_KEYS_REGEX" "$f" >/dev/null 2>&1; then
        rg -n -i "$FORBIDDEN_JSON_KEYS_REGEX" "$f" | head -n 20 >&2 || true
        fail "meta-only violation: forbidden raw-content-like key in $f"
      fi
      # 3) PII patterns
      if rg -n -e "$EMAIL_REGEX" -e "$KRRN_REGEX" -e "$URL_REGEX" "$f" >/dev/null 2>&1; then
        rg -n -e "$EMAIL_REGEX" -e "$KRRN_REGEX" -e "$URL_REGEX" "$f" | head -n 20 >&2 || true
        fail "meta-only violation: PII/url-like pattern in $f"
      fi
      # 4) Phone pattern
      if rg -n -e "$PHONE_REGEX" "$f" >/dev/null 2>&1; then
        rg -n -e "$PHONE_REGEX" "$f" | head -n 20 >&2 || true
        fail "meta-only violation: phone-like pattern in $f"
      fi
      ;;
    
    # Proof logs: raw-content keys forbidden, PII forbidden
    *proof-*.log)
      # 1) Forbidden JSON keys (raw-content-like)
      if rg -n -i "$FORBIDDEN_JSON_KEYS_REGEX" "$f" >/dev/null 2>&1; then
        rg -n -i "$FORBIDDEN_JSON_KEYS_REGEX" "$f" | head -n 20 >&2 || true
        fail "meta-only violation: forbidden raw-content-like key in $f"
      fi
      # 2) PII patterns
      if rg -n -e "$EMAIL_REGEX" -e "$KRRN_REGEX" -e "$URL_REGEX" "$f" >/dev/null 2>&1; then
        rg -n -e "$EMAIL_REGEX" -e "$KRRN_REGEX" -e "$URL_REGEX" "$f" | head -n 20 >&2 || true
        fail "meta-only violation: PII/url-like pattern in $f"
      fi
      # 3) Phone pattern
      if rg -n -e "$PHONE_REGEX" "$f" >/dev/null 2>&1; then
        rg -n -e "$PHONE_REGEX" "$f" | head -n 20 >&2 || true
        fail "meta-only violation: phone-like pattern in $f"
      fi
      ;;
    
    # Other JSON/LOG files: apply all checks
    *)
      # 1) Forbidden JSON keys
      if rg -n -i "$FORBIDDEN_JSON_KEYS_REGEX" "$f" >/dev/null 2>&1; then
        rg -n -i "$FORBIDDEN_JSON_KEYS_REGEX" "$f" | head -n 20 >&2 || true
        fail "meta-only violation: forbidden raw-content-like key in $f"
      fi
      # 2) PII patterns
      if rg -n -e "$EMAIL_REGEX" -e "$KRRN_REGEX" -e "$URL_REGEX" "$f" >/dev/null 2>&1; then
        rg -n -e "$EMAIL_REGEX" -e "$KRRN_REGEX" -e "$URL_REGEX" "$f" | head -n 20 >&2 || true
        fail "meta-only violation: PII/url-like pattern in $f"
      fi
      # 3) Phone pattern (for JSON/LOG)
      case "$f" in
        *.log|*.json)
          if rg -n -e "$PHONE_REGEX" "$f" >/dev/null 2>&1; then
            rg -n -e "$PHONE_REGEX" "$f" | head -n 20 >&2 || true
            fail "meta-only violation: phone-like pattern in $f"
          fi
          ;;
      esac
      ;;
  esac
done

echo "OK: meta-only verifier passed (${#FILES[@]} file(s) scanned)"
