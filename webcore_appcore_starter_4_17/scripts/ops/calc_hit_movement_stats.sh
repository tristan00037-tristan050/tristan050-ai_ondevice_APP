#!/usr/bin/env bash
# Hit movement statistics calculator (meta-only)
# Calculates hit movement between baseline and current rankings
set -euo pipefail

cd "$(git rev-parse --show-toplevel)/webcore_appcore_starter_4_17"

BASELINE="${BASELINE:-docs/ops/r10-s7-retriever-metrics-baseline.json}"
REPORT="${REPORT:-docs/ops/r10-s7-retriever-quality-phase1-report.json}"
GSET="${GSET:-docs/ops/r10-s7-retriever-goldenset.jsonl}"
CORPUS="${CORPUS:-docs/ops/r10-s7-retriever-corpus.jsonl}"

test -f "$BASELINE" || { echo "FAIL: baseline missing: $BASELINE" >&2; exit 1; }
test -f "$REPORT" || { echo "FAIL: phase1 report missing: $REPORT" >&2; exit 1; }
test -f "$GSET" || { echo "FAIL: goldenset missing: $GSET" >&2; exit 1; }
test -f "$CORPUS" || { echo "FAIL: corpus missing: $CORPUS" >&2; exit 1; }

# Calculate hit movement stats (meta-only: numbers only, no PII)
python3 - <<'PY' "$BASELINE" "$REPORT" "$GSET" "$CORPUS"
import json, sys, re, os

baseline_path, report_path, gset_path, corpus_path = sys.argv[1], sys.argv[2], sys.argv[3], sys.argv[4]

def tok(s: str):
    s = s.lower()
    s = re.sub(r"[^a-z0-9가-힣 ]+", " ", s)
    return [t for t in s.split() if t]

def relevant(dtoks, must_have_any):
    for term in must_have_any:
        tt = set(tok(str(term)))
        if tt and tt.issubset(dtoks):
            return True
    return False

# Load corpus
docs = {}
for line in open(corpus_path, "r", encoding="utf-8"):
    line = line.strip()
    if not line:
        continue
    j = json.loads(line)
    did = str(j.get("id", ""))
    text = str(j.get("text", ""))
    if did:
        docs[did] = set(tok(text))

# Load goldenset
queries = []
for line in open(gset_path, "r", encoding="utf-8"):
    line = line.strip()
    if not line:
        continue
    j = json.loads(line)
    queries.append(j)

# Load baseline and report
b = json.load(open(baseline_path, "r", encoding="utf-8"))
r = json.load(open(report_path, "r", encoding="utf-8"))

# Check if inputs match
if r["inputs"]["goldenset_sha256"] != b["inputs"]["goldenset_sha256"]:
    raise SystemExit("FAIL: goldenset sha256 mismatch (cannot compare)")
if r["inputs"]["corpus_sha256"] != b["inputs"]["corpus_sha256"]:
    raise SystemExit("FAIL: corpus sha256 mismatch (cannot compare)")

# For each query, calculate baseline and current rankings
# Since we don't have stored rankings, we need to recompute baseline ranking
# Baseline: primary only, no tie-break
# Current: with tie-break if enabled

topk = int(r.get("topk", 5))
tie_enable = r.get("tiebreak", {}).get("enable", False)

# Build DF for secondary calculation
df = {}
for did, dt in docs.items():
    for t in dt:
        df[t] = df.get(t, 0) + 1
N = len(docs)

def rank_baseline(query: str, k: int):
    """Baseline ranking: primary only, no tie-break"""
    q = set(tok(query))
    scored = []
    for did, dt in docs.items():
        inter = q & dt
        primary = len(inter)
        scored.append((primary, did, dt))
    scored.sort(key=lambda x: (-x[0], x[1]))  # primary desc, doc_id asc
    return [x[1] for x in scored[:k]]

def rank_current(query: str, k: int, tie_enable: bool, tie_min_primary: int, tie_weight: float, tie_eps: float):
    """Current ranking: with tie-break if enabled, using near-tie threshold"""
    q = set(tok(query))
    scored = []
    for did, dt in docs.items():
        inter = q & dt
        primary = len(inter)
        secondary = 0.0
        if tie_enable and primary >= tie_min_primary:
            rare_sum = sum((N - df.get(t, 0)) for t in inter)
            # 문서 길이 신호 추가 (eval_retriever_quality_phase1.sh와 동일)
            doc_len = len(dt)
            doc_len_score = 1.0 / (1.0 + doc_len * 0.05) if doc_len > 0 else 0.0
            # Jaccard similarity 추가 (eval_retriever_quality_phase1.sh와 동일)
            q_size = len(q)
            jaccard = len(inter) / (q_size + len(dt) - len(inter)) if (q_size + len(dt) - len(inter)) > 0 else 0.0
            # overlap ratio 추가 (eval_retriever_quality_phase1.sh와 동일)
            overlap_ratio = len(inter) / q_size if q_size > 0 else 0.0
            # eval_retriever_quality_phase1.sh와 동일한 계산식
            secondary = (tie_weight * 2.0) * rare_sum + 0.2 * doc_len_score + 0.5 * jaccard + 0.4 * overlap_ratio
        scored.append((primary, secondary, did, dt))
    
    # Apply near-tie threshold (same logic as eval_retriever_quality_phase1.sh)
    if tie_enable:
        scored.sort(key=lambda x: (-x[0], x[2]))  # primary desc, doc_id asc
        scored_sorted = []
        i = 0
        while i < len(scored):
            curr_primary = scored[i][0]
            group = [scored[i]]
            j = i + 1
            while j < len(scored) and abs(scored[j][0] - curr_primary) <= tie_eps:
                group.append(scored[j])
                j += 1
            if len(group) > 1:
                group.sort(key=lambda x: (-x[1], x[2]))  # secondary desc, doc_id asc
            scored_sorted.extend(group)
            i = j
        scored = scored_sorted
    else:
        scored.sort(key=lambda x: (-x[0], -x[1], x[2]))
    
    return [x[2] for x in scored[:k]]

