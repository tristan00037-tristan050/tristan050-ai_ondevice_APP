#!/usr/bin/env bash
set -euo pipefail

# R10-S6 S6-1: Baseline-bump guard
# 
# PR에서 baseline 파일이 변경되면, 품질 지표가 하향 조정되는 것을 원천 차단
# 
# DoD:
# - hitAt5/hitAt10/mrrAt10는 감소 금지
# - noResultRate는 증가 금지
# - 위반 시 FAIL

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
OPS_DIR="${ROOT}/docs/ops"
BASELINE_FILE="${OPS_DIR}/r10-s5-p1-1-retrieval-baseline.json"

echo "[verify] Baseline-bump guard: baseline 파일 변경 검증"
echo ""

# Git이 사용 가능한지 확인
if ! command -v git > /dev/null; then
  echo "[WARN] git 명령어를 사용할 수 없습니다. Baseline-bump guard를 건너뜁니다."
  exit 0
fi

# main 브랜치와 비교
BASE_REF="${BASE_REF:-origin/main}"

# Baseline 파일이 변경되었는지 확인
if ! git diff --name-only "$BASE_REF" -- "$BASELINE_FILE" | grep -q "baseline.json"; then
  echo "[OK] Baseline 파일 변경 없음 (guard 불필요)"
  exit 0
fi

echo "[test] Baseline 파일 변경 감지: ${BASELINE_FILE}"
echo ""

# main의 baseline과 현재 baseline 비교
MAIN_BASELINE=$(git show "$BASE_REF:$BASELINE_FILE" 2>/dev/null || echo "")
CURRENT_BASELINE=$(cat "$BASELINE_FILE" 2>/dev/null || echo "")

if [ -z "$MAIN_BASELINE" ]; then
  echo "[WARN] main 브랜치에 baseline 파일이 없습니다. 신규 생성으로 간주합니다."
  exit 0
fi

if [ -z "$CURRENT_BASELINE" ]; then
  echo "[FAIL] 현재 baseline 파일이 없습니다."
  exit 1
fi

# Python으로 비교
GATE_RESULT=$(python3 - <<PY
import json
import sys

try:
    main_baseline = json.loads('''$MAIN_BASELINE''')
    current_baseline = json.loads('''$CURRENT_BASELINE''')
except Exception as e:
    print(f"PARSE_ERROR: {e}", file=sys.stderr)
    sys.exit(2)

failures = []

# hitAt5/hitAt10/mrrAt10는 감소 금지
main_hit_at_5 = main_baseline.get('hitAt5', 0.0)
current_hit_at_5 = current_baseline.get('hitAt5', 0.0)
if current_hit_at_5 < main_hit_at_5:
    failures.append(f"hitAt5 decreased: {current_hit_at_5:.3f} < {main_hit_at_5:.3f}")

main_hit_at_10 = main_baseline.get('hitAt10', 0.0)
current_hit_at_10 = current_baseline.get('hitAt10', 0.0)
if current_hit_at_10 < main_hit_at_10:
    failures.append(f"hitAt10 decreased: {current_hit_at_10:.3f} < {main_hit_at_10:.3f}")

main_mrr_at_10 = main_baseline.get('mrrAt10', 0.0)
current_mrr_at_10 = current_baseline.get('mrrAt10', 0.0)
if current_mrr_at_10 < main_mrr_at_10:
    failures.append(f"mrrAt10 decreased: {current_mrr_at_10:.3f} < {main_mrr_at_10:.3f}")

# noResultRate는 증가 금지
main_no_result_rate = main_baseline.get('noResultRate', 0.0)
current_no_result_rate = current_baseline.get('noResultRate', 0.0)
if current_no_result_rate > main_no_result_rate:
    failures.append(f"noResultRate increased: {current_no_result_rate:.3f} > {main_no_result_rate:.3f}")

if failures:
    print("BASELINE_BUMP_FAIL: " + "; ".join(failures))
    sys.exit(1)
else:
    print("BASELINE_BUMP_PASS")
    sys.exit(0)
PY
)

GATE_EXIT=$?

if [ $GATE_EXIT -eq 0 ]; then
  echo "[OK] $GATE_RESULT"
  echo ""
  echo "[OK] Baseline-bump guard PASS"
  exit 0
elif [ $GATE_EXIT -eq 2 ]; then
  echo "[FAIL] Baseline 파싱 오류"
  exit 2
else
  echo "[FAIL] $GATE_RESULT"
  echo ""
  echo "[FAIL] Baseline-bump guard FAIL (baseline 하향 조정 감지)"
  exit 1
fi

