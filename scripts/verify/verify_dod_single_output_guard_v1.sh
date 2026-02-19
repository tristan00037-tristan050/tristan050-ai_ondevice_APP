#!/usr/bin/env bash
set -euo pipefail

DOD_SINGLE_OUTPUT_GUARD_V1_OK=0

trap 'echo "DOD_SINGLE_OUTPUT_GUARD_V1_OK=${DOD_SINGLE_OUTPUT_GUARD_V1_OK}"' EXIT

f="scripts/verify/verify_repo_contracts.sh"
test -f "$f" || { echo "BLOCK: missing verify_repo_contracts.sh"; exit 1; }

# Must contain the key-capture filter (grep -vE ... _OK=)
grep -Fq "grep -vE '^[A-Z0-9_]+_OK=" "$f" || { echo "BLOCK: run_guard does not filter _OK lines"; exit 1; }
grep -Eq 'eval "\$key=\$val"' "$f" || { echo "BLOCK: run_guard does not apply captured keys"; exit 1; }

DOD_SINGLE_OUTPUT_GUARD_V1_OK=1
exit 0
