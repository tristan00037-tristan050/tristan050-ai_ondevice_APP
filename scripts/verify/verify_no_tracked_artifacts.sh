#!/usr/bin/env bash
set -euo pipefail

# .artifacts는 CI 런타임 생성물 경로(커밋 금지)
hits="$(git ls-files ".artifacts" 2>/dev/null || true)"
if [ -n "$hits" ]; then
  echo "BLOCK: .artifacts contains tracked files:"
  echo "$hits"
  echo "ARTIFACTS_NOT_TRACKED_OK=0"
  exit 1
fi

echo "ARTIFACTS_NOT_TRACKED_OK=1"
