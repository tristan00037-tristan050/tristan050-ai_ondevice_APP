#!/usr/bin/env bash
# SSOT 변경 시 ADR 파일을 날짜 기반으로 생성합니다.
# 사용: bash scripts/ops/new_adr_for_ssot_change.sh
# 생성: docs/ssot/DECISIONS/ADR-YYYY-MM-DD-CHANGE.md

set -euo pipefail
REPO_ROOT="${REPO_ROOT:-$(git rev-parse --show-toplevel)}"
cd "$REPO_ROOT"
DATE="$(date +%Y-%m-%d)"
ADR="docs/ssot/DECISIONS/ADR-${DATE}-CHANGE.md"
cp docs/ssot/DECISIONS/ADR_TEMPLATE.md "$ADR"
echo "Created: $ADR"
