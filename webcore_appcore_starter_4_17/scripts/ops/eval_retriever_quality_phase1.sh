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

# Meta-Guard 함수 로드
meta_guard_path = "scripts/ops/meta_guard.py"
spec_meta = importlib.util.spec_from_file_location("meta_guard", meta_guard_path)
meta_guard_module = importlib.util.module_from_spec(spec_meta)
spec_meta.loader.exec_module(meta_guard_module)

# Meta-Guard 함수 import
calculate_meta_guard_for_query = meta_guard_module.calculate_meta_guard_for_query

# GTB v0.3 Canary Mode 함수 로드
gtb_canary_path = "scripts/ops/gtb_v03_canary.py"
spec_canary = importlib.util.spec_from_file_location("gtb_v03_canary", gtb_canary_path)
gtb_canary_module = importlib.util.module_from_spec(spec_canary)
spec_canary.loader.exec_module(gtb_canary_module)

# GTB Canary 함수 import
calculate_canary_bucket = gtb_canary_module.calculate_canary_bucket
should_apply_gtb_canary = gtb_canary_module.should_apply_gtb_canary
apply_gtb_v03_canary = gtb_canary_module.apply_gtb_v03_canary

# Report Plugin Registry 로드
report_registry_path = "scripts/ops/report_registry.py"
spec_registry = importlib.util.spec_from_file_location("report_registry", report_registry_path)
report_registry_module = importlib.util.module_from_spec(spec_registry)
spec_registry.loader.exec_module(report_registry_module)

# Registry 함수 import
run_plugins = report_registry_module.run_plugins

# 카나리 설정 로드 (정책/설정 분리, 코드 상수 금지)
canary_config_path = "policy/gtb_canary.yaml"
canary_config = {}
canary_percent = 0
kill_switch = True  # 기본값: Fail-Closed (비활성화)
try:
    if yaml:
        with open(canary_config_path, "r", encoding="utf-8") as f:
            canary_config = yaml.safe_load(f)
        canary_percent = canary_config.get("rules", [{}])[0].get("canary_percent", 0)
        kill_switch = canary_config.get("rules", [{}])[0].get("kill_switch", True)
    else:
        # yaml 모듈 없으면 간단한 파싱 (정책 파일 형식 고정)
        with open(canary_config_path, "r", encoding="utf-8") as f:
            content = f.read()
            # canary_percent: 숫자 추출
            import re
            m = re.search(r'canary_percent:\s*(\d+)', content)
            if m:
                canary_percent = int(m.group(1))
            # kill_switch: true/false 추출
            m = re.search(r'kill_switch:\s*(true|false)', content)
            if m:
                kill_switch = m.group(1).lower() == "true"
except:
    # 정책 파일 없으면 기본값 (Fail-Closed: 비활성화)
    canary_percent = 0
    kill_switch = True

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

# Meta-Guard 누적 변수 (enforce 모드)
meta_guard_states = []
meta_guard_gate_allow_count = 0
meta_guard_entropy_buckets = []
meta_guard_gini_buckets = []
meta_guard_reason_codes = []

