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

fail() { echo "FAIL: $*" >&2; exit 1; }

test -f "$GSET"   || fail "goldenset not found: $GSET"
test -f "$CORPUS" || fail "corpus not found: $CORPUS"
mkdir -p "$OUT_DIR"

python3 - <<'PY' "$GSET" "$CORPUS" "$REPORT" "$TOPK"
import json, sys, re, time, hashlib, math

gset, corpus, out, topk = sys.argv[1], sys.argv[2], sys.argv[3], int(sys.argv[4])

# algo 문자열은 Step2 호환성 유지를 위해 변경하지 않음(정본)
ALGO = "lexical_overlap/v1"
ALGO_VARIANT = "weighted_stopwords_dfboost/v1"

def sha256_file(p):
    raw = open(p,"rb").read()
    return hashlib.sha256(raw).hexdigest()

STOP = {
  # ko stopwords (minimal)
  "은","는","이","가","을","를","의","에","에서","으로","로","과","와","및","또는","그리고","또","하다",
  # en stopwords (minimal)
  "the","a","an","and","or","to","of","in","on","for","with","is","are"
}

CORE = {
  # core tokens that should be boosted deterministically
  "always","on","meta","only","baseline","regression","proof","latest","gate","verify","destructive","anchor","integrity","healthz","sha","ci","phase0","phase1",
  "s7","dod","doda"
}

def tok(s: str):
    s = s.lower()
    s = re.sub(r"[^a-z0-9가-힣 ]+", " ", s)
    parts = [t for t in s.split() if t]
    out=[]
    for t in parts:
        if t in STOP:
            continue
        # 1글자 한글 토큰은 노이즈가 많아 기본 제외(결정적)
        if len(t) == 1 and re.match(r"[가-힣]", t):
            continue
        out.append(t)
    return out

# load corpus (deterministic order)
docs=[]
for i,line in enumerate(open(corpus,"r",encoding="utf-8"),1):
    line=line.strip()
    if not line: 
        continue
    j=json.loads(line)
    did=str(j.get("id"))
    text=str(j.get("text",""))  # 입력 텍스트는 평가 내부에서만 사용(출력 금지)
    dt=set(tok(text))
    docs.append((did, dt))

if not docs:
    raise SystemExit("FAIL: corpus empty")

docs.sort(key=lambda x:x[0])

# document frequency for df-boost (integer weights, cross-platform stable)
N=len(docs)
df={}
for _,dt in docs:
    for t in dt:
        df[t]=df.get(t,0)+1

def w(token: str) -> int:
    # rare token => bigger weight, integer deterministic
    return 1 + (N - df.get(token, 0))

def boost(token: str) -> int:
    return 2 if token in CORE else 1

def rank(query: str, k: int):
    qt=set(tok(query))
    scored=[]
    for did, dt in docs:
        inter = qt & dt
        score = 0
        for t in inter:
            score += w(t) * boost(t)
        scored.append((score, did, dt))
    scored.sort(key=lambda x:(-x[0], x[1]))
    return scored[:k]

def relevant(dtoks, must_have_any):
    for term in must_have_any:
        tt=set(tok(str(term)))
        if tt and tt.issubset(dtoks):
            return True
    return False

# load goldenset
items=[]
for i,line in enumerate(open(gset,"r",encoding="utf-8"),1):
    line=line.strip()
    if not line:
        continue
    items.append(json.loads(line))

if not items:
    raise SystemExit("FAIL: goldenset empty")

items.sort(key=lambda x:str(x.get("id","")))

k=topk
prec_sum=rec_sum=mrr_sum=ndcg_sum=0.0
n=0

for it in items:
    must = (it.get("expected") or {}).get("must_have_any") or []
    ranked = rank(str(it.get("query","")), k)

    rel_total = sum(1 for _,dt in docs if relevant(dt, must))
    rel_total = max(rel_total, 1)

    hits=[]
    for idx, (_, did, dt) in enumerate(ranked, 1):
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
  "algo": ALGO,
  "algo_variant": ALGO_VARIANT,
  "topk": k,
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

open(out,"w",encoding="utf-8").write(json.dumps(report, ensure_ascii=False, indent=2) + "\n")
print(f"OK: phase1 report written: {out}")
print("OK: report contains no query key by design")
PY

echo "OK: eval_retriever_quality_phase1 exit 0"
