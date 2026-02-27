#!/usr/bin/env bash
set -euo pipefail

ENGINE=""
INPUTS=""
OUTDIR=""

usage() {
  echo "Usage: $0 --engine <mock|ondevice_candidate_v0|ondevice_runtime_v1> --inputs <path.jsonl> --outdir <dir>"
  exit 2
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --engine) ENGINE="${2:-}"; shift 2;;
    --inputs) INPUTS="${2:-}"; shift 2;;
    --outdir) OUTDIR="${2:-}"; shift 2;;
    *) usage;;
  esac
done

[[ -n "$ENGINE" && -n "$INPUTS" && -n "$OUTDIR" ]] || usage
[[ -f "$INPUTS" ]] || { echo "BLOCK: inputs not found: $INPUTS" >&2; exit 1; }

mkdir -p "$OUTDIR"
RESULT_PATH="$OUTDIR/result.jsonl"
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/../.." && pwd)"
OUTPUT_ROOT="${EXEC_MODE_OUTPUT_ROOT:-$REPO_ROOT/docs}"
REPORT_PATH="$OUTPUT_ROOT/EXEC_MODE_REPORT_V1.md"
mkdir -p "$OUTPUT_ROOT"

# Count inputs (strict: non-empty lines only)
INPUT_COUNT="$(python3 - "$INPUTS" <<'PY'
import sys
p=sys.argv[1]
n=0
with open(p,'r',encoding='utf-8') as f:
  for line in f:
    if line.strip():
      n+=1
print(n)
PY
)"

ts_ms() { python3 - <<'PY'
import time
print(int(time.time()*1000))
PY
}

ENGINE_META_JSON="{}"
ENGINE_EXIT=0
ENGINE_BLOCK=0
ENGINE_STDOUT_LOG=""

if [[ "$ENGINE" == "mock" ]]; then
  # mock: 결과는 항상 성공으로 fan-out
  ENGINE_EXIT=0
  ENGINE_BLOCK=0
  ENGINE_STDOUT_LOG="MOCK_OK=1"
  ENGINE_META_JSON='{"engine":"mock","tokens_out_supported":false,"result_fingerprint_sha256":null}'
elif [[ "$ENGINE" == "ondevice_candidate_v0" ]]; then
  # real compute candidate A: run once
  LOG_PATH="$OUTDIR/ondevice_candidate_v0.log"
  set +e
  bash "$REPO_ROOT/scripts/verify/verify_ondevice_real_compute_once.sh" 2>&1 | tee "$LOG_PATH"
  ENGINE_EXIT="${PIPESTATUS[0]}"
  set -e

  ENGINE_STDOUT_LOG="$(tail -n 400 "$LOG_PATH" || true)"

  # fail-closed signal: BLOCK: in output OR non-zero exit
  if echo "$ENGINE_STDOUT_LOG" | grep -q "BLOCK:"; then ENGINE_BLOCK=1; fi
  if [[ "$ENGINE_EXIT" -ne 0 ]]; then ENGINE_BLOCK=1; fi

  # try extract fingerprint (robust): any 64-hex near result_fingerprint_sha256
  # NOTE: read from LOG_PATH to avoid stdin/empty reads (fail-closed)
  FPR="$(python3 - "$LOG_PATH" <<'PYP'
import re,sys
log_path=sys.argv[1]
text=open(log_path,'r',encoding='utf-8',errors='replace').read()
m=re.search(r"result_fingerprint_sha256[^0-9a-fA-F]*([0-9a-fA-F]{64})", text)
print(m.group(1).lower() if m else "")
PYP
)"

  if [[ -n "$FPR" ]]; then
    ENGINE_META_JSON="$(FPR="$FPR" python3 - <<'PY'
import json,os
fpr=os.environ.get("FPR","")
print(json.dumps({"engine":"ondevice_candidate_v0","tokens_out_supported":False,"result_fingerprint_sha256":fpr}, ensure_ascii=False))
PY
)"
  else
    ENGINE_META_JSON='{"engine":"ondevice_candidate_v0","tokens_out_supported":false,"result_fingerprint_sha256":null}'
  fi

elif [[ "$ENGINE" == "ondevice_runtime_v1" ]]; then
  # real on-device runtime (slot; fail-closed until wired)
  LOG_PATH="$OUTDIR/ondevice_runtime_v1.log"
  set +e
  PROMPT="(slot)" bash "$REPO_ROOT/tools/exec_mode/engines/ondevice_runtime_v1.sh" 2>&1 | tee "$LOG_PATH"
  ENGINE_EXIT="${PIPESTATUS[0]}"
  set -e

  ENGINE_STDOUT_LOG="$(tail -n 400 "$LOG_PATH" || true)"
  if echo "$ENGINE_STDOUT_LOG" | grep -q "BLOCK:"; then ENGINE_BLOCK=1; fi
  if [[ "$ENGINE_EXIT" -ne 0 ]]; then ENGINE_BLOCK=1; fi

  ENGINE_META_JSON='{"engine":"ondevice_runtime_v1","tokens_out_supported":false,"result_fingerprint_sha256":null}'