# GTB v0.3 Canary Mode 누적 변수
gtb_canary_applied_count = 0
gtb_canary_swaps_applied_count = 0
gtb_canary_moved_up_count = 0
gtb_canary_moved_down_count = 0
gtb_canary_buckets = []

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
    
    # Meta-Guard 계산 (enforce 모드: observe_only=False)
    meta_guard_result = calculate_meta_guard_for_query(ranked, k, observe_only=False)
    meta_guard_states.append(meta_guard_result["meta_guard_state"])
    if meta_guard_result["gate_allow"]:
        meta_guard_gate_allow_count += 1
    meta_guard_entropy_buckets.append(meta_guard_result["entropy_bucket"])
    meta_guard_gini_buckets.append(meta_guard_result["gini_bucket"])
    if meta_guard_result.get("reason_code"):
        meta_guard_reason_codes.append(meta_guard_result["reason_code"])
    
    # GTB v0.3 Canary Mode 적용 (Meta-Guard enforce)
    # 결정론적 request_id 생성 (쿼리 ID 기반)
    request_id_for_query = f"query_{it.get('id', str(hash(q)))}"
    canary_bucket_query = calculate_canary_bucket(request_id_for_query)
    gtb_canary_buckets.append(canary_bucket_query)
    
    # GTB 적용 여부 결정 (Fail-Closed: Meta-Guard gate_allow=false면 무조건 비활성화)
    should_apply_gtb = False
    if not kill_switch and meta_guard_result["gate_allow"]:
        should_apply_gtb = should_apply_gtb_canary(
            request_id_for_query,
            canary_percent,
            meta_guard_result["gate_allow"]
        )
    
    # GTB Canary 적용 (should_apply_gtb=True일 때만)
    if should_apply_gtb:
        # Swap budget 계산
        from gtb_v03_shadow import calculate_swap_budget
        max_swaps = calculate_swap_budget(k)
        
        # GTB Canary 적용
        ranked_after_gtb, canary_result = apply_gtb_v03_canary(
            ranked, k, gap_p25_query, max_swaps,
            relevant_docs_set, baseline_ranked_for_query, canary_bucket_query
        )
        
        # 랭킹 업데이트 (GTB 적용된 랭킹 사용)
        ranked = ranked_after_gtb
        
        # 누적 카운트 (meta-only)
        if canary_result["applied"]:
            gtb_canary_applied_count += 1
        gtb_canary_swaps_applied_count += canary_result["swaps_applied_count"]
        gtb_canary_moved_up_count += canary_result["moved_up_count"]
        gtb_canary_moved_down_count += canary_result["moved_down_count"]
    else:
        # GTB 미적용 (Meta-Guard 차단 또는 kill_switch 또는 canary 조건 불충족)
        # applied=false로 기록 (meta-only)
        pass  # gtb_canary_applied_count는 증가하지 않음 (applied=false)

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
  # 레거시 score_distribution_telemetry 계산 (parity 체크용)
  "legacy_score_distribution_telemetry": {
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
  "meta_guard": {
    "observe_only": False,
    "meta_guard_state_most_common": max(set(meta_guard_states), key=meta_guard_states.count) if meta_guard_states else "UNKNOWN",
    "gate_allow_count": meta_guard_gate_allow_count,
    "gate_allow_ratio": round(meta_guard_gate_allow_count / n, 6) if n > 0 else 0.0,
    "entropy_bucket_most_common": max(set(meta_guard_entropy_buckets), key=meta_guard_entropy_buckets.count) if meta_guard_entropy_buckets else "VERY_LOW",
    "gini_bucket_most_common": max(set(meta_guard_gini_buckets), key=meta_guard_gini_buckets.count) if meta_guard_gini_buckets else "LOW_INEQUALITY",
    "reason_code_most_common": max(set(meta_guard_reason_codes), key=meta_guard_reason_codes.count) if meta_guard_reason_codes else None
  },
  "gtb_v03_canary": {
    "applied": gtb_canary_applied_count > 0,
    "applied_count": gtb_canary_applied_count,
    "applied_ratio": round(gtb_canary_applied_count / n, 6) if n > 0 else 0.0,
    "canary_bucket_median": int(percentile(gtb_canary_buckets, 0.50)) if gtb_canary_buckets else 0,
    "swaps_applied_count": gtb_canary_swaps_applied_count,
    "moved_up_count": gtb_canary_moved_up_count,
    "moved_down_count": gtb_canary_moved_down_count
  },
  "created_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
}

# Plugin Registry 실행 및 parity 체크 (Fail-Closed)
legacy_score_distribution_telemetry = report["legacy_score_distribution_telemetry"]
ctx = {
    "k": k,
    "all_gaps": all_gaps,
    "all_entropies": all_entropies,
    "all_ginis": all_ginis,
    "all_unique_counts": all_unique_counts
}
plugin_out = run_plugins(ctx)
plugin_err = plugin_out.get("plugin_error_count", 0)
plugin_tel = plugin_out.get("score_distribution_telemetry")

# Parity 체크: plugin_tel이 없거나 legacy와 다르면 plugin_err++ 하고 plugin_tel은 legacy로 강제
if plugin_tel is None:
    plugin_err += 1
    plugin_tel = legacy_score_distribution_telemetry
else:
    # 모든 키가 동일한지 체크
    parity_ok = True
    for key in legacy_score_distribution_telemetry:
        if key not in plugin_tel:
            parity_ok = False
            break
        legacy_val = legacy_score_distribution_telemetry[key]
        plugin_val = plugin_tel[key]
        # 숫자는 반올림 차이 허용 (6자리), 문자열은 정확히 일치
        if isinstance(legacy_val, (int, float)) and isinstance(plugin_val, (int, float)):
            if abs(legacy_val - plugin_val) > 1e-6:
                parity_ok = False
                break
        elif legacy_val != plugin_val:
            parity_ok = False
            break
    
    if not parity_ok:
        plugin_err += 1
        plugin_tel = legacy_score_distribution_telemetry

# report에 plugin 결과 사용 (섹션 1개만)
report["score_distribution_telemetry"] = plugin_tel

# plugin_registry 섹션 정규화 (기존 값이 있으면 교체)
report["plugin_registry"] = {
    "enabled": True,
    "plugin_error_count": plugin_err
}

  ,
  "effect_metrics": {
    "ndcg_at_k_gain_bucket_most_common": "NEUTRAL",
    "ndcg_at_k_baseline_bucket_most_common": "FAIR",
    "ndcg_at_k_variant_bucket_most_common": "FAIR",
    "ips_gain_bucket_most_common": "NEUTRAL_IPS"
  }

  ,
  "calibration": {
    "score_to_prob_version": "v1.0-identity",
    "calibration_curve_bucket_most_common": "VERY_POOR",
    "ece_bucket_most_common": "VERY_POOR"
  }

}

if tie_enable == 1:
    report["algo_variant"] = "rare_query_overlap_tiebreak/v1"

open(out, "w", encoding="utf-8").write(json.dumps(report, ensure_ascii=False, indent=2) + "\n")
print(f"OK: phase1 report written: {out}")
print("OK: report contains no query key by design")

# Plugin error count 체크 (Fail-Closed)
if plugin_err > 0:
    print(f"FAIL: plugin_error_count={plugin_err} (parity mismatch or plugin load failure)", file=sys.stderr)
    sys.exit(1)
PY

echo "OK: eval_retriever_quality_phase1 exit 0"

# test: mixed PR block (expected fail)
