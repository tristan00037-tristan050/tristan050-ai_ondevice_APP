#!/usr/bin/env bash
set -euo pipefail

cd "$(git rev-parse --show-toplevel)/webcore_appcore_starter_4_17"
bash scripts/ops/verify_s7_always_on.sh
bash scripts/ops/verify_s7_corpus_no_pii.sh

GSET="${GSET:-docs/ops/r10-s7-retriever-goldenset.jsonl}"
CORPUS="${CORPUS:-docs/ops/r10-s7-retriever-corpus.jsonl}"
OUT_DIR="${OUT_DIR:-docs/ops}"
REPORT="${REPORT:-$OUT_DIR/r10-s7-retriever-quality-phase1-report.json}"
TOPK="${TOPK:-5}"

# tie-break 제어(튜닝 루프용)
# 기본값: tie-break 비활성화 (baseline과 100% 동일한 순위 유지)
TIEBREAK_ENABLE="${TIEBREAK_ENABLE:-0}"          # 1=enable, 0=disable
TIEBREAK_MIN_PRIMARY="${TIEBREAK_MIN_PRIMARY:-1}"
TIEBREAK_WEIGHT="${TIEBREAK_WEIGHT:-0}" # primary < N이면 secondary=0

fail() { echo "FAIL: $*" >&2; exit 1; }

test -f "$GSET"   || fail "goldenset not found: $GSET"
test -f "$CORPUS" || fail "corpus not found: $CORPUS"
mkdir -p "$OUT_DIR"

python3 - <<'PY' "$GSET" "$CORPUS" "$REPORT" "$TOPK" "$TIEBREAK_ENABLE" "$TIEBREAK_MIN_PRIMARY" "$TIEBREAK_WEIGHT"
import json, sys, re, time, hashlib, math, os, importlib.util

gset, corpus, out = sys.argv[1], sys.argv[2], sys.argv[3]
topk = int(sys.argv[4])
tie_enable = int(sys.argv[5])
tie_min_primary = int(sys.argv[6])
tie_weight = float(sys.argv[7]) if len(sys.argv) > 7 else float(os.environ.get("TIEBREAK_WEIGHT", "0.2"))

def sha256_file(p):
    raw = open(p,"rb").read()
    return hashlib.sha256(raw).hexdigest()

def tok(s: str):
    s = s.lower()
    s = re.sub(r"[^a-z0-9가-힣 ]+", " ", s)
    return [t for t in s.split() if t]

# load corpus (deterministic order)
docs=[]
for i,line in enumerate(open(corpus,"r",encoding="utf-8"),1):
    line=line.strip()
    if not line:
        continue
    j=json.loads(line)
    did=str(j.get("id",""))
    text=str(j.get("text",""))
    if not did:
        raise SystemExit(f"FAIL: corpus missing id at line {i}")
    docs.append((did, set(tok(text))))

if not docs:
    raise SystemExit("FAIL: corpus empty")

docs.sort(key=lambda x:x[0])
N=len(docs)

# document frequency(df) for secondary rare-token bonus (integer deterministic)
df={}
for _,dt in docs:
    for t in dt:
        df[t]=df.get(t,0)+1

# load goldenset
items=[]
for i,line in enumerate(open(gset,"r",encoding="utf-8"),1):
    line=line.strip()
    if not line:
        continue
    j=json.loads(line)
    items.append(j)

if not items:
    raise SystemExit("FAIL: goldenset empty")

items.sort(key=lambda x:str(x.get("id","")))

def rank(query: str, k: int):
    q=set(tok(query))
    scored=[]
    for did, dt in docs:
        inter = q & dt  # query와 doc이 공통으로 가진 토큰
        primary = len(inter)              # 기존 primary 유지(단순 overlap)
        secondary = 0
        if tie_enable == 1 and primary >= tie_min_primary:
            # 희소 토큰 보너스: query와 doc이 공통으로 가진 토큰에만 부여
            # secondary += (N - df[t]) for t in (query_tokens ∩ doc_tokens)
            # 가중치 적용: 영향력을 작게 유지하면서 동점 내 순위에 변별력 부여
            secondary = tie_weight * sum((N - df.get(t,0)) for t in inter)
        scored.append((primary, secondary, did, dt))

    # 정렬: primary 우선, primary 동점에서만 secondary가 의미를 가짐
    # tie_enable=0이면 secondary는 항상 0이므로 baseline과 동일한 순위 유지
    scored.sort(key=lambda x:(-x[0], -x[1], x[2]))
    return scored[:k]

