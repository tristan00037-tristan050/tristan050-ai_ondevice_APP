#!/usr/bin/env bash
set -euo pipefail

# ONE_COMMAND_VERIFY_V1
# - 목적: clean checkout에서 1커맨드로 동일한 실행 경험 제공
# - 순서 고정: preflight -> verify_repo_contracts
# - 주의: verify는 판정만, 준비는 preflight가 수행

bash tools/preflight_v1.sh
bash scripts/verify/verify_repo_contracts.sh ; echo "EXIT=$?"
