#!/usr/bin/env bash
# S7 Step4-B B 보강 2 검증 원샷 (정본)
# 테스트/보완팀 요구: ONE_SHOT 로그 tail, git status clean, SSOT JSON meta-only 자동 점검

set -euo pipefail
cd "$(git rev-parse --show-toplevel)/webcore_appcore_starter_4_17"

OUT_JSON="docs/ops/r10-s7-step4b-b-strict-improvement.json"
LOG="/tmp/step4b_b_one_shot_$(date +%Y%m%d_%H%M%S).log"

echo "=== 1) RUN ONE_SHOT (capture log) ==="
set +e
bash docs/ops/R10S7_STEP4B_B_ONE_SHOT_PROMPT.sh 2>&1 | tee "$LOG"
RC=${PIPESTATUS[0]}
set -e
echo "ONE_SHOT_EXIT=$RC"

echo "=== 2) SSOT JSON existence (must exist ALWAYS) ==="
test -f "$OUT_JSON" || { echo "FAIL: SSOT JSON not created: $OUT_JSON"; exit 1; }
echo "OK: SSOT JSON exists -> $OUT_JSON"

echo "=== 3) TAIL LOG (80 lines) ==="
tail -n 80 "$LOG"

echo "=== 4) PRINT SSOT JSON (for reviewer) ==="
cat "$OUT_JSON"

echo "=== 5) META-ONLY AUTO CHECK (forbidden patterns + long string) ==="
python3 - <<'PY' "$OUT_JSON"
import json, re, sys
p=sys.argv[1]
raw=open(p,"r",encoding="utf-8").read()
j=json.loads(raw)

# 1) 금지 패턴(대표): URL/IP/email/secret 키워드/주민등록번호 패턴 등
forbid = [
  r"https?://",
  r"\b\d{1,3}(?:\.\d{1,3}){3}\b",  # IPv4
  r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}",
  r"\b(bearer|authorization|token|secret|api[_-]?key|private[_-]?key)\b",
  r"\b\d{6}-\d{7}\b",
]
for rx in forbid:
  if re.search(rx, raw, flags=re.IGNORECASE):
    print("FAIL: forbidden pattern matched:", rx)
    sys.exit(1)

# 2) 값 타입 규칙: 숫자/불리언/None + (짧은 문자열만) 허용
#    긴 문자열은 '자유 텍스트'로 간주하고 FAIL
MAX_STR_LEN = 64

def walk(x, path="$"):
  if isinstance(x, dict):
    for k,v in x.items():
      walk(v, f"{path}.{k}")
  elif isinstance(x, list):
    for i,v in enumerate(x):
      walk(v, f"{path}[{i}]")
  elif isinstance(x, (int,float,bool)) or x is None:
    return
  elif isinstance(x, str):
    if len(x) > MAX_STR_LEN:
      print("FAIL: long string detected (possible free text):", path, "len=", len(x))
      sys.exit(1)
  else:
    print("FAIL: unsupported type:", path, type(x))
    sys.exit(1)

walk(j)
print("OK: meta-only checks passed")

# 3) strict_improvement 결과와 exit code의 정합성 점검(가능한 경우)
#    - strict_improvement=false이면 exit !=0 이 정상 (fail-fast)
#    - strict_improvement=true이면 exit==0 이 정상
#    단, ONE_SHOT 내부에서 regression gate 등 다른 FAIL이 있을 수 있어 여기서는 참고만 출력
try:
  si = j.get("result", {}).get("strict_improvement")
  print("INFO: strict_improvement =", si)
except Exception:
  pass
PY

echo "=== 6) REPO HYGIENE (must be clean) ==="
if [ -n "$(git status --porcelain)" ]; then
  echo "FAIL: working tree not clean"
  git status --porcelain
  exit 1
fi
echo "OK: working tree clean"

echo "=== DONE ==="
echo "ONE_SHOT_LOG=$LOG"
echo "SSOT_JSON=$OUT_JSON"