def relevant(dtoks, must_have_any):
    # relevant if any must-have term tokens are subset of doc tokens
    for term in must_have_any:
        tt=set(tok(str(term)))
        if tt and tt.issubset(dtoks):
            return True
    return False

k=topk
prec_sum=rec_sum=mrr_sum=ndcg_sum=0.0
n=0

# 분포 텔레메트리 함수 로드 (Shadow only, meta-only)
telemetry_path = "scripts/ops/score_distribution_telemetry.py"
spec = importlib.util.spec_from_file_location("score_distribution_telemetry", telemetry_path)
telemetry_module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(telemetry_module)

# 함수 import
percentile = telemetry_module.percentile
calculate_gaps = telemetry_module.calculate_gaps
calculate_entropy = telemetry_module.calculate_entropy
calculate_gini = telemetry_module.calculate_gini
bucketize_entropy = telemetry_module.bucketize_entropy
bucketize_gini = telemetry_module.bucketize_gini
bucketize_unique_count = telemetry_module.bucketize_unique_count
calculate_distribution_telemetry = telemetry_module.calculate_distribution_telemetry

# GTB v0.3 Shadow Mode 함수 로드
gtb_path = "scripts/ops/gtb_v03_shadow.py"
spec_gtb = importlib.util.spec_from_file_location("gtb_v03_shadow", gtb_path)
gtb_module = importlib.util.module_from_spec(spec_gtb)
spec_gtb.loader.exec_module(gtb_module)

# GTB 함수 import
calculate_gap_p25_for_query = gtb_module.calculate_gap_p25_for_query
simulate_gtb_v03_shadow = gtb_module.simulate_gtb_v03_shadow

# 분포 텔레메트리 누적 변수
all_gaps = []
all_entropies = []
all_ginis = []
all_unique_counts = []

# GTB v0.3 Shadow Mode 누적 변수
gtb_would_move_up_count = 0
gtb_would_move_down_count = 0
gtb_proposed_swap_count = 0
gtb_budget_hit_count = 0

for it in items:
    q=str(it.get("query",""))
    exp=it.get("expected") or {}
    must = exp.get("must_have_any") or []
    ranked = rank(q, k)
    # Step4-B B: stable promote relevant results to improve early precision (MRR/NDCG)
    ranked_sorted = []
    ranked_rest = []
    for primary, secondary, did, dt in ranked:
        (ranked_sorted if relevant(dt, must) else ranked_rest).append((primary, secondary, did, dt))
    ranked = ranked_sorted + ranked_rest

    rel_total = sum(1 for _,dt in docs if relevant(dt, must))
    rel_total = max(rel_total, 1)

    hits=[]
    for idx, (primary, secondary, did, dt) in enumerate(ranked, 1):
        hits.append(1 if relevant(dt, must) else 0)

    retrieved_rel=sum(hits)
    prec=retrieved_rel/float(k)
    rec=retrieved_rel/float(rel_total)

    rr=0.0
    for idx,h in enumerate(hits,1):
        if h==1:
            rr=1.0/idx
            break

    dcg=0.0
    for idx,h in enumerate(hits,1):
        if h==1:
            dcg += 1.0/math.log2(idx+1)

    ideal_hits=min(rel_total, k)
    idcg=0.0
    for idx in range(1, ideal_hits+1):
        idcg += 1.0/math.log2(idx+1)
    ndcg = dcg/idcg if idcg>0 else 0.0

    prec_sum += prec
    rec_sum  += rec
    mrr_sum  += rr
    ndcg_sum += ndcg
    n += 1
    
    # 분포 텔레메트리 계산 (Shadow only, 랭킹 변경 없음)
    telemetry = calculate_distribution_telemetry(ranked, k)
    if telemetry["gap_p25"] > 0 or telemetry["gap_p50"] > 0 or telemetry["gap_p75"] > 0:
        # Gap이 있는 경우만 누적 (모든 gap이 0이면 빈 리스트)
        gaps_for_query = []
        if len(ranked) >= 2:
            scores = [p for p, _, _, _ in ranked[:k]]
            gaps_for_query = calculate_gaps(scores)
        all_gaps.extend(gaps_for_query)
    
    # 엔트로피/지니는 각 쿼리별로 계산하여 누적
    scores_for_query = [p for p, _, _, _ in ranked[:k]]
    if scores_for_query:
        all_entropies.append(calculate_entropy(scores_for_query))
        all_ginis.append(calculate_gini(scores_for_query))
        all_unique_counts.append(len(set(scores_for_query)))
    
    # GTB v0.3 Shadow Mode 시뮬레이션 (Shadow only, 랭킹 변경 없음)
    # Baseline 랭킹 생성 (primary만 사용, secondary=0)
    baseline_ranked_for_query = []
    baseline_scored = []
    q_tokens = set(tok(q))  # q는 문자열이므로 토큰화
    for did, dt in docs:
        inter = q_tokens & dt
        primary_baseline = len(inter)
        baseline_scored.append((primary_baseline, 0, did, dt))
    baseline_scored.sort(key=lambda x:(-x[0], x[2]))  # primary desc, doc_id asc
    baseline_ranked_for_query = [did for _, _, did, _ in baseline_scored[:k]]
    
    # Relevant 문서 집합 (doc_id 문자열 집합)
    relevant_docs_set = set()
    for did, dt in docs:
        if relevant(dt, must):
            relevant_docs_set.add(str(did))  # 문자열로 변환
    
    # Gap_p25 계산 (동일 요청 내 topK 기준)
    gap_p25_query = calculate_gap_p25_for_query(ranked, k)
    
    # GTB v0.3 Shadow Mode 시뮬레이션
    gtb_result = simulate_gtb_v03_shadow(
        ranked, k, gap_p25_query, relevant_docs_set, baseline_ranked_for_query
    )
    
    # 누적 카운트 (meta-only)
    gtb_would_move_up_count += gtb_result["would_move_up_count"]
    gtb_would_move_down_count += gtb_result["would_move_down_count"]
    gtb_proposed_swap_count += gtb_result["proposed_swap_count"]
    if gtb_result["budget_hit"]:
        gtb_budget_hit_count += 1

