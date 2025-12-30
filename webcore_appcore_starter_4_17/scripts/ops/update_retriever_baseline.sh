#!/usr/bin/env bash
set -euo pipefail
cd "$(git rev-parse --show-toplevel)/webcore_appcore_starter_4_17"

bash scripts/ops/verify_s7_always_on.sh
bash scripts/ops/verify_s7_corpus_no_pii.sh

BASELINE="${BASELINE:-docs/ops/r10-s7-retriever-metrics-baseline.json}"
REPORT="${REPORT:-docs/ops/r10-s7-retriever-quality-phase1-report.json}"

TOL="${TOL:-0.0}"

UPDATE=0
MIN_GAIN=0.0
REANCHOR_INPUT=0
while [[ $# -gt 0 ]]; do
  case "$1" in
    --update-baseline)
      UPDATE=1
      shift
      ;;
    --min-gain)
      MIN_GAIN="$2"
      shift 2
      ;;
    --reanchor-input)
      REANCHOR_INPUT=1
      shift
      ;;
    *)
      echo "FAIL: unknown option: $1" >&2
      echo "Usage: $0 [--update-baseline] [--min-gain VALUE] [--reanchor-input]" >&2
      exit 1
      ;;
  esac
done

# Phase1 report 생성(현 러너 기준)
bash scripts/ops/eval_retriever_quality_phase1.sh
test -f "$REPORT"

if [ "$UPDATE" -ne 1 ]; then
  echo "OK: baseline update skipped (require --update-baseline)"
  exit 0
fi

test -f "$BASELINE" || { echo "FAIL: baseline missing: $BASELINE" >&2; exit 1; }

# --reanchor-input는 main 브랜치에서만 허용
if [ "$REANCHOR_INPUT" -eq 1 ]; then
  CURRENT_BRANCH="$(git rev-parse --abbrev-ref HEAD)"
  if [ "$CURRENT_BRANCH" != "main" ]; then
    echo "FAIL: --reanchor-input is only allowed on main branch (current: $CURRENT_BRANCH)" >&2
    exit 1
  fi
  echo "OK: re-anchoring mode enabled (main branch only)"
fi

python3 - <<'PY' "$BASELINE" "$REPORT" "$TOL" "$MIN_GAIN" "$REANCHOR_INPUT"
import json, sys
base, rep, tol, min_gain, reanchor = sys.argv[1], sys.argv[2], float(sys.argv[3]), float(sys.argv[4]), int(sys.argv[5])
b=json.load(open(base,"r",encoding="utf-8"))
r=json.load(open(rep,"r",encoding="utf-8"))

# 입력 해시 비교
gset_mismatch = r["inputs"]["goldenset_sha256"] != b["inputs"]["goldenset_sha256"]
corpus_mismatch = r["inputs"]["corpus_sha256"] != b["inputs"]["corpus_sha256"]

if gset_mismatch or corpus_mismatch:
    if reanchor == 0:
        # 기본 동작: 입력 해시 불일치면 FAIL
        if gset_mismatch:
            raise SystemExit("FAIL: goldenset sha256 mismatch vs baseline (input change requires --reanchor-input flag)")
        if corpus_mismatch:
            raise SystemExit("FAIL: corpus sha256 mismatch vs baseline (input change requires --reanchor-input flag)")
    else:
        # re-anchoring 모드: 입력 해시 불일치 허용 (main에서만)
        print("OK: input hash mismatch detected, re-anchoring mode enabled")
        print(f"  goldenset: {b['inputs']['goldenset_sha256'][:16]}... -> {r['inputs']['goldenset_sha256'][:16]}...")
        print(f"  corpus: {b['inputs']['corpus_sha256'][:16]}... -> {r['inputs']['corpus_sha256'][:16]}...")

keys=["precision_at_k","recall_at_k","mrr_at_k","ndcg_at_k"]

# re-anchoring 모드가 아니면 기존 baseline과 비교
if reanchor == 0:
    decrease=[]
    improve=False
    for k in keys:
        bv=float(b["metrics"][k])
        rv=float(r["metrics"][k])
        if rv + tol < bv:
            decrease.append((k,bv,rv))
        if rv > bv + min_gain:
            improve=True

    if decrease:
        print("FAIL: cannot ratchet baseline (regression detected)")
        for k,bv,rv in decrease:
            print(f"- {k}: baseline={bv:.6f} current={rv:.6f} tol={tol}")
        raise SystemExit(1)

    if not improve and min_gain > 0.0:
        print(f"OK: no metric improved by MIN_GAIN={min_gain} (no baseline update)")
        raise SystemExit(0)

    print("OK: ratchet conditions satisfied (no decreases; improvement requirement met if configured)")
else:
    # re-anchoring 모드: 입력 해시가 변경되었으므로 기존 baseline metrics와 비교 불가
    # 현재 phase1 report metrics로 재고정
    print("OK: re-anchoring mode - baseline will be re-anchored to current input hash and metrics")
PY

# baseline 교체(meta-only)
# re-anchoring 모드든 일반 ratchet 모드든 동일하게 처리:
# 현재 phase1 report의 inputs sha와 metrics로 baseline 재고정
python3 - <<'PY' "$REPORT" "$BASELINE" "$REANCHOR_INPUT"
import json, sys, time
rep, base, reanchor = sys.argv[1], sys.argv[2], int(sys.argv[3])
r=json.load(open(rep,"r",encoding="utf-8"))
b={
  "ok": True,
  "phase": "S7/Phase1Baseline",
  "meta_only": True,
  "algo": r.get("algo", "lexical_overlap/v1"),
  "topk": r["topk"],
  "inputs": {
    "goldenset_sha256": r["inputs"]["goldenset_sha256"],
    "corpus_sha256": r["inputs"]["corpus_sha256"]
  },
  "metrics": r["metrics"],
  "created_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
}
open(base,"w",encoding="utf-8").write(json.dumps(b, ensure_ascii=False, indent=2) + "\n")
if reanchor == 1:
    print(f"OK: baseline re-anchored (input hash changed): {base}")
else:
    print(f"OK: baseline ratcheted: {base}")
PY

# meta-only 스캔 + DEBUG 출력(레포 증빙용)
META_ONLY_DEBUG=1 bash scripts/ops/verify_rag_meta_only.sh >/dev/null
echo "OK: update_retriever_baseline completed"

