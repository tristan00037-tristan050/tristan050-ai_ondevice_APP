import json, re
from collections import Counter
from pathlib import Path

# 현재 파일: webcore_appcore_starter_4_17/docs/ops/R10S7_STEP4B_B_DIAG_PRIMARY_TIES.py
# ROOT는 webcore_appcore_starter_4_17 디렉토리
ROOT = Path(__file__).resolve().parent.parent.parent
CORPUS = ROOT / "docs/ops/r10-s7-retriever-corpus.jsonl"
GSET   = ROOT / "docs/ops/r10-s7-retriever-goldenset.jsonl"
OUT    = ROOT / "docs/ops/r10-s7-step4b-b-primary-tie-stats.json"

def tok(s: str):
    s = s.lower()
    s = re.sub(r"[^a-z0-9가-힣 ]+", " ", s)
    return [t for t in s.split() if t]

def load_docs():
    docs = []
    with CORPUS.open("r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            j = json.loads(line)
            did = str(j.get("id", ""))
            text = str(j.get("text", ""))
            if not did:
                continue
            docs.append((did, set(tok(text))))
    docs.sort(key=lambda x: x[0])
    return docs

def load_items():
    items = []
    with GSET.open("r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            items.append(json.loads(line))
    return items

def main():
    if not CORPUS.exists():
        raise SystemExit(f"FAIL: missing corpus: {CORPUS}")
    if not GSET.exists():
        raise SystemExit(f"FAIL: missing goldenset: {GSET}")

    docs = load_docs()
    items = load_items()

    tie_top = 0
    tie_any = 0
    n = len(items)

    sample = []
    for it in items[:10]:
        q = set(tok(str(it.get("query", ""))))
        prim = [len(q & dt) for _, dt in docs]
        c = Counter(prim)
        mx = max(prim) if prim else 0
        sample.append({"max_primary": mx, "top_tie": int(c[mx]) if prim else 0})

    for it in items:
        q = set(tok(str(it.get("query", ""))))
        prim = [len(q & dt) for _, dt in docs]
        c = Counter(prim)
        mx = max(prim) if prim else 0
        if mx > 0 and c[mx] >= 2:
            tie_top += 1
        if any(k > 0 and v >= 2 for k, v in c.items()):
            tie_any += 1

    out = {
        "n_queries": n,
        "queries_with_top_primary_tie": tie_top,
        "queries_with_any_primary_tie": tie_any,
        "sample_first10": sample,
    }
    OUT.write_text(json.dumps(out, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print("OK: wrote", str(OUT))
    print(json.dumps(out, ensure_ascii=False, indent=2))

if __name__ == "__main__":
    main()

