#!/usr/bin/env bash
set -euo pipefail
cd "$(git rev-parse --show-toplevel)/webcore_appcore_starter_4_17"

DEBUG="${META_ONLY_DEBUG:-0}"

fail() { echo "FAIL: $*" >&2; exit 1; }

# 입력(텍스트 포함 가능) → meta-only 스캔 제외 대상(정본 규칙)
EXCLUDES=(
  "docs/ops/r10-s7-retriever-corpus.jsonl"
  "docs/ops/r10-s7-retriever-goldenset.jsonl"
  "docs/ops/r10-s7-retriever-goldenset.schema.json"
)

# 출력(반드시 meta-only) → 스캔 대상
shopt -s nullglob
FILES=(
  docs/ops/r10-s7-retriever-quality-phase0-report.json
  docs/ops/r10-s7-retriever-quality-phase1-report.json
  docs/ops/r10-s7-retriever-metrics-baseline.json
  docs/ops/r10-s7-retriever-quality-proof.latest
  docs/ops/r10-s7-retriever-regression-proof.latest
  docs/ops/r10-s7-retriever-quality-proof-*.log
  docs/ops/r10-s7-retriever-regression-proof-*.log
)
shopt -u nullglob

# DEBUG: exclude/scan 목록을 "출력으로" 증명(레포 증빙용)
if [[ "$DEBUG" == "1" ]]; then
  echo "META_ONLY_DEBUG=1"
  for x in "${EXCLUDES[@]}"; do
    if [[ -f "$x" ]]; then
      echo "META_ONLY_DEBUG: exclude $x"
    fi
  done
fi

# 스캔 대상이 0이면 초기 단계에서 정상 PASS(결정적)
if [[ "${#FILES[@]}" -eq 0 ]]; then
  echo "OK: meta-only verifier (no S7 retriever artifacts found; nothing to scan)"
  exit 0
fi

# 정렬(결정적 출력)
IFS=$'\n' FILES_SORTED=($(printf "%s\n" "${FILES[@]}" | sort))
unset IFS

if [[ "$DEBUG" == "1" ]]; then
  for f in "${FILES_SORTED[@]}"; do
    echo "META_ONLY_DEBUG: scan $f"
  done
fi

python3 - <<'PY' "${FILES_SORTED[@]}"
import json, re, sys, pathlib

files = sys.argv[1:]

# outputs에는 절대로 포함되면 안 되는 키(원문/페이로드 계열)
FORBIDDEN_KEYS = {
  "query","queries","text","content","payload","raw","prompt","completion","message","messages","chunk","chunks","document","documents","passage","passages"
}

# PII/secret 기본 패턴(출력물에서 이런 패턴이 나오면 즉시 FAIL)
PII_PATTERNS = [
  ("EMAIL", re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}")),
  ("URL", re.compile(r"\b(?:https?|wss?)://", re.IGNORECASE)),
  ("IPV4", re.compile(r"\b(?:\d{1,3}\.){3}\d{1,3}\b")),
  ("RRN", re.compile(r"\b\d{6}-\d{7}\b")),
  ("AWS_ACCESS_KEY", re.compile(r"\b(?:AKIA|ASIA)[0-9A-Z]{16}\b")),
  ("GITHUB_TOKEN", re.compile(r"\bgh[pousr]_[A-Za-z0-9]{30,}\b")),
  ("PRIVATE_KEY_PEM", re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----")),
  ("AUTH_BEARER", re.compile(r"(?i)\bauthorization\s*:\s*bearer\s+\S{10,}")),
  ("SECRET_ASSIGN", re.compile(r"(?i)\b(api[_-]?key|secret|token|access[_-]?key|private[_-]?key)\b\s*[:=]\s*\S{6,}")),
]

def walk_keys(obj, bad):
    if isinstance(obj, dict):
        for k,v in obj.items():
            ks = str(k)
            if ks in FORBIDDEN_KEYS:
                bad.append(("FORBIDDEN_KEY", ks))
            walk_keys(v, bad)
    elif isinstance(obj, list):
        for x in obj:
            walk_keys(x, bad)

def scan_text(s: str):
    hits=[]
    for name, rx in PII_PATTERNS:
        if rx.search(s):
            hits.append(name)
    return hits

for p in files:
    pp = pathlib.Path(p)
    if not pp.exists():
        raise SystemExit(f"FAIL: missing artifact to scan: {p}")

    raw = pp.read_text(encoding="utf-8", errors="replace")

    # 텍스트 기반 PII/secret 스캔(원문 출력 금지: 패턴명/파일만)
    hits = scan_text(raw)
    if hits:
        print("FAIL: meta-only scan detected PII/secret patterns")
        for h in sorted(set(hits))[:20]:
            print(f"- FILE={p} PATTERN={h}")
        raise SystemExit(1)

    # JSON 계열이면 forbidden key를 구조적으로 탐지
    if pp.suffix == ".json":
        try:
            obj = json.loads(raw)
        except Exception as e:
            raise SystemExit(f"FAIL: invalid JSON artifact: {p}: {e}")
        bad=[]
        walk_keys(obj, bad)
        if bad:
            print("FAIL: meta-only JSON contains forbidden keys")
            for _, k in bad[:20]:
                print(f"- FILE={p} KEY={k}")
            raise SystemExit(1)

    # 로그/포인터(.log/.latest)에서는 JSON 키 형태만 추가 탐지 (오탐 방지)
    else:
        # '"query":' 같은 형태만 탐지
        if re.search(r"\"(query|text|content|payload)\"\s*:", raw):
            print("FAIL: meta-only text artifact contains forbidden JSON key pattern")
            print(f"- FILE={p}")
            raise SystemExit(1)

print(f"OK: meta-only verifier scanned {len(files)} file(s)")
PY
