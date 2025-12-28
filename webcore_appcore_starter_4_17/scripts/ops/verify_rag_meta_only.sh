#!/usr/bin/env bash
set -euo pipefail

fail() { echo "FAIL: $*" >&2; exit 1; }

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "$ROOT"
DOCS_OPS_DIR="docs/ops"

FILES=()
while IFS= read -r f; do
  # corpus.jsonl은 입력 데이터이므로 스캔 대상에서 제외
  [[ "$f" != *corpus.jsonl ]] && FILES+=("$f")
done < <(
  find "$DOCS_OPS_DIR" -maxdepth 1 -type f \( \
    -name "r10-s7-retriever-*.json" -o \
    -name "r10-s7-retriever-*.jsonl" -o \
    -name "r10-s7-retriever-*.log" -o \
    -name "r10-s7-retriever-quality-*.json" -o \
    -name "r10-s7-retriever-quality-*.log" -o \
    -name "r10-s7-retriever-metrics-baseline.json" -o \
    -name "r10-s7-retriever-regression-proof.latest" -o \
    -name "r10-s7-retriever-regression-proof-*.log" \
  \) 2>/dev/null | sort
)

if [ "${#FILES[@]}" -eq 0 ]; then
  echo "OK: meta-only verifier (no S7 retriever artifacts found; nothing to scan)"
  exit 0
fi

if [ "${META_ONLY_DEBUG:-0}" = "1" ]; then
  echo "== meta-only scan targets =="
  for f in "${FILES[@]}"; do echo "$f"; done
fi

FORBIDDEN_JSON_KEYS_REGEX='\"(text|content|snippet|passage|raw|prompt|completion|message|document|context)\"[[:space:]]*:'
EMAIL_REGEX='[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}'
KRRN_REGEX='[0-9]{6}-[1-4][0-9]{6}'
URL_REGEX='https?://[^[:space:]]+'
PHONE_REGEX='(\+?[0-9]{1,3}[- ]?)?([0-9]{2,4}[- ]?){2,4}[0-9]{3,4}'

for f in "${FILES[@]}"; do
  base="$(basename "$f")"

  if [[ "$base" == *goldenset.schema.json ]]; then
    if rg -n -i "$FORBIDDEN_JSON_KEYS_REGEX" "$f" >/dev/null 2>&1; then
      rg -n -i "$FORBIDDEN_JSON_KEYS_REGEX" "$f" | head -n 20 >&2 || true
      fail "meta-only violation: forbidden raw-content-like key in schema $f"
    fi
    continue
  fi

  if [[ "$base" == *goldenset.jsonl ]]; then
    if rg -n -i "$FORBIDDEN_JSON_KEYS_REGEX" "$f" >/dev/null 2>&1; then
      rg -n -i "$FORBIDDEN_JSON_KEYS_REGEX" "$f" | head -n 20 >&2 || true
      fail "meta-only violation: forbidden raw-content-like key in goldenset $f"
    fi
    if rg -n -e "$EMAIL_REGEX" -e "$KRRN_REGEX" -e "$URL_REGEX" "$f" >/dev/null 2>&1; then
      rg -n -e "$EMAIL_REGEX" -e "$KRRN_REGEX" -e "$URL_REGEX" "$f" | head -n 20 >&2 || true
      fail "meta-only violation: PII/url-like pattern in goldenset $f"
    fi
    continue
  fi

  if [[ "$base" == *phase0-report.json || "$base" == *phase1-report.json ]]; then
    if rg -n "\"query\"[[:space:]]*:" "$f" >/dev/null 2>&1; then
      rg -n "\"query\"[[:space:]]*:" "$f" | head -n 20 >&2 || true
      fail "meta-only violation: query key found in report $f"
    fi
  fi

  if rg -n -i "$FORBIDDEN_JSON_KEYS_REGEX" "$f" >/dev/null 2>&1; then
    rg -n -i "$FORBIDDEN_JSON_KEYS_REGEX" "$f" | head -n 20 >&2 || true
    fail "meta-only violation: forbidden raw-content-like key in $f"
  fi

  if rg -n -e "$EMAIL_REGEX" -e "$KRRN_REGEX" -e "$URL_REGEX" "$f" >/dev/null 2>&1; then
    rg -n -e "$EMAIL_REGEX" -e "$KRRN_REGEX" -e "$URL_REGEX" "$f" | head -n 20 >&2 || true
    fail "meta-only violation: PII/url-like pattern in $f"
  fi

  case "$f" in
    *.log|*.json)
      if rg -n -e "$PHONE_REGEX" "$f" >/dev/null 2>&1; then
        rg -n -e "$PHONE_REGEX" "$f" | head -n 20 >&2 || true
        fail "meta-only violation: phone-like pattern in $f"
      fi
      ;;
  esac
done

echo "OK: meta-only verifier passed (${#FILES[@]} file(s) scanned)"
