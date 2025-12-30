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

# 1) 입력/베이스라인 "변경 0" 잠금(작업 시작 전)
#   - goldenset/corpus/baseline이 변경되면 즉시 중단
git status --porcelain
CHANGED="$(git diff --name-only)"
echo "$CHANGED" | sed -n '1,200p'

# rg가 없을 수 있으면 grep -E로 대체 가능하지만,
# 레포가 rg 기반이면 rg 사용을 우선합니다.
if echo "$CHANGED" | rg -n "^docs/ops/r10-s7-retriever-(goldenset\.jsonl|corpus\.jsonl)$|^docs/ops/r10-s7-retriever-metrics-baseline\.json$" ; then
  echo "FAIL: input/baseline files must not be modified in Step4-B B (input frozen PR)"
  exit 1
fi

# 2) 코퍼스 입력 안전 게이트(입력 변경 없더라도 정본 흐름 유지)
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

# 4) 로컬 검증(필수)
# - Regression Gate PASS
bash scripts/ops/prove_retriever_regression_gate.sh

# - Meta-only PASS
bash scripts/ops/verify_rag_meta_only.sh

# 5) strict improvement 체크(필수: baseline 대비 최소 1개 지표 strictly greater)
python3 - <<'PY'
import json
base="docs/ops/r10-s7-retriever-metrics-baseline.json"
rep ="docs/ops/r10-s7-retriever-quality-phase1-report.json"
b=json.load(open(base,"r",encoding="utf-8"))
r=json.load(open(rep ,"r",encoding="utf-8"))
keys=["precision_at_k","recall_at_k","mrr_at_k","ndcg_at_k"]

improved=[]
print("=== STRICT IMPROVEMENT CHECK (meta-only numbers) ===")
for k in keys:
    bv=float(b["metrics"][k])
    rv=float(r["metrics"][k])
    d=rv-bv
    print(f"{k}: baseline={bv:.6f} current={rv:.6f} delta={d:+.6f}")
    if rv>bv:
        improved.append(k)

print("IMPROVED_KEYS=", improved)
raise SystemExit(0 if improved else 1)
PY

# 6) 입력 고정 재확인(커밋 직전)
CHANGED2="$(git diff --name-only)"
if echo "$CHANGED2" | rg -n "^docs/ops/r10-s7-retriever-(goldenset\.jsonl|corpus\.jsonl)$|^docs/ops/r10-s7-retriever-metrics-baseline\.json$" ; then
  echo "FAIL: input/baseline files changed unexpectedly"
  exit 1
fi

# 7) 커밋
git add -A
git commit -m "feat(s7): step4-b-b enable deterministic tiebreak for strict improvement (input frozen)"
git push

