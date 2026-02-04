#!/usr/bin/env bash
set -euo pipefail

usage() {
  cat <<'USAGE'
verify_pass_gate.sh --verify <one_shot_verify_script> --ssot <ssot_evidence_file>

필수:
  --verify  원샷 검증 스크립트 경로(1줄 실행으로 PASS 재현되어야 함)
  --ssot    SSOT 증거 파일 경로(성공/실패와 무관하게 항상 생성되어야 함)

옵션:
  --log     로그 저장 경로(기본: /tmp/pass_gate_<ts>.log)
  --root    프로젝트 루트(기본: git rev-parse --show-toplevel 기준에서 webcore_appcore_starter_4_17)
USAGE
}

VERIFY=""
SSOT=""
LOG=""
ROOT=""

while [[ $# -gt 0 ]]; do
  case "$1" in
    --verify) VERIFY="$2"; shift 2;;
    --ssot) SSOT="$2"; shift 2;;
    --log) LOG="$2"; shift 2;;
    --root) ROOT="$2"; shift;;
    -h|--help) usage; exit 0;;
    *) echo "FAIL: unknown arg: $1"; usage; exit 2;;
  esac
done

command -v git >/dev/null 2>&1 || { echo "FAIL: git not found"; exit 1; }
command -v python3 >/dev/null 2>&1 || { echo "FAIL: python3 not found"; exit 1; }

if [[ -z "${ROOT}" ]]; then
  ROOT="$(git rev-parse --show-toplevel)/webcore_appcore_starter_4_17"
fi

cd "$ROOT"

if [[ -z "${VERIFY}" || -z "${SSOT}" ]]; then
  echo "FAIL: --verify and --ssot are required"
  usage
  exit 2
fi

if [[ ! -f "${VERIFY}" ]]; then
  echo "FAIL: verify script not found: ${VERIFY}"
  exit 1
fi

if [[ -z "${LOG}" ]]; then
  TS="$(python3 - <<'PY'
import time
print(time.strftime("%Y%m%d_%H%M%S", time.localtime()))
PY
)"
  LOG="/tmp/pass_gate_${TS}.log"
fi

echo "== PASS GATE START =="
echo "ROOT=$ROOT"
echo "VERIFY=$VERIFY"
echo "SSOT=$SSOT"
echo "LOG=$LOG"
echo "TIP: tail -n 80 \"$LOG\""

# 1) 원샷 검증 실행(반드시 0이어야 PASS)
set +e
bash "$VERIFY" >"$LOG" 2>&1
VERIFY_RC=$?
set -e
echo "VERIFY_EXIT=$VERIFY_RC"

# 2) SSOT 증거 파일 존재(항상 생성)
SSOT_EXISTS=0
if [[ -f "$SSOT" ]]; then
  SSOT_EXISTS=1
  echo "OK: SSOT evidence exists: $SSOT"
else
  echo "FAIL: missing SSOT evidence file: $SSOT"
fi

# 3) meta-only 자동 점검(SSOT가 존재할 때만 수행)
META_ONLY_OK=0
if [[ "$SSOT_EXISTS" -eq 1 ]]; then
  python3 - <<'PY' "$SSOT"
import json, re, sys
p=sys.argv[1]
raw=open(p,"r",encoding="utf-8",errors="replace").read()

# 금지 패턴(대표): URL/IP/email/secret 키워드/키 블록 등
forbid = [
  r"https?://",
  r"\b\d{1,3}(?:\.\d{1,3}){3}\b",  # IPv4
  r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}",
  r"\b(bearer|authorization|token|secret|api[_-]?key|private[_-]?key)\b",
  r"AKIA[0-9A-Z]{16}",
  r"-----BEGIN",
  r"ssh-rsa",
  r"\b\d{6}-\d{7}\b",
]
for rx in forbid:
  if re.search(rx, raw, flags=re.IGNORECASE):
    print("FAIL: meta-only forbidden pattern matched:", rx)
    sys.exit(1)

# JSON 파싱
j=json.loads(raw)

# 값 타입 규칙: 숫자/불리언/None + (짧은 문자열)만 허용
MAX_STR_LEN=64

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
      print("FAIL: meta-only long string detected:", path, "len=", len(x))
      sys.exit(1)
  else:
    print("FAIL: meta-only unsupported type:", path, type(x))
    sys.exit(1)

walk(j)
print("OK: meta-only checks passed")
PY
  META_ONLY_OK=1
fi

# 4) 위생: working tree clean
HYGIENE_OK=0
if [[ -z "$(git status --porcelain)" ]]; then
  HYGIENE_OK=1
  echo "OK: working tree clean"
else
  echo "FAIL: working tree not clean"
  git status --porcelain
fi

# 5) .gitignore 봉인 + SSOT 추적 금지(Tracked 금지)
IGNORE_OK=0
TRACKED_OK=0

if [[ -f ".gitignore" ]]; then
  # SSOT가 tracked면 무조건 FAIL
  if git ls-files --error-unmatch "$SSOT" >/dev/null 2>&1; then
    echo "FAIL: SSOT evidence is tracked by git (must be runtime artifact): $SSOT"
  else
    TRACKED_OK=1
    echo "OK: SSOT evidence is not tracked"
  fi

  # .gitignore에 SSOT 경로가 '명시적으로' 포함되어 있어야 봉인(재현성/정합성)
  python3 - <<'PY' ".gitignore" "$SSOT"
import sys
ig_path, ssot = sys.argv[1], sys.argv[2]
lines=open(ig_path,"r",encoding="utf-8",errors="replace").read().splitlines()
for line in lines:
  s=line.strip()
  if not s or s.startswith("#"):
    continue
  if s == ssot:
    print("OK: .gitignore sealed (explicit rule exists)")
    raise SystemExit(0)
print("FAIL: .gitignore missing explicit ignore rule for SSOT:", ssot)
raise SystemExit(1)
PY
  IGNORE_OK=1
else
  echo "FAIL: missing .gitignore"
fi

# 6) verify 스크립트 PASS 여부 반영 + 로그 tail 제공
if [[ "$VERIFY_RC" -ne 0 ]]; then
  echo "FAIL: verify script failed rc=$VERIFY_RC"
  echo "== LOG TAIL (120) =="
  tail -n 120 "$LOG" || true
  exit 1
fi
echo "OK: verify script PASS"

# 여기까지 왔다는 것은 verify가 PASS였다는 뜻.
# 나머지 체크가 모두 PASS여야 최종 PASS.
if [[ "$SSOT_EXISTS" -ne 1 ]]; then exit 1; fi
if [[ "$META_ONLY_OK" -ne 1 ]]; then exit 1; fi
if [[ "$HYGIENE_OK" -ne 1 ]]; then exit 1; fi
if [[ "$TRACKED_OK" -ne 1 ]]; then exit 1; fi
if [[ "$IGNORE_OK" -ne 1 ]]; then exit 1; fi

SHA="$(git rev-parse --short HEAD 2>/dev/null || true)"

echo "== PASS DECLARATION TEMPLATE =="
echo "- 실행(원샷): bash $VERIFY"
echo "- SSOT 증거 파일: $SSOT"
echo "- meta-only: PASS"
echo "- 위생: git status --porcelain 빈 출력"
echo "- 커밋: ${SHA}"
echo "- 로그: $LOG"
echo "- 판정: PASS (CLOSED & SEALED)"

echo "PASS: CLOSED & SEALED eligible"
