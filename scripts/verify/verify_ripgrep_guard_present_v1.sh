#!/usr/bin/env bash
set -euo pipefail

VERIFY_RIPGREP_GUARD_PRESENT_V1_OK=0

cleanup(){ echo "VERIFY_RIPGREP_GUARD_PRESENT_V1_OK=${VERIFY_RIPGREP_GUARD_PRESENT_V1_OK}"; }
trap cleanup EXIT

ROOT="$(git rev-parse --show-toplevel)"
cd "$ROOT"

test -s "scripts/verify/verify_no_ripgrep_in_verify_v1.sh" || { echo "BLOCK: missing ripgrep guard script"; exit 1; }

VERIFY_RIPGREP_GUARD_PRESENT_V1_OK=1
exit 0

