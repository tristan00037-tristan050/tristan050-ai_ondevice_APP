#!/usr/bin/env bash
set -euo pipefail

AI_FEATURE_DIGEST_V1_PRESENT_OK=0
AI_FEATURE_DIGEST_V1_ALLOWED_KEYS_OK=0
AI_FEATURE_DIGEST_V1_VALUE_LIMITS_OK=0

trap 'echo "AI_FEATURE_DIGEST_V1_PRESENT_OK=${AI_FEATURE_DIGEST_V1_PRESENT_OK}";
      echo "AI_FEATURE_DIGEST_V1_ALLOWED_KEYS_OK=${AI_FEATURE_DIGEST_V1_ALLOWED_KEYS_OK}";
      echo "AI_FEATURE_DIGEST_V1_VALUE_LIMITS_OK=${AI_FEATURE_DIGEST_V1_VALUE_LIMITS_OK}"' EXIT

policy="docs/ops/contracts/FEATURE_DIGEST_POLICY_V1.md"
allow="docs/ops/contracts/FEATURE_DIGEST_ALLOWED_KEYS_V1.txt"
impl="packages/ai/feature_digest/feature_digest_v1.cjs"
gv="scripts/ai/golden_vectors_v2.json"

test -f "$policy" || { echo "BLOCK: missing policy"; exit 1; }
grep -q "FEATURE_DIGEST_POLICY_V1_TOKEN=1" "$policy" || { echo "BLOCK: missing policy token"; exit 1; }

test -f "$allow" || { echo "BLOCK: missing allowlist"; exit 1; }
test -f "$impl" || { echo "BLOCK: missing implementation"; exit 1; }
test -f "$gv" || { echo "BLOCK: missing golden vectors v2 json ($gv)"; exit 1; }

# P2: Detect JSON -0 at text level (python parses -0 as 0)
if grep -EIn '":[[:space:]]*-0([^0-9]|$)' "$gv" >/dev/null 2>&1; then
  echo "BLOCK: forbidden -0 literal detected in JSON"
  exit 1
fi

PYTHON_BIN="python3"
command -v "$PYTHON_BIN" >/dev/null 2>&1 || PYTHON_BIN="python"
command -v "$PYTHON_BIN" >/dev/null 2>&1 || { echo "BLOCK: python3/python not found"; exit 1; }

"$PYTHON_BIN" - <<'PY'
import json, sys, re, pathlib

gv_path = pathlib.Path("scripts/ai/golden_vectors_v2.json")
allow_path = pathlib.Path("docs/ops/contracts/FEATURE_DIGEST_ALLOWED_KEYS_V1.txt")

allow = set([l.strip() for l in allow_path.read_text(encoding="utf-8").splitlines() if l.strip()])

data = json.loads(gv_path.read_text(encoding="utf-8"))

# golden_vectors_v2.json 구조를 모르므로:
# - list 또는 dict 모두 대응
items = []
if isinstance(data, list):
  items = data
elif isinstance(data, dict):
  # 흔한 형태: {"vectors":[...]} 또는 {"cases":[...]} 등
  for k in ("vectors","cases","items","data"):
    if k in data and isinstance(data[k], list):
      items = data[k]; break
  if not items:
    # dict 자체가 단일 케이스일 수도 있음
    items = [data]
else:
  print("BLOCK: golden vectors json is not list/dict")
  sys.exit(1)

found = 0
for it in items:
  if not isinstance(it, dict):
    continue
  # 케이스 내부에 feature_digest_v1이 존재해야 함
  if "feature_digest_v1" not in it:
    continue
  fd = it["feature_digest_v1"]
  if not isinstance(fd, dict):
    print("BLOCK: feature_digest_v1 must be object")
    sys.exit(1)
  found += 1

  for k,v in fd.items():
    if k not in allow:
      print(f"BLOCK: feature_digest_v1 key not allowed: {k}")
      sys.exit(1)
    if v is None:
      continue
    if isinstance(v, bool):
      continue
    if isinstance(v, (int,float)):
      if not (v == v and abs(v) != float("inf")):
        print("BLOCK: non-finite number in feature_digest_v1")
        sys.exit(1)
      # -0 check (python has no -0 distinct for ints; handle float sign)
      if isinstance(v, float) and v == 0.0 and str(v).startswith("-"):
        print("BLOCK: negative zero in feature_digest_v1")
        sys.exit(1)
      continue
    if isinstance(v, str):
      if len(v) > 64:
        print("BLOCK: feature_digest_v1 string too long")
        sys.exit(1)
      continue
    print("BLOCK: feature_digest_v1 value must be primitive")
    sys.exit(1)

if found == 0:
  print("BLOCK: feature_digest_v1 not found in golden_vectors_v2.json")
  sys.exit(1)

print("OK")
PY

AI_FEATURE_DIGEST_V1_PRESENT_OK=1
AI_FEATURE_DIGEST_V1_ALLOWED_KEYS_OK=1
AI_FEATURE_DIGEST_V1_VALUE_LIMITS_OK=1
exit 0