# Get tie-break parameters from report
tie_min_primary = r.get("tiebreak", {}).get("min_primary", 1)
# Use environment variable if set, otherwise default to 0.15 (matches ONE_SHOT)
tie_weight = float(os.environ.get("TIEBREAK_WEIGHT", "0.15"))
tie_eps = float(os.environ.get("TIEBREAK_EPS", "0.5"))

q_total = 0
hit_total = 0
hit_moved_up = 0
hit_moved_down = 0
hit_same = 0
hit_missing = 0
first_hit_delta_sum = 0

for it in queries:
    q = str(it.get("query", ""))
    exp = it.get("expected", {})
    must = exp.get("must_have_any", [])
    
    if not q:
        continue
    
    q_total += 1
    
    # Get baseline ranking
    baseline_ranked = rank_baseline(q, topk)
    # Get current ranking
    current_ranked = rank_current(q, topk, tie_enable, tie_min_primary, tie_weight, tie_eps)
    
    # Find first hit in baseline (lowest rank = best position)
    baseline_first_hit_rank = None
    for idx, did in enumerate(baseline_ranked, 1):
        if did in docs and relevant(docs[did], must):
            if baseline_first_hit_rank is None:
                baseline_first_hit_rank = idx
            hit_total += 1
    
    # Find first hit in current (lowest rank = best position)
    current_first_hit_rank = None
    for idx, did in enumerate(current_ranked, 1):
        if did in docs and relevant(docs[did], must):
            if current_first_hit_rank is None:
                current_first_hit_rank = idx
            # Count total hits (including new ones not in baseline)
            if baseline_first_hit_rank is None or did not in baseline_ranked[:baseline_first_hit_rank] if baseline_first_hit_rank else True:
                # Rough check: if baseline had no hit or this doc wasn't in baseline top-k
                pass
            # Always count for HIT_TOTAL
            if baseline_first_hit_rank is None:
                # New hit in query that had no baseline hit
                hit_total += 1
            elif did not in baseline_ranked:
                # New hit not in baseline top-k
                hit_total += 1
    
    # Classify query based on first hit movement (one classification per query)
    if baseline_first_hit_rank is not None:
        # Baseline had at least one hit
        if current_first_hit_rank is not None:
            # Current also has at least one hit
            if current_first_hit_rank < baseline_first_hit_rank:
                hit_moved_up += 1
            elif current_first_hit_rank > baseline_first_hit_rank:
                hit_moved_down += 1
            else:
                hit_same += 1
            # First hit delta
            first_hit_delta_sum += (current_first_hit_rank - baseline_first_hit_rank)
        else:
            # Baseline had hit but current doesn't (in top-k)
            hit_missing += 1
    else:
        # Baseline had no hit - classify as HIT_SAME (no change, still no hit)
        hit_same += 1

# Verify invariant: HIT_MOVED_UP + HIT_MOVED_DOWN + HIT_SAME + HIT_MISSING == Q_TOTAL
# This counts queries that had hits in baseline
hit_query_total = hit_moved_up + hit_moved_down + hit_same + hit_missing
if hit_query_total != q_total:
    print(f"FAIL: invariant violation: HIT_MOVED_UP({hit_moved_up}) + HIT_MOVED_DOWN({hit_moved_down}) + HIT_SAME({hit_same}) + HIT_MISSING({hit_missing}) = {hit_query_total} != Q_TOTAL({q_total})", file=sys.stderr)
    raise SystemExit(1)

# Output meta-only stats
print(f"Q_TOTAL={q_total}")
print(f"HIT_TOTAL={hit_total}")
print(f"HIT_MOVED_UP={hit_moved_up}")
print(f"HIT_MOVED_DOWN={hit_moved_down}")
print(f"HIT_SAME={hit_same}")
print(f"HIT_MISSING={hit_missing}")
print(f"FIRST_HIT_DELTA_SUM={first_hit_delta_sum}")
PY

echo "OK: hit movement stats calculated (meta-only)"
