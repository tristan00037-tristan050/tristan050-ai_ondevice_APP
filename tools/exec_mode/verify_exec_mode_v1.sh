#!/usr/bin/env bash
set -euo pipefail

INPUTS=""
OUTDIR=""

usage() {
  echo "Usage: $0 --inputs <path.jsonl> --outdir <dir>"
  exit 2
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --inputs) INPUTS="${2:-}"; shift 2;;
    --outdir) OUTDIR="${2:-}"; shift 2;;
    *) usage;;
  esac
done

[[ -n "$INPUTS" && -n "$OUTDIR" ]] || usage
[[ -f "$INPUTS" ]] || { echo "BLOCK: inputs not found: $INPUTS" >&2; exit 1; }

RESULT_PATH="$OUTDIR/result.jsonl"
[[ -f "$RESULT_PATH" ]] || { echo "BLOCK: result not found: $RESULT_PATH" >&2; exit 1; }

# P17-P0-03: SSOT schema (required_keys from JSON only)
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
SCHEMA_PATH="${ROOT}/docs/ops/contracts/EXEC_MODE_SCHEMA_V1.json"
[[ -f "$SCHEMA_PATH" ]] || { echo "BLOCK: SSOT schema not found: $SCHEMA_PATH" >&2; exit 1; }

python3 - "$INPUTS" "$RESULT_PATH" "$SCHEMA_PATH" <<'PY'
import json,sys,os

inputs_path=sys.argv[1]
result_path=sys.argv[2]
schema_path=sys.argv[3]

with open(schema_path,'r',encoding='utf-8') as f:
  schema=json.load(f)
required_keys=schema.get("required_keys")
if not isinstance(required_keys,list) or len(required_keys)==0:
  raise SystemExit("BLOCK: schema required_keys missing or empty")

def read_jsonl(p):
  rows=[]
  with open(p,'r',encoding='utf-8') as f:
    for line in f:
      if not line.strip():
        continue
      rows.append(json.loads(line))  # fail-closed
  return rows

inp=read_jsonl(inputs_path)
out=read_jsonl(result_path)

if len(inp)!=len(out):
  raise SystemExit(f"BLOCK: RESULT_COUNT != INPUT_COUNT ({len(out)} != {len(inp)})")

# build set of ids from inputs
inp_ids=[]
for obj in inp:
  _id=obj.get("id", None)
  if not isinstance(_id,str) or not _id:
    raise SystemExit("BLOCK: input id must be non-empty string")
  inp_ids.append(_id)

# verify each output row (required_keys from SSOT schema)
for i,obj in enumerate(out):
  for k in required_keys:
    if k not in obj:
      raise SystemExit(f"BLOCK: output missing required key (schema): {k!r}")
  _id=obj.get("id", None)
  if not isinstance(_id,str) or not _id:
    raise SystemExit("BLOCK: output id must be non-empty string")
  if "result" not in obj:
    raise SystemExit("BLOCK: output missing result")
  if _id!=inp_ids[i]:
    raise SystemExit("BLOCK: output id order mismatch (must match inputs line-by-line)")

  # required fields per schema
  if "exit_code" not in obj:
    raise SystemExit("BLOCK: output missing exit_code")
  if not isinstance(obj["exit_code"], int):
    raise SystemExit("BLOCK: exit_code must be int")

  if "latency_ms" not in obj:
    raise SystemExit("BLOCK: output missing latency_ms")
  if not isinstance(obj["latency_ms"], int):
    raise SystemExit("BLOCK: latency_ms must be int")

  em=obj.get("engine_meta", None)
  if not isinstance(em,dict):
    raise SystemExit("BLOCK: engine_meta missing or not object")

  eng_meta_engine=em.get("engine", None)
  if not isinstance(eng_meta_engine, str) or not eng_meta_engine:
    raise SystemExit("BLOCK: engine_meta.engine must be non-empty string")

  # tokens_out must exist (int or null); for candidate engine it must be null
  if "tokens_out" not in obj:
    raise SystemExit("BLOCK: output missing tokens_out")
  tokens_out=obj["tokens_out"]

  # tokens_out_supported must be present and false
  tos=em.get("tokens_out_supported", None)
  if tos is not False:
    raise SystemExit("BLOCK: engine_meta.tokens_out_supported must be false")

  if eng_meta_engine=="ondevice_candidate_v0":
    if tokens_out is not None:
      raise SystemExit("BLOCK: ondevice_candidate_v0 requires tokens_out=null")

print("EXEC_MODE_V1_OK=1")
PY
