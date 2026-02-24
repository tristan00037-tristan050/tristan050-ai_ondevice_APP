#!/usr/bin/env bash
# PR-P0-DEPLOY-02: BFF secret schema v1. Input: env vars only. No value output (meta-only, fail-closed).
set -euo pipefail

BFF_SECRET_SCHEMA_V1_OK=0
BFF_SECRET_FORMAT_OK=0
BFF_SECRET_EMPTY_STRING_BLOCK_OK=0
bff_secret_fail_class="unknown"
bff_secret_fail_hint=""
bff_secret_required_keys="DATABASE_URL,EXPORT_SIGN_SECRET"
bff_secret_value_dump="<forbidden>"

cleanup() {
  echo "BFF_SECRET_SCHEMA_V1_OK=${BFF_SECRET_SCHEMA_V1_OK}"
  echo "BFF_SECRET_FORMAT_OK=${BFF_SECRET_FORMAT_OK}"
  echo "BFF_SECRET_EMPTY_STRING_BLOCK_OK=${BFF_SECRET_EMPTY_STRING_BLOCK_OK}"
  echo "bff_secret_required_keys=${bff_secret_required_keys}"
  echo "bff_secret_value_dump=${bff_secret_value_dump}"
  if [[ "$BFF_SECRET_SCHEMA_V1_OK" != "1" ]]; then
    echo "bff_secret_fail_class=${bff_secret_fail_class}"
    echo "bff_secret_fail_hint=${bff_secret_fail_hint}"
  fi
}
trap cleanup EXIT

# Input from env only; never echo values
db_url="${DATABASE_URL:-}"
sign_secret="${EXPORT_SIGN_SECRET:-}"

# missing_key
if [[ -z "${db_url}" ]]; then
  bff_secret_fail_class="missing_key"
  bff_secret_fail_hint="DATABASE_URL not set or empty"
  exit 1
fi
if [[ -z "${sign_secret}" ]]; then
  bff_secret_fail_class="missing_key"
  bff_secret_fail_hint="EXPORT_SIGN_SECRET not set or empty"
  exit 1
fi

# empty_string (explicit empty string after trim)
db_trim="${db_url//[[:space:]]/}"
sign_trim="${sign_secret//[[:space:]]/}"
if [[ -z "$db_trim" ]]; then
  bff_secret_fail_class="empty_string"
  bff_secret_fail_hint="DATABASE_URL is empty or whitespace-only"
  exit 1
fi
if [[ -z "$sign_trim" ]]; then
  bff_secret_fail_class="empty_string"
  bff_secret_fail_hint="EXPORT_SIGN_SECRET is empty or whitespace-only"
  exit 1
fi
BFF_SECRET_EMPTY_STRING_BLOCK_OK=1

# DATABASE_URL: parse as URL (scheme + host/port)
if ! echo "$db_trim" | grep -qE '^[a-zA-Z][a-zA-Z0-9+.-]*://'; then
  bff_secret_fail_class="url_parse_failed"
  bff_secret_fail_hint="DATABASE_URL missing or invalid scheme"
  exit 1
fi
if ! echo "$db_trim" | grep -qE '://[^/?#]+'; then
  bff_secret_fail_class="url_parse_failed"
  bff_secret_fail_hint="DATABASE_URL missing host/authority"
  exit 1
fi

# EXPORT_SIGN_SECRET: length >= 16 (no value output)
sign_len="${#sign_trim}"
if [[ "$sign_len" -lt 16 ]]; then
  bff_secret_fail_class="format_invalid"
  bff_secret_fail_hint="EXPORT_SIGN_SECRET length must be >= 16 (got length=${sign_len})"
  exit 1
fi

BFF_SECRET_FORMAT_OK=1
BFF_SECRET_SCHEMA_V1_OK=1
exit 0
