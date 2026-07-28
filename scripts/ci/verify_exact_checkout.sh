#!/usr/bin/env bash
set -euo pipefail

expected="${1:-}"
actual="$(git rev-parse HEAD)"
tree="$(git rev-parse 'HEAD^{tree}')"
object_format="$(git rev-parse --show-object-format)"

case "${object_format}" in
  sha1) length=40 ;;
  sha256) length=64 ;;
  *)
    echo "FIRSTSCREEN_EXACT_CHECKOUT_OK=0"
    echo "ERROR_CODE=OBJECT_FORMAT_INVALID"
    exit 1
    ;;
esac

hex_pattern="^[0-9a-f]{${length}}$"
if [[ ! "${expected}" =~ ${hex_pattern} ]] \
  || [[ ! "${actual}" =~ ${hex_pattern} ]] \
  || [[ ! "${tree}" =~ ${hex_pattern} ]]; then
  echo "FIRSTSCREEN_EXACT_CHECKOUT_OK=0"
  echo "ERROR_CODE=CHECKOUT_IDENTITY_INVALID"
  exit 1
fi
if [[ "${actual}" != "${expected}" ]]; then
  echo "FIRSTSCREEN_EXACT_CHECKOUT_OK=0"
  echo "ERROR_CODE=CHECKOUT_HEAD_MISMATCH"
  exit 1
fi

echo "FIRSTSCREEN_EXACT_CHECKOUT_OK=1"
