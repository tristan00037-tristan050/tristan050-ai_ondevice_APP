#!/usr/bin/env bash
set -euo pipefail

CANONICALIZE_SINGLE_SOURCE_NO_DUPLICATION_OK=0
trap 'echo "CANONICALIZE_SINGLE_SOURCE_NO_DUPLICATION_OK=$CANONICALIZE_SINGLE_SOURCE_NO_DUPLICATION_OK"' EXIT

# canonicalize_v1.* 가 1개만 존재해야 함
count="$(find packages -type f -name 'canonicalize_v1.*' | wc -l | tr -d ' ')"
[ "$count" = "1" ] || { echo "BLOCK: canonicalize_v1 duplicated (count=$count)"; exit 1; }

CANONICALIZE_SINGLE_SOURCE_NO_DUPLICATION_OK=1
exit 0
