#!/usr/bin/env bash
set -euo pipefail

# R10-S5 P1-1: RAG Retrieval 게이트 검증
# 
# DoD:
# - 로컬에서 단 한 번의 스크립트로 PASS/FAIL이 결정됨
# - 업스트림/BFF 상태와 무관하게(=mock) 동작
# - 인덱스 생성 → 질의 → topK 결과가 기대 키워드를 포함하는지 검증
# - Baseline 대비 회귀 차단 (게이트 판정)

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
FIXTURES_DIR="${ROOT}/tools/rag_fixtures"
FIXTURES_FILE="${FIXTURES_DIR}/cs_tickets.json"
OPS_DIR="${ROOT}/docs/ops"
BASELINE_FILE="${OPS_DIR}/r10-s5-p1-1-retrieval-baseline.json"

mkdir -p "$OPS_DIR"

# 타임스탬프 생성
STAMP="$(date -u +%Y%m%dT%H%M%SZ)"
RUN_JSON="${OPS_DIR}/r10-s5-p1-1-retrieval-run-${STAMP}.json"
RUN_LOG="${OPS_DIR}/r10-s5-p1-1-retrieval-run-${STAMP}.log"

# 로그 파일로 리다이렉트 시작
exec > >(tee "$RUN_LOG") 2>&1

echo "[verify] RAG Retrieval 검증 (P1-1 Gates)"
echo ""

# 1) 픽스처 파일 존재 확인
if [ ! -f "${FIXTURES_FILE}" ]; then
  echo "[FAIL] 픽스처 파일이 없습니다: ${FIXTURES_FILE}"
  exit 1
fi

echo "[OK] 픽스처 파일 존재: ${FIXTURES_FILE}"

# 2) RAG 검색 테스트 실행
echo "[test] RAG 파이프라인 검색 테스트 실행"
PYTHON_SCRIPT="${ROOT}/scripts/_lib/rag_retrieval_test.py"

if [ ! -f "$PYTHON_SCRIPT" ]; then
  echo "[FAIL] Python 테스트 스크립트가 없습니다: ${PYTHON_SCRIPT}"
  exit 1
fi

# Python 스크립트 실행 및 JSON 저장
python3 "$PYTHON_SCRIPT" "$FIXTURES_FILE" > "$RUN_JSON" 2>&1

if [ ! -s "$RUN_JSON" ]; then
  echo "[FAIL] 검색 테스트 실행 실패 (JSON 비어있음)"
  exit 1
fi

echo "[OK] 검색 테스트 완료: ${RUN_JSON}"

# 3) Baseline 모드: baseline.json 생성 후 종료
if [ "${BASELINE_MODE:-0}" = "1" ]; then
  echo "[baseline] Baseline 모드: baseline.json 생성"
  cp "$RUN_JSON" "$BASELINE_FILE"
  echo "[OK] Baseline 생성 완료: ${BASELINE_FILE}"
  exit 0
fi

# 4) Baseline 로드 및 게이트 판정
if [ ! -f "$BASELINE_FILE" ]; then
  echo "[FAIL] Baseline 파일이 없습니다: ${BASELINE_FILE}"
  echo "[INFO] Baseline 생성: BASELINE_MODE=1 bash scripts/verify_rag_retrieval.sh"
  exit 2
fi

echo "[test] Baseline 대비 게이트 판정"

