#!/usr/bin/env bash
set -euo pipefail

cd "$(git rev-parse --show-toplevel)/webcore_appcore_starter_4_17"

CORPUS="${CORPUS:-docs/ops/r10-s7-retriever-corpus.jsonl}"

fail() { echo "FAIL: $*" >&2; exit 1; }
test -f "$CORPUS" || fail "corpus not found: $CORPUS"

python3 - <<'PY' "$CORPUS"
import json, re, sys

path = sys.argv[1]

# meta-only: 원문 출력 금지(라인번호/패턴만)
PATTERNS = [
  ("EMAIL", re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}")),
  ("URL", re.compile(r"\b(?:https?|wss?)://", re.IGNORECASE)),
  ("IPV4", re.compile(r"\b(?:\d{1,3}\.){3}\d{1,3}\b")),
  ("RRN", re.compile(r"\b\d{6}-\d{7}\b")),
  ("AWS_ACCESS_KEY", re.compile(r"\b(?:AKIA|ASIA)[0-9A-Z]{16}\b")),
  ("GITHUB_TOKEN", re.compile(r"\bgh[pousr]_[A-Za-z0-9]{30,}\b")),
  ("PRIVATE_KEY_PEM", re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----")),
  # 키워드 자체가 아니라 "키/토큰이 실제 값으로 붙는 형태"만 잡는다 (false positive 최소화)
  ("SECRET_ASSIGN", re.compile(
      r"(?i)\b(api[_-]?key|secret|token|access[_-]?key|private[_-]?key)\b\s*[:=]\s*\S{6,}"
  )),
  ("AUTH_BEARER", re.compile(
      r"(?i)\bauthorization\s*:\s*bearer\s+\S{10,}"
  )),
]

bad = []
with open(path, "r", encoding="utf-8") as f:
    for i, line in enumerate(f, 1):
        s = line.strip()
        if not s:
            continue
        # corpus는 JSONL이므로 파싱 실패도 즉시 FAIL(입력 품질 봉인)
        try:
            j = json.loads(s)
        except Exception:
            bad.append(("INVALID_JSON", i))
            continue

        # 스캔 대상: text/id 전체(입력 데이터이므로 텍스트 자체는 허용, PII/secret 패턴만 차단)
        blob = f'{j.get("id","")}\n{j.get("text","")}'
        for name, rx in PATTERNS:
            if rx.search(blob):
                bad.append((name, i))

if bad:
    print("FAIL: corpus contains PII/secret patterns")
    for name, i in bad[:50]:
        print(f"- PATTERN={name} line={i}")
    raise SystemExit(1)

print("OK: corpus no PII/secret patterns detected")
PY

