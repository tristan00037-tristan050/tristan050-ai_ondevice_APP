#!/usr/bin/env bash
# S7 Step4-B B (Algorithm Improvement PR) - One Shot
# Hard rules: Input Frozen / Baseline Frozen / Always On / Meta-only
# Goal: Regression Gate PASS + Strict Improvement (>=1 metric strictly greater than baseline)

set -euo pipefail
cd "$(git rev-parse --show-toplevel)/webcore_appcore_starter_4_17"

# (고정) 운영 서버 접속 코드
echo "ssh -o StrictHostKeyChecking=no <USER>@49.50.139.248"

# 0) Always On
bash scripts/ops/verify_s7_always_on.sh

# 1) 입력 고정(변경 0) 강제 확인
ROOT="$(git rev-parse --show-toplevel)"
APP="$ROOT/webcore_appcore_starter_4_17"

cd "$ROOT"
git fetch origin main --depth=1
CHANGED="$(git diff --name-only origin/main...HEAD)"
echo "$CHANGED" | sed -n "1,200p"

echo "$CHANGED" | rg -n "^webcore_appcore_starter_4_17/docs/ops/r10-s7-retriever-(goldenset\.jsonl|corpus\.jsonl)$" && {
  echo "FAIL: input must be frozen for Step4-B B"
  exit 1
} || true

echo "$CHANGED" | rg -n "^webcore_appcore_starter_4_17/docs/ops/r10-s7-retriever-metrics-baseline\.json$" && {
  echo "FAIL: baseline must not be modified in PR"
  exit 1
} || true

cd "$APP"

# 2) Safety gates (meta-only)
bash scripts/ops/verify_s7_corpus_no_pii.sh

# 3) 알고리즘 변경(정본 지침)
# - tiebreak(secondary_score)을 '동점(primary_score 동일)'에서만 반영
# - 결정적 tie-break 유지(마지막 tie-break는 doc_id)
#
# 구현 위치는 레포마다 다를 수 있으니, 아래 검색으로 실제 정렬 지점을 찾고 수정:
rg -n "TIEBREAK_ENABLE|secondary_score|secondaryScore|primary_score|primaryScore|rank|sort" scripts src webcore_appcore_starter_4_17 2>/dev/null || true

# TODO (개발자가 수행):
# - 실제 ranking comparator/정렬 로직 파일에서:
#   1) primary_score 내림차순
#   2) primary_score 동점일 때만 secondary_score 내림차순
#   3) 마지막 tie-break는 doc_id 오름차순(재현성)
# - 기존 opt-in이 있으면, CI 경로에서 tiebreak가 적용되도록
#   (a) 기본값을 enable로 하거나, 또는
#   (b) regression gate 실행 경로에서 TIEBREAK_ENABLE=1을 결정적으로 설정
#   중 하나를 선택(둘 다 하면 혼선).
#
# 주의: 출력/로그는 meta-only 유지. 쿼리/문서 원문 출력 금지.

# 4) Regression proof (must PASS)
export TIEBREAK_ENABLE=1
bash scripts/ops/prove_retriever_regression_gate.sh

# 5) Meta-only scan + debug evidence
META_ONLY_DEBUG=1 bash scripts/ops/verify_rag_meta_only.sh | tee /tmp/meta_only_debug_step4b_b.log

# 5) strict improvement JSON (SSOT 고정, meta-only)
# 보강 2: 항상 생성 (phase1 report 부재 시에도 strict_improvement=false로 생성)
OUT_JSON="docs/ops/r10-s7-step4b-b-strict-improvement.json"
BASELINE_JSON="docs/ops/r10-s7-retriever-metrics-baseline.json"
PHASE1_JSON="docs/ops/r10-s7-retriever-quality-phase1-report.json"

mkdir -p "$(dirname "$OUT_JSON")"

python3 - <<'PY' "$BASELINE_JSON" "$PHASE1_JSON" "$OUT_JSON"
import json, sys, time, os

baseline_path, phase1_path, out_path = sys.argv[1], sys.argv[2], sys.argv[3]

# baseline은 필수
if not os.path.exists(baseline_path):
    raise SystemExit(f"FAIL: baseline missing: {baseline_path}")

b = json.load(open(baseline_path, "r", encoding="utf-8"))

# phase1 report가 없으면 strict_improvement=false로 생성 (보강 2: 항상 생성)
if not os.path.exists(phase1_path):
    payload = {
      "ts": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
      "mode": "step4b-b",
      "result": {
        "strict_improvement": False,
        "improved_metrics": [],
        "regressed_metrics": [],
        "note": "phase1_report_missing"
      },
      "metrics": {}
    }
    open(out_path, "w", encoding="utf-8").write(json.dumps(payload, ensure_ascii=False, indent=2) + "\n")
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    sys.exit(0)

r = json.load(open(phase1_path, "r", encoding="utf-8"))

# "metrics" 키가 없으면(스키마 변동) 즉시 FAIL하도록 보수적으로 처리
if "metrics" not in b or "metrics" not in r or not isinstance(b["metrics"], dict) or not isinstance(r["metrics"], dict):
    raise SystemExit("FAIL: baseline/report JSON schema missing top-level 'metrics' dict")

# 숫자 메트릭만 비교(meta-only 유지)
metrics = {}
improved = []
regressed = []

for k, bv_raw in b["metrics"].items():
    if k not in r["metrics"]:
        continue
    rv_raw = r["metrics"][k]

    # 숫자형만 처리
    try:
        bv = float(bv_raw)
        rv = float(rv_raw)
    except Exception:
        continue

    dv = rv - bv
    metrics[k] = {"baseline": bv, "current": rv, "delta": dv}
    if dv > 0:
        improved.append(k)
    elif dv < 0:
        regressed.append(k)

payload = {
  "ts": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
  "mode": "step4b-b",
  "result": {
    "strict_improvement": len(improved) > 0,
    "improved_metrics": improved,
    "regressed_metrics": regressed
  },
  "metrics": metrics
}

open(out_path, "w", encoding="utf-8").write(json.dumps(payload, ensure_ascii=False, indent=2) + "\n")
print(json.dumps(payload, ensure_ascii=False, indent=2))
PY

echo "OK: strict improvement json -> $OUT_JSON"

# Step4-B B 정본: strict improvement가 없으면 ONE_SHOT은 FAIL로 종료
python3 - <<'PY' "$OUT_JSON"
import json, sys
j=json.load(open(sys.argv[1],"r",encoding="utf-8"))
if not j["result"]["strict_improvement"]:
    print("FAIL: strict improvement is 0 (no metric strictly improved)")
    raise SystemExit(1)
print("OK: strict improvement >= 1")
PY

# 6) 입력 고정 재확인(커밋 직전)
CHANGED2="$(git diff --name-only)"
echo "$CHANGED2" | rg -n "docs/ops/r10-s7-retriever-(goldenset\.jsonl|corpus\.jsonl)" && {
  echo "FAIL: input must be frozen for Step4-B B"
  exit 1
} || true

echo "$CHANGED2" | rg -n "docs/ops/r10-s7-retriever-metrics-baseline\.json" && {
  echo "FAIL: baseline must not be modified in PR"
  exit 1
} || true

# 7) 커밋
git add -A
git commit -m "feat(s7): step4-b-b enable deterministic tiebreak for strict improvement (input frozen)"
git push