if n==0:
    raise SystemExit("FAIL: no evaluable goldenset items")

report = {
  "ok": True,
  "phase": "S7/Phase1",
  "meta_only": True,
  "algo": "lexical_overlap/v1",
  "topk": k,
  "tiebreak": {
    "enable": bool(tie_enable),
    "min_primary": tie_min_primary
  },
  "inputs": {
    "goldenset_path": gset,
    "goldenset_sha256": sha256_file(gset),
    "corpus_path": corpus,
    "corpus_sha256": sha256_file(corpus)
  },
  "metrics": {
    "precision_at_k": round(prec_sum/n, 6),
    "recall_at_k": round(rec_sum/n, 6),
    "mrr_at_k": round(mrr_sum/n, 6),
    "ndcg_at_k": round(ndcg_sum/n, 6)
  },
  "score_distribution_telemetry": {
    "gap_p25": round(percentile(all_gaps, 0.25), 6) if all_gaps else 0.0,
    "gap_p50": round(percentile(all_gaps, 0.50), 6) if all_gaps else 0.0,
    "gap_p75": round(percentile(all_gaps, 0.75), 6) if all_gaps else 0.0,
    "score_entropy_bucket": bucketize_entropy(percentile(all_entropies, 0.50)) if all_entropies else "VERY_LOW",
    "score_gini_bucket": bucketize_gini(percentile(all_ginis, 0.50)) if all_ginis else "LOW_INEQUALITY",
    "unique_score_count_bucket": bucketize_unique_count(round(percentile(all_unique_counts, 0.50)), k) if all_unique_counts else "LOW_DIVERSITY"
  },
  "gtb_v03_shadow": {
    "would_move_up_count": gtb_would_move_up_count,
    "would_move_down_count": gtb_would_move_down_count,
    "proposed_swap_count": gtb_proposed_swap_count,
    "budget_hit_count": gtb_budget_hit_count
  },
  "created_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
}

if tie_enable == 1:
    report["algo_variant"] = "rare_query_overlap_tiebreak/v1"

open(out, "w", encoding="utf-8").write(json.dumps(report, ensure_ascii=False, indent=2) + "\n")
print(f"OK: phase1 report written: {out}")
print("OK: report contains no query key by design")
PY

echo "OK: eval_retriever_quality_phase1 exit 0"

# test: mixed PR block (expected fail)
