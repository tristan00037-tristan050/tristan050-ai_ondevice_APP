#!/usr/bin/env bash
set -euo pipefail

ONE_COMMAND_VERIFY_V1_OK=0

trap 'echo "ONE_COMMAND_VERIFY_V1_OK=$ONE_COMMAND_VERIFY_V1_OK"' EXIT

script="tools/verify_one_v1.sh"
test -f "$script" || { echo "BLOCK: missing $script"; exit 1; }

# 1) 실행권한(권장)
test -x "$script" || { echo "BLOCK: $script must be executable"; exit 1; }

# 2) 내용에 preflight 호출이 있어야 함
grep -q "bash tools/preflight_v1.sh" "$script" || { echo "BLOCK: preflight call missing"; exit 1; }

# 3) 내용에 verify_repo_contracts 호출이 있어야 함
grep -q "bash scripts/verify/verify_repo_contracts.sh" "$script" || { echo "BLOCK: verify_repo_contracts call missing"; exit 1; }

# 4) 순서 고정: preflight가 verify보다 먼저
preflight_line="$(grep -n "bash tools/preflight_v1.sh" "$script" | head -n1 | cut -d: -f1)"
verify_line="$(grep -n "bash scripts/verify/verify_repo_contracts.sh" "$script" | head -n1 | cut -d: -f1)"
[ "$preflight_line" -lt "$verify_line" ] || { echo "BLOCK: preflight must run before verify"; exit 1; }

ONE_COMMAND_VERIFY_V1_OK=1
exit 0
