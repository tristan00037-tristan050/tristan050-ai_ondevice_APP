#!/usr/bin/env bash
set -euo pipefail
cd "$(git rev-parse --show-toplevel)/webcore_appcore_starter_4_17"

fail() { echo "FAIL: $*"; exit 1; }

# Build Anchor 문서/증빙 봉인 상태
test -f docs/R10S7_BUILD_ANCHOR_POST_MORTEM.md || fail "missing post-mortem"
test -f docs/ops/R10S7_BUILD_ANCHOR_CLOSEOUT_NOTICE_2025-12-28.md || fail "missing closeout notice"
test -f docs/ops/r10-s7-build-anchor-esm-proof.latest || fail "missing .latest"
PROOF="$(tr -d "\r\n" < docs/ops/r10-s7-build-anchor-esm-proof.latest)"
test -n "$PROOF" || fail ".latest empty"
test -f "docs/ops/$PROOF" || fail ".latest target missing: docs/ops/$PROOF"

# 금지 표현(결정성 훼손 문구) 유입 차단
if rg -n "부분 확인|타이밍 이슈" docs/ops/R10S7_BUILD_ANCHOR_CLOSEOUT_NOTICE_2025-12-28.md >/dev/null 2>&1; then
  rg -n "부분 확인|타이밍 이슈" docs/ops/R10S7_BUILD_ANCHOR_CLOSEOUT_NOTICE_2025-12-28.md || true
  fail "forbidden phrase detected"
fi

# Build Anchor Gate 스크립트 존재(Always On)
test -f scripts/ops/verify_build_anchor.sh || fail "missing verify_build_anchor.sh"
test -f scripts/ops/prove_build_anchor.sh || fail "missing prove_build_anchor.sh"
test -f scripts/ops/destructive_build_anchor_should_fail.sh || fail "missing destructive_build_anchor_should_fail.sh"

# Meta-only Policy (Always On): 존재해야 하며, 있으면 반드시 PASS해야 함
# 파일명은 레포 표준에 맞춰 사용 중인 것을 우선한다.
META_CANDIDATES=(
  "scripts/ops/verify_telemetry_rag_meta_only.sh"
  "scripts/ops/verify_rag_meta_only.sh"
)

META=""
for c in "${META_CANDIDATES[@]}"; do
  if [[ -f "$c" ]]; then META="$c"; break; fi
done

[[ -n "$META" ]] || fail "missing meta-only verifier (expected one of: ${META_CANDIDATES[*]})"
bash "$META"

echo "OK: S7 Always On invariants are present and verified"
