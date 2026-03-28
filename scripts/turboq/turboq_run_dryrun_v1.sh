#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "$ROOT_DIR"

mkdir -p tmp

echo '================================================'
echo '  TurboQuant 통합 dry-run 검증'
echo '================================================'

find scripts/turboq -name '*.py' -print0 | xargs -0 python -m py_compile
printf 'COMPILE_OK=1
' | tee tmp/turboq_compile_result.txt

python scripts/turboq/turboq_verify_v1.py --dry-run

python -m pytest tests/turboq/ -v 2>&1 | tee tmp/turboq_unittest_result.txt

bash -n scripts/turboq/turboq_run_dryrun_v1.sh
printf 'SHELL_SYNTAX_OK=1
' | tee tmp/turboq_shell_syntax_result.txt

echo '================================================'
echo '  dry-run 완료. GPU/실기기 DoD는 실행팀 범위입니다.'
echo '================================================'
