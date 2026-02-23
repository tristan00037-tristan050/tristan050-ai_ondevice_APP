#!/usr/bin/env bash
set -euo pipefail

WF=".github/workflows/release.yml"

test -f "$WF" || { echo "BLOCK: missing $WF"; exit 1; }

# 1) publish-and-deploy가 self-hosted인지(Phase1 SSOT)
if ! rg -n '^\s+publish-and-deploy:\s*$' "$WF" >/dev/null; then
  echo "BLOCK: publish-and-deploy job not found in $WF"
  exit 1
fi

# publish-and-deploy job block 내 runs-on 확인(간단 fail-closed)
pub_block="$(awk '
  $0 ~ /^  publish-and-deploy:/ { job=1 }
  job==1 { print }
  job==1 && NR>1 && $0 ~ /^  [a-zA-Z0-9_-]+:/ && $0 !~ /^  publish-and-deploy:/ { exit }
' "$WF")"

echo "$pub_block" | rg -n 'runs-on:\s*\[\s*self-hosted' >/dev/null || {
  echo "BLOCK: publish-and-deploy must run on self-hosted (Phase 1)."
  echo "hint: runs-on: [self-hosted, macOS, ARM64]"
  exit 1
}

# 2) KUBECONFIG를 먼저 고정한 뒤 Preflight(kubectl cluster-info)를 수행하는지
# (현재 흔한 재발: cluster-info가 KUBECONFIG 전에 실행됨)
rg -n 'Use local kubeconfig' "$WF" >/dev/null || {
  echo "BLOCK: missing 'Use local kubeconfig' step in publish-and-deploy."
  exit 1
}

# KUBECONFIG 설정 라인이 Preflight보다 위에 있어야 한다(간단 순서 체크)
line_kcfg="$(rg -n 'KUBECONFIG=\$CFG' "$WF" | rg 'publish-and-deploy' -n || true)"
# 위 방식이 환경에 따라 불안정하므로, 더 단순하게 파일 전체에서 순서 검사:
kcfg_line="$(rg -n 'KUBECONFIG=\$CFG' "$WF" | head -n1 | cut -d: -f1 || echo 0)"
pre_line="$(rg -n 'kubectl cluster-info' "$WF" | head -n1 | cut -d: -f1 || echo 0)"

if [ "${kcfg_line:-0}" -eq 0 ] || [ "${pre_line:-0}" -eq 0 ]; then
  echo "BLOCK: cannot locate KUBECONFIG set or kubectl cluster-info in $WF"
  exit 1
fi

if [ "$kcfg_line" -gt "$pre_line" ]; then
  echo "BLOCK: kubectl cluster-info appears before KUBECONFIG is set. Fix step order."
  exit 1
fi

echo "OK: release-bff Phase1 gate passed"
