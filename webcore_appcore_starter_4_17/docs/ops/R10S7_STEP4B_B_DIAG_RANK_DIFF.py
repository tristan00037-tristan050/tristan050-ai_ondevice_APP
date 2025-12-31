import json, re, os, math
from pathlib import Path
from collections import Counter

ROOT = Path(__file__).resolve().parent.parent.parent
CORPUS = ROOT / "docs/ops/r10-s7-retriever-corpus.jsonl"
GSET   = ROOT / "docs/ops/r10-s7-retriever-goldenset.jsonl"
OUT    = ROOT / "docs/ops/r10-s7-step4b-b-rank-diff.json"

TOPK = 5
TIE_MIN_PRIMARY = 2
TIE_WEIGHT = float(os.environ.get("TIEBREAK_WEIGHT", "0.2"))

def tok(s: str):
    s = s.lower()
    s = re.sub(r"[^a-z0-9가-힣 ]+", " ", s)
    return [t for t in s.split() if t]

def load_docs():
    docs=[]
    with CORPUS.open("r", encoding="utf-8") as f:
        for line in f:
            line=line.strip()
            if not line: continue
            j=json.loads(line)
            did=str(j.get("id",""))
            text=str(j.get("text",""))
            if not did: continue
            docs.append((did, set(tok(text))))
    docs.sort(key=lambda x:x[0])
    return docs

def load_items():
    items=[]
    with GSET.open("r", encoding="utf-8") as f:
        for line in f:
            line=line.strip()
            if not line: continue
            items.append(json.loads(line))
    return items

def build_df(docs):
    df=Counter()
    for _,dt in docs:
        for t in dt:
            df[t]+=1
    return df

def rank(query: str, docs, df, tie_enable: int):
    q=set(tok(query))
    scored=[]
    N=len(docs)
    for did,dt in docs:
        inter = q & dt
        primary = len(inter)
        secondary = 0.0
        if tie_enable==1 and primary>=TIE_MIN_PRIMARY:
            # eval_retriever_quality_phase1.sh와 완전히 동일한 계산식 (SSOT)
            # 희소 토큰 우선 강화: query의 희소 토큰 상위 3개만 사용
            qtoks = list(q)
            qtoks.sort(key=lambda t: df.get(t, 0))  # 희소 토큰 우선 (df 오름차순)
            rare = qtoks[:3]  # 상위 3개 희소 토큰만 사용
            # 그 토큰이 문서에 포함되면 가점
            secondary = TIE_WEIGHT * sum((N - df.get(t,0)) for t in rare if t in dt)
        scored.append((primary, secondary, did))
    scored.sort(key=lambda x:(-x[0], -x[1], x[2]))
    return [did for _,_,did in scored[:TOPK]]

def main():
    if not CORPUS.exists(): raise SystemExit(f"FAIL: missing {CORPUS}")
    if not GSET.exists(): raise SystemExit(f"FAIL: missing {GSET}")

    docs = load_docs()
    items = load_items()
    df = build_df(docs)

    changed = 0
    total = len(items)
    examples = []
    tie_groups_checked = 0
    tie_groups_secondary_unique = []

    for it in items:
        q=str(it.get("query",""))
        r0 = rank(q, docs, df, 0)
        r1 = rank(q, docs, df, 1)
        if r0 != r1:
            changed += 1
            if len(examples) < 10:
                examples.append({"query": q, "rank0": r0, "rank1": r1})
        
        # 동점 그룹 내 secondary 변별력 확인
        q_set = set(tok(q))
        primaries = [len(q_set & dt) for _, dt in docs]
        mx = max(primaries) if primaries else 0
        if mx > 0:
            # primary==mx인 문서들의 secondary 값 수집
            tie_secondaries = []
            for idx, (did, dt) in enumerate(docs):
                inter = q_set & dt
                primary = len(inter)
                if primary == mx:
                    secondary = 0.0
                    if primary >= TIE_MIN_PRIMARY:
                        # eval과 동일한 희소 토큰 우선 로직
                        qtoks = list(q_set)
                        qtoks.sort(key=lambda t: df.get(t, 0))
                        rare = qtoks[:3]
                        secondary = TIE_WEIGHT * sum((len(docs) - df.get(t,0)) for t in rare if t in dt)
                    tie_secondaries.append(secondary)
            
            if len(tie_secondaries) >= 2:  # 동점 그룹이 2개 이상
                tie_groups_checked += 1
                unique_count = len(set(tie_secondaries))
                tie_groups_secondary_unique.append(unique_count)

    out = {
        "topk": TOPK,
        "tie_min_primary": TIE_MIN_PRIMARY,
        "tie_weight": TIE_WEIGHT,
        "total_queries": total,
        "queries_rank_changed": changed,
        "ratio": (changed/total if total else 0.0),
        "tie_groups_checked": tie_groups_checked,
        "tie_groups_secondary_unique": {
            "counts": tie_groups_secondary_unique,
            "unique_1_count": sum(1 for x in tie_groups_secondary_unique if x == 1),
            "unique_gt1_count": sum(1 for x in tie_groups_secondary_unique if x > 1),
        },
        "examples": examples,
    }
    OUT.write_text(json.dumps(out, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print("OK: wrote", str(OUT))
    print(json.dumps(out, ensure_ascii=False, indent=2))

if __name__ == "__main__":
    main()

