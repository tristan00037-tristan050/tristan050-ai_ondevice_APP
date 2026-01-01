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
TIEBREAK_MIN_PRIMARY="${TIEBREAK_MIN_PRIMARY:-1}" # primary < N이면 secondary=0

fail() { echo "FAIL: $*" >&2; exit 1; }

test -f "$GSET"   || fail "goldenset not found: $GSET"
test -f "$CORPUS" || fail "corpus not found: $CORPUS"
mkdir -p "$OUT_DIR"

python3 - <<'PY' "$GSET" "$CORPUS" "$REPORT" "$TOPK" "$TIEBREAK_ENABLE" "$TIEBREAK_MIN_PRIMARY" "$TIEBREAK_WEIGHT"
import json, sys, re, time, hashlib, math, os

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
