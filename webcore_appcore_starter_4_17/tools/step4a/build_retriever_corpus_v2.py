import os, json, re, hashlib
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "docs/ops/r10-s7-retriever-corpus.jsonl"

MAX_BODY_CHARS = int(os.environ.get("CORPUS_BODY_CHARS", "4000"))
SCAN_HEADER_LINES = 80

# PII sanitization patterns (meta-only policy)
PII_RE = [
    # URL
    (re.compile(r"https?://\S+|www\.\S+", re.IGNORECASE), "[URL]"),
    # Email
    (re.compile(r"\b[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}\b", re.IGNORECASE), "[EMAIL]"),
    # IPv4
    (re.compile(r"\b(?:\d{1,3}\.){3}\d{1,3}\b"), "[IP]"),
    # Common secret assignments (KEY=..., TOKEN:..., etc.)
    (re.compile(r"\b(AWS|API|ACCESS|SECRET|TOKEN|KEY|PASSWORD|PASS|PWD|BEARER|AUTH)[A-Z0-9_ -]{0,30}\s*[:=]\s*\S+", re.IGNORECASE), "[SECRET]"),
]

def sanitize_text(s: str) -> str:
    """Replace suspicious patterns with neutral placeholders (meta-only policy)"""
    out = s
    for rx, rep in PII_RE:
        out = rx.sub(rep, out)
    return out

def read_text(p: Path) -> str:
    return p.read_text(encoding="utf-8", errors="replace")

def md_headers(s: str):
    hs=[]
    for line in s.splitlines()[:SCAN_HEADER_LINES]:
        if re.match(r"^#{1,3}\s+", line):
            hs.append(re.sub(r"^#{1,3}\s+", "", line).strip())
    return hs

def make_id(rel: str) -> str:
    return hashlib.sha1(rel.encode("utf-8")).hexdigest()[:12]

def main():
    # Source: repo docs (md/txt). This is Step4-A only.
    candidates=[]
    for root, _, files in os.walk(ROOT):
        root = str(root)
        if "/node_modules/" in root or "/dist/" in root or "/.git/" in root:
            continue
        for f in files:
            ext = os.path.splitext(f)[1].lower()
            if ext not in (".md", ".txt"):
                continue
            p = Path(root) / f
            rel = str(p.relative_to(ROOT))
            candidates.append((rel, p))

    candidates.sort(key=lambda x:x[0])

    OUT.parent.mkdir(parents=True, exist_ok=True)
    out_n = 0

    with OUT.open("w", encoding="utf-8") as w:
        for rel, p in candidates:
            raw = read_text(p)
            title = os.path.basename(rel)

            headers = md_headers(raw) if rel.lower().endswith(".md") else []
            body = (raw[:MAX_BODY_CHARS]).strip()

            combined = " ".join([title] + headers + [body]).strip()
            if not combined:
                continue

            # PII sanitization (meta-only policy)
            combined = sanitize_text(combined)

            rec = {"id": make_id(rel), "text": combined}
            w.write(json.dumps(rec, ensure_ascii=False) + "\n")
            out_n += 1

    # meta-only output
    print(json.dumps({
        "ok": True,
        "out": str(OUT),
        "doc_count": out_n,
        "body_chars": MAX_BODY_CHARS,
        "header_lines": SCAN_HEADER_LINES,
    }, ensure_ascii=False))

if __name__ == "__main__":
    main()