# Python으로 게이트 판정
GATE_RESULT=$(python3 - <<PY
import json
import sys

def load_json(path):
    with open(path, 'r', encoding='utf-8') as f:
        return json.load(f)

try:
    baseline = load_json("${BASELINE_FILE}")
    current = load_json("${RUN_JSON}")
except Exception as e:
    print(f"PARSE_ERROR: {e}", file=sys.stderr)
    sys.exit(2)

failures = []

# Hard Gates (무조건 0)
if current.get('determinismMismatchCount', 0) != 0:
    failures.append(f"determinismMismatchCount={current.get('determinismMismatchCount')} (expected 0)")

if current.get('networkRequestCount', 0) != 0:
    failures.append(f"networkRequestCount={current.get('networkRequestCount')} (expected 0)")

if current.get('telemetryBannedKeysLeakCount', 0) != 0:
    failures.append(f"telemetryBannedKeysLeakCount={current.get('telemetryBannedKeysLeakCount')} (expected 0)")

# Quality Gates (Baseline 대비 허용오차)
hit_at_5 = current.get('hitAt5', 0.0)
hit_at_10 = current.get('hitAt10', 0.0)
mrr_at_10 = current.get('mrrAt10', 0.0)
no_result_rate = current.get('noResultRate', 1.0)

baseline_hit_at_5 = baseline.get('hitAt5', 0.0)
baseline_hit_at_10 = baseline.get('hitAt10', 0.0)
baseline_mrr_at_10 = baseline.get('mrrAt10', 0.0)
baseline_no_result_rate = baseline.get('noResultRate', 0.0)

# Baseline 대비 허용오차
if hit_at_5 < baseline_hit_at_5 - 0.05:
    failures.append(f"hitAt5={hit_at_5:.3f} < baseline-0.05={baseline_hit_at_5-0.05:.3f}")

if hit_at_10 < baseline_hit_at_10 - 0.03:
    failures.append(f"hitAt10={hit_at_10:.3f} < baseline-0.03={baseline_hit_at_10-0.03:.3f}")

if mrr_at_10 < baseline_mrr_at_10 - 0.05:
    failures.append(f"mrrAt10={mrr_at_10:.3f} < baseline-0.05={baseline_mrr_at_10-0.05:.3f}")

if no_result_rate > baseline_no_result_rate + 0.05:
    failures.append(f"noResultRate={no_result_rate:.3f} > baseline+0.05={baseline_no_result_rate+0.05:.3f}")

# 절대 바닥값
if hit_at_5 < 0.60:
    failures.append(f"hitAt5={hit_at_5:.3f} < 0.60 (absolute floor)")

if hit_at_10 < 0.75:
    failures.append(f"hitAt10={hit_at_10:.3f} < 0.75 (absolute floor)")

if no_result_rate > 0.20:
    failures.append(f"noResultRate={no_result_rate:.3f} > 0.20 (absolute floor)")

# Performance Gates
p95_retrieve_ms = current.get('p95RetrieveMs', 0.0)
p99_retrieve_ms = current.get('p99RetrieveMs', 0.0)

baseline_p95 = baseline.get('p95RetrieveMs', 0.0)
baseline_p99 = baseline.get('p99RetrieveMs', 0.0)

# Baseline 대비 허용오차
p95_max = max(baseline_p95 * 1.5, baseline_p95 + 100)
p99_max = max(baseline_p99 * 2.0, baseline_p99 + 200)

if p95_retrieve_ms > p95_max:
    failures.append(f"p95RetrieveMs={p95_retrieve_ms:.1f} > max({baseline_p95*1.5:.1f}, {baseline_p95+100:.1f})={p95_max:.1f}")

if p99_retrieve_ms > p99_max:
    failures.append(f"p99RetrieveMs={p99_retrieve_ms:.1f} > max({baseline_p99*2.0:.1f}, {baseline_p99+200:.1f})={p99_max:.1f}")

# 절대 상한
if p95_retrieve_ms > 500:
    failures.append(f"p95RetrieveMs={p95_retrieve_ms:.1f} > 500 (absolute ceiling)")

if p99_retrieve_ms > 1000:
    failures.append(f"p99RetrieveMs={p99_retrieve_ms:.1f} > 1000 (absolute ceiling)")

if failures:
    print("GATE FAIL: " + "; ".join(failures))
    sys.exit(1)
else:
    print("GATE PASS")
    sys.exit(0)
PY
)

GATE_EXIT=$?

if [ $GATE_EXIT -eq 0 ]; then
  echo "[OK] $GATE_RESULT"
  echo ""
  echo "[OK] RAG Retrieval 검증 완료 (게이트 PASS)"
  exit 0
elif [ $GATE_EXIT -eq 2 ]; then
  echo "[FAIL] Baseline 파싱 오류"
  exit 2
else
  echo "[FAIL] $GATE_RESULT"
  echo ""
  echo "[FAIL] RAG Retrieval 검증 실패 (게이트 FAIL)"
  exit 1
fi
