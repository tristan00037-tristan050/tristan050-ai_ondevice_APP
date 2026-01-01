import json, re
from pathlib import Path
from collections import Counter, defaultdict

# 이 스크립트는 webcore_appcore_starter_4_17/docs/ops/ 아래에 있다고 가정한다.
# 따라서 프로젝트 루트는 parents[2]가 맞다. (중복 폴더 append 금지)
ROOT = Path(__file__).resolve().parents[2]
CORPUS = ROOT / "docs/ops/r10-s7-retriever-corpus.jsonl"
GSET   = ROOT / "docs/ops/r10-s7-retriever-goldenset.jsonl"
OUT    = ROOT / "docs/ops/r10-s7-step4a-hitless-token-coverage.json"

def tok(s: str):
    s = (s or "").lower()
    s = re.sub(r"[^a-z0-9가-힣 ]+", " ", s)
    return [t for t in s.split() if t]

def main():
    if not CORPUS.exists():
        raise SystemExit(f"FAIL: missing corpus: {CORPUS}")
    if not GSET.exists():
        raise SystemExit(f"FAIL: missing goldenset: {GSET}")

    # corpus token df (text only, schema가 text만 보장된다는 가정 하에 시작)
    df = Counter()
    doc_n = 0
    for line in CORPUS.open("r", encoding="utf-8"):
        line = line.strip()
        if not line:
            continue
        j = json.loads(line)
        text = str(j.get("text", ""))
        dt = set(tok(text))
        for t in dt:
            df[t] += 1
        doc_n += 1

    items = [json.loads(l) for l in GSET.open("r", encoding="utf-8") if l.strip()]
    total = len(items)

    agg = defaultdict(int)
    miss_counts = []

    for it in items:
        exp = it.get("expected") or {}
        must = exp.get("must_have_any") or []

        must_tokens = []
        for term in must:
            must_tokens.extend(tok(str(term)))
        must_set = set(must_tokens)

        missing = [t for t in must_set if df.get(t, 0) == 0]
        miss_counts.append(int(len(missing)))

        if len(must_set) == 0:
            agg["queries_with_empty_must"] += 1
        elif len(missing) == len(must_set):
            agg["queries_all_must_missing"] += 1
        elif len(missing) > 0:
            agg["queries_some_must_missing"] += 1
        else:
            agg["queries_all_must_present"] += 1

    out = {
        "doc_count": int(doc_n),
        "total_queries": int(total),
        "agg": dict(agg),
        "missing_count_hist": dict(Counter(miss_counts)),
        "note": "Text-only corpus token coverage. No raw tokens are output."
    }

    OUT.write_text(json.dumps(out, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print("OK: wrote", str(OUT))
    print(json.dumps(out, ensure_ascii=False, indent=2))

if __name__ == "__main__":
    main()
