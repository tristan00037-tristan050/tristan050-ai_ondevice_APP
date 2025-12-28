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

ALGO = "lexical_overlap/v1"

def sha256_file(p):
    raw = open(p,"rb").read()
    return hashlib.sha256(raw).hexdigest()

def tok(s: str):
    s = s.lower()
    s = re.sub(r"[^a-z0-9가-힣 ]+", " ", s)
    return [t for t in s.split() if t]

# load corpus
docs = []
for i, line in enumerate(open(corpus, "r", encoding="utf-8"), 1):
    line=line.strip()
    if not line: 
        continue
    j=json.loads(line)
    did = str(j["id"])
    dtoks = set(tok(str(j["text"])))
    docs.append((did, dtoks))

if not docs:
    raise SystemExit("FAIL: corpus empty")

# stable order not required for ranking (we sort by id later), but keep deterministic anyway
docs.sort(key=lambda x: x[0])

# load goldenset
items = []
for i, line in enumerate(open(gset, "r", encoding="utf-8"), 1):
    line=line.strip()
    if not line:
        continue
    j=json.loads(line)
    items.append(j)

if not items:
    raise SystemExit("FAIL: goldenset empty")

items.sort(key=lambda x: str(x.get("id","")))

def relevant(dtoks, must_have_any):
    # relevant if any "must-have phrase" tokens are fully present in doc tokens
    for term in must_have_any:
        tt=set(tok(str(term)))
        if tt and tt.issubset(dtoks):
            return True
    return False

def rank(query: str, k: int):
    q=set(tok(query))
    scored=[]
    for did, dtoks in docs:
        score=len(q & dtoks)
        scored.append((score, did, dtoks))
    scored.sort(key=lambda x: (-x[0], x[1]))
    return scored[:k]

k = topk
prec_sum=rec_sum=mrr_sum=ndcg_sum=0.0
n=0

for it in items:
    must = (it.get("expected") or {}).get("must_have_any") or []
    ranked = rank(str(it.get("query","")), k)
    rel_total = sum(1 for _,dtoks in docs if relevant(dtoks, must))
    rel_total = max(rel_total, 1)

    hits=[]
    for idx, (_, did, dtoks) in enumerate(ranked, 1):
        hits.append(1 if relevant(dtoks, must) else 0)

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

    ideal_hits = min(rel_total, k)
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

open(out, "w", encoding="utf-8").write(json.dumps(report, ensure_ascii=False, indent=2) + "\n")
print(f"OK: phase1 report written: {out}")
PY

echo "OK: eval_retriever_quality_phase1 exit 0"