else
  echo "BLOCK: unknown engine: $ENGINE" >&2
  exit 1
fi

START_MS="$(ts_ms)"
# Build result.jsonl (always valid JSON; id must be string; result must exist; count must match)
python3 - "$ENGINE" "$INPUTS" "$RESULT_PATH" "$ENGINE_EXIT" "$ENGINE_BLOCK" "$ENGINE_META_JSON" <<'PY'
import json,sys,time
engine=sys.argv[1]
inputs_path=sys.argv[2]
result_path=sys.argv[3]
engine_exit=int(sys.argv[4])
engine_block=int(sys.argv[5])
engine_meta=json.loads(sys.argv[6])

# fixed fields
tokens_out=None
engine_meta["tokens_out_supported"]=False  # hard seal

# determine result string
if engine_block or engine_exit!=0:
  result="BLOCK"
  exit_code=1
else:
  result="OK"
  exit_code=0

rows=[]
with open(inputs_path,'r',encoding='utf-8') as f:
  for line in f:
    if not line.strip():
      continue
    obj=json.loads(line)  # fail-closed if invalid
    _id=obj.get("id", None)
    if not isinstance(_id,str) or not _id:
      raise SystemExit("BLOCK: input id must be non-empty string")
    rows.append(_id)

# latency: keep simple (ms)
latency_ms=0

with open(result_path,'w',encoding='utf-8') as out:
  for _id in rows:
    rec={
      "id": _id,
      "result": result,
      "exit_code": exit_code,
      "latency_ms": latency_ms,
      "tokens_out": tokens_out,
      "engine_meta": engine_meta,
    }
    out.write(json.dumps(rec, ensure_ascii=False) + "\n")
PY

END_MS="$(ts_ms)"

# Update report (append/overwrite minimal summary)
python3 - "$ENGINE" "$INPUTS" "$OUTDIR" "$REPORT_PATH" <<'PY'
import os,sys,json
engine=sys.argv[1]
inputs=sys.argv[2]
outdir=sys.argv[3]
report_path=sys.argv[4]
result_path=os.path.join(outdir,"result.jsonl")

def count_lines(p):
  n=0
  with open(p,'r',encoding='utf-8') as f:
    for line in f:
      if line.strip(): n+=1
  return n

inp=count_lines(inputs)
out=count_lines(result_path)

# read one line for meta
meta={}
with open(result_path,'r',encoding='utf-8') as f:
  first=f.readline()
  if first.strip():
    meta=json.loads(first).get("engine_meta",{})

txt=[]
txt.append("# EXEC_MODE_REPORT_V1")
txt.append("")
txt.append("## Latest run")
txt.append(f"- engine: {engine}")
txt.append(f"- inputs: {inp}")
txt.append(f"- outputs: {out}")
txt.append(f"- tokens_out_supported: {meta.get('tokens_out_supported')}")
txt.append(f"- result_fingerprint_sha256: {meta.get('result_fingerprint_sha256')}")
txt.append("")
with open(report_path,'w',encoding='utf-8') as f:
  f.write("\n".join(txt))

# Archive run (commit-able; text only)
from datetime import datetime, timezone
run_date = datetime.now(timezone.utc).strftime("%Y-%m-%d")
archive_dir = os.path.join(os.path.dirname(report_path), "EXEC_MODE_RUNS", run_date)
os.makedirs(archive_dir, exist_ok=True)
archive_path = os.path.join(archive_dir, f"{engine}__{datetime.now(timezone.utc).strftime('%H%M%S%f')}.md")
arch=[]
arch.append("# EXEC_MODE_RUN_ARCHIVE_V1")
arch.append("")
arch.append(f"- utc_date: {run_date}")
arch.append(f"- engine: {engine}")
arch.append(f"- inputs: {inp}")
arch.append(f"- outputs: {out}")
arch.append(f"- tokens_out_supported: {meta.get('tokens_out_supported')}")
arch.append(f"- result_fingerprint_sha256: {meta.get('result_fingerprint_sha256')}")
arch.append("")
with open(archive_path,'w',encoding='utf-8') as af:
  af.write("\n".join(arch))
PY

echo "EXEC_MODE_RUN_OK=1"
echo "ENGINE=$ENGINE INPUT_COUNT=$INPUT_COUNT RESULT_PATH=$RESULT_PATH"
